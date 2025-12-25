# =============================================================================
# AZURE DEVOPS PIPELINE SCHEDULER APPLICATION
# =============================================================================
# Bu uygulama Azure DevOps pipeline'larını zamanlamak için kullanılır
# Kullanıcılar projeler ve pipeline'ları görüntüleyebilir, gelecekte çalıştırılmak üzere zamanlayabilir

# Gerekli kütüphaneleri içe aktarıyoruz
import os                    # Sistem ve dosya işlemleri için
import requests             # HTTP istekleri yapmak için (Azure DevOps API)
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required
from apscheduler.schedulers.background import BackgroundScheduler  # Zamanlanmış görevler için
from datetime import datetime  # Tarih ve saat işlemleri için
import base64               # Authentication için base64 encoding
import json                 # JSON dosya işlemleri için
import time                 # Zaman hesaplamaları için
import sys                  # Sistem işlemleri için
import traceback           # Hata detaylarını göstermek için
import re                  # Regex işlemleri için

# Flask uygulamasını başlatıyoruz
app = Flask(__name__)

# =============================================================================
# LOGIN & SESSION MANAGEMENT
# =============================================================================

# Oturum yönetimi için gizli anahtar (production'da değiştirilmeli)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-should-be-changed')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Giriş yapılmamışsa yönlendirilecek sayfa
login_manager.login_message = "Bu sayfayı görüntülemek için lütfen giriş yapın."
login_manager.login_message_category = "error"

# Basit kullanıcı modeli
class User(UserMixin):
    def __init__(self, id):
        self.id = id

# Kullanıcı veritabanı (geçici, production'da güvenli bir yerden okunmalı)
# Örnek: admin / password
users = {
    "admin": {"password": "password"} 
}

@login_manager.user_loader
def load_user(user_id):
    if user_id in users:
        return User(user_id)
    return None


# =============================================================================
# CONFIGURATION SECTION - Uygulama Ayarları
# =============================================================================

def _read_appsettings_json():
    """appsettings.Test.json dosyasını /app veya proje kökünden okumayı dener."""
    paths = ['/app/appsettings.Test.json', 'appsettings.Test.json']
    for p in paths:
        try:
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    print(f"Konfig dosyası yüklendi: {p}")
                    return cfg
        except json.JSONDecodeError as e:
            print(f"HATA: JSON bozuk ({p}): {e}")
            return None
        except Exception as e:
            print(f"HATA: JSON okunamadı ({p}): {e}")
            return None
    print("HATA: appsettings.Test.json dosyası bulunamadı")
    return None


def _load_ado_setting_from_json(key):
    """appsettings.Test.json içindeki azureDevOps bölümünden istenen anahtarı döndürür."""
    cfg = _read_appsettings_json()
    try:
        if cfg and isinstance(cfg, dict):
            section = cfg.get('azureDevOps') or {}
            val = section.get(key)
            # Placeholder değerleri veya boş değerleri kabul etmeyelim
            if val and isinstance(val, str) and val.strip() and val.strip().lower() not in {"yourvariable", "$(pat)"}:
                return val.strip()
    except Exception:
        pass
    return ""


def load_pat():
    """
    JSON dosyasından Azure DevOps Personal Access Token (PAT) yükler.
    Yoksa boş döner; üst katman env'den dener.
    """
    try:
        pat_value = _load_ado_setting_from_json('pat')
        if pat_value:
            print(f"PAT başarıyla yüklendi. Uzunluk: {len(pat_value)}")
            return pat_value
        print("HATA: JSON'da geçerli PAT değeri bulunamadı")
        return ""
    except Exception as e:
        print(f"HATA: PAT yüklenirken beklenmeyen hata - {e}")
        print(f"Hata detayı: {traceback.format_exc()}")
        return ""

# Azure DevOps bağlantı ayarları - Sadece JSON'dan yüklenir (ENV fallback kapalı)
AZURE_DEVOPS_ORG_URL = (
    _load_ado_setting_from_json('AZURE_DEVOPS_ORG_URL')
    or ""
)
AZURE_DEVOPS_PROJECT = (
    _load_ado_setting_from_json('AZURE_DEVOPS_PROJECT')
    or ""
)

# PAT'ı yüklemeye çalışıyoruz
print("Uygulama başlatılıyor - Konfigürasyon yükleniyor...")
AZURE_DEVOPS_PAT = load_pat()

# ENV fallback tamamen kapatıldı
if not AZURE_DEVOPS_PAT:
    print("UYARI: appsettings.Test.json içinde geçerli PAT bulunamadı. Demo verileri kullanılacak.")

# Fail-fast guard: PAT varsa URL ve Project zorunlu
if AZURE_DEVOPS_PAT and (not AZURE_DEVOPS_ORG_URL or not AZURE_DEVOPS_PROJECT):
    print("HATA: AZURE_DEVOPS_ORG_URL ve AZURE_DEVOPS_PROJECT appsettings.Test.json içinde tanımlı olmalıdır (ENV fallback kapalı).")
    sys.exit(1)

# Konfigürasyon özetini yazdırıyoruz
print("=" * 50)
print("AZURE DEVOPS KONFIGÜRASYONU:")
print(f"Organization URL: {AZURE_DEVOPS_ORG_URL}")
print(f"Varsayılan Proje: {AZURE_DEVOPS_PROJECT}")
print(f"PAT Durumu: {'✓ Mevcut' if AZURE_DEVOPS_PAT else '✗ Yok (Demo modu)'}")
if AZURE_DEVOPS_PAT:
    print(f"PAT Uzunluğu: {len(AZURE_DEVOPS_PAT)}")
print("=" * 50)

# =============================================================================
# SCHEDULER SETUP - Zamanlanmış Görevler İçin
# =============================================================================

# Zamanlanmış görevleri hafızada tutuyoruz (uygulama yeniden başlatıldığında silinir)
scheduled_jobs = []  # Liste formatında görevleri saklıyoruz

# Arka planda çalışacak zamanlayıcıyı başlatıyoruz
try:
    scheduler = BackgroundScheduler()
    scheduler.start()
    print("✓ Zamanlayıcı başarıyla başlatıldı")
except Exception as e:
    print(f"HATA: Zamanlayıcı başlatılamadı - {e}")
    print("Uygulama zamanlama özelliği olmadan çalışacak")
    scheduler = None

# =============================================================================
# CACHE SYSTEM - Veri Önbelleği Sistemi
# =============================================================================
# Azure DevOps'tan aldığımız verileri dosyada saklıyoruz
# Bu sayede her defasında API'ye gitmek zorunda kalmıyoruz

# Cache dosya isimleri
PROJECTS_CACHE_FILE = 'projects_cache.json'    # Proje listesi için
PIPELINES_CACHE_FILE = 'pipelines_cache.json'  # Pipeline listesi için
CACHE_EXPIRY_HOURS = 24  # Cache 24 saat sonra eski sayılır ve yenilenir

# Projeler için cache yapısı
projects_cache = {
    'data': [],          # Proje listesi burada tutulur
    'last_updated': 0    # Son güncellenme zamanı (timestamp)
}

# Pipeline'lar için cache yapısı  
pipelines_cache = {
    'data': {},          # Proje bazında pipeline'lar: {proje_adı: [pipeline_listesi]}
    'last_updated': 0    # Son güncellenme zamanı (timestamp)
}

print("Cache sistemi hazırlandı")

# =============================================================================
# CACHE HELPER FUNCTIONS - Önbellek Yardımcı Fonksiyonları
# =============================================================================

def load_projects_cache():
    """
    Proje cache dosyasını yükler
    Eğer dosya yoksa veya bozuksa, boş cache oluşturur
    """
    global projects_cache
    try:
        print(f"Proje cache dosyası kontrol ediliyor: {PROJECTS_CACHE_FILE}")
        
        # Dosya var mı kontrol ediyoruz
        if os.path.exists(PROJECTS_CACHE_FILE):
            print("Cache dosyası bulundu, yükleniyor...")
            
            # Dosyayı okuyoruz
            with open(PROJECTS_CACHE_FILE, 'r', encoding='utf-8') as f:
                loaded_cache = json.load(f)
                
            # Cache yapısını kontrol ediyoruz
            if isinstance(loaded_cache, dict) and 'data' in loaded_cache and 'last_updated' in loaded_cache:
                projects_cache = loaded_cache
                cache_age_hours = (time.time() - projects_cache['last_updated']) / 3600
                print(f"✓ Proje cache yüklendi. Yaş: {cache_age_hours:.1f} saat, Proje sayısı: {len(projects_cache['data'])}")
            else:
                print("UYARI: Cache dosyası geçersiz yapıda, sıfırlanıyor")
                projects_cache = {'data': [], 'last_updated': 0}
        else:
            print("Cache dosyası bulunamadı, yeni cache oluşturulacak")
            
    except json.JSONDecodeError as e:
        print(f"HATA: Proje cache dosyası bozuk JSON - {e}")
        projects_cache = {'data': [], 'last_updated': 0}
    except PermissionError:
        print("HATA: Cache dosyasına erişim yetkisi yok")
        projects_cache = {'data': [], 'last_updated': 0}
    except Exception as e:
        print(f"HATA: Proje cache yüklenirken beklenmeyen hata - {e}")
        print(f"Hata detayı: {traceback.format_exc()}")
        projects_cache = {'data': [], 'last_updated': 0}

def save_projects_cache():
    """
    Proje cache'ini dosyaya kaydeder
    Hata durumunda devam eder (kritik değil)
    """
    try:
        print(f"Proje cache kaydediliyor: {len(projects_cache['data'])} proje")
        
        # Dosyaya yazıyoruz (güzel formatlı)
        with open(PROJECTS_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(projects_cache, f, indent=2, ensure_ascii=False)
            
        print("✓ Proje cache başarıyla kaydedildi")
        
    except PermissionError:
        print("HATA: Cache dosyasına yazma yetkisi yok")
    except OSError as e:
        print(f"HATA: Cache dosyası yazılamıyor - disk dolu veya erişim sorunu: {e}")
    except Exception as e:
        print(f"HATA: Proje cache kaydedilirken beklenmeyen hata - {e}")
        print(f"Hata detayı: {traceback.format_exc()}")

def load_pipelines_cache():
    """
    Pipeline cache dosyasını yükler
    Eğer dosya yoksa veya bozuksa, boş cache oluşturur
    """
    global pipelines_cache
    try:
        print(f"Pipeline cache dosyası kontrol ediliyor: {PIPELINES_CACHE_FILE}")
        
        # Dosya var mı kontrol ediyoruz
        if os.path.exists(PIPELINES_CACHE_FILE):
            print("Cache dosyası bulundu, yükleniyor...")
            
            # Dosyayı okuyoruz
            with open(PIPELINES_CACHE_FILE, 'r', encoding='utf-8') as f:
                loaded_cache = json.load(f)
                
            # Cache yapısını kontrol ediyoruz
            if isinstance(loaded_cache, dict) and 'data' in loaded_cache and 'last_updated' in loaded_cache:
                pipelines_cache = loaded_cache
                cache_age_hours = (time.time() - pipelines_cache['last_updated']) / 3600
                total_pipelines = sum(len(pipelines) for pipelines in pipelines_cache['data'].values())
                print(f"✓ Pipeline cache yüklendi. Yaş: {cache_age_hours:.1f} saat, Toplam pipeline: {total_pipelines}")
            else:
                print("UYARI: Cache dosyası geçersiz yapıda, sıfırlanıyor")
                pipelines_cache = {'data': {}, 'last_updated': 0}
        else:
            print("Cache dosyası bulunamadı, yeni cache oluşturulacak")
            
    except json.JSONDecodeError as e:
        print(f"HATA: Pipeline cache dosyası bozuk JSON - {e}")
        pipelines_cache = {'data': {}, 'last_updated': 0}
    except PermissionError:
        print("HATA: Cache dosyasına erişim yetkisi yok")
        pipelines_cache = {'data': {}, 'last_updated': 0}
    except Exception as e:
        print(f"HATA: Pipeline cache yüklenirken beklenmeyen hata - {e}")
        print(f"Hata detayı: {traceback.format_exc()}")
        pipelines_cache = {'data': {}, 'last_updated': 0}

def save_pipelines_cache():
    """
    Pipeline cache'ini dosyaya kaydeder
    Hata durumunda devam eder (kritik değil)
    """
    try:
        total_pipelines = sum(len(pipelines) for pipelines in pipelines_cache['data'].values())
        print(f"Pipeline cache kaydediliyor: {total_pipelines} pipeline")
        
        # Dosyaya yazıyoruz (güzel formatlı)
        with open(PIPELINES_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(pipelines_cache, f, indent=2, ensure_ascii=False)
            
        print("✓ Pipeline cache başarıyla kaydedildi")
        
    except PermissionError:
        print("HATA: Cache dosyasına yazma yetkisi yok")
    except OSError as e:
        print(f"HATA: Cache dosyası yazılamıyor - disk dolu veya erişim sorunu: {e}")
    except Exception as e:
        print(f"HATA: Pipeline cache kaydedilirken beklenmeyen hata - {e}")
        print(f"Hata detayı: {traceback.format_exc()}")

# =============================================================================
# AZURE DEVOPS API FUNCTIONS - Azure DevOps ile İletişim Fonksiyonları
# =============================================================================

def fetch_projects_from_azure():
    """
    Azure DevOps'tan tüm projeleri çeker
    Eğer PAT yoksa demo veriler döner
    Network hatalarında boş liste döner
    """
    print("\n[FETCH PROJECTS] Azure DevOps projelerini getirme işlemi başladı")
    
    # PAT kontrolü - yoksa demo veri döndür
    if not AZURE_DEVOPS_PAT:
        print("⚠️  PAT bulunamadı, demo verileri kullanılıyor")
        return [
            {"id": "sample1", "name": "Sample Project 1", "description": "Sample project for demo", "state": "wellFormed"},
            {"id": "sample2", "name": "Sample Project 2", "description": "Another sample project", "state": "wellFormed"}
        ]
    
    # API URL'ini oluştur
    api_url = f"{AZURE_DEVOPS_ORG_URL}/_apis/projects?api-version=6.0"
    print(f"🌐 API URL: {api_url}")
    print(f"🔑 PAT Durumu: {'✓ Mevcut' if AZURE_DEVOPS_PAT else '✗ Yok'} (Uzunluk: {len(AZURE_DEVOPS_PAT)})")
    
    # Authorization header'ı hazırla (Base64 encoding ile)
    try:
        auth_string = f":{AZURE_DEVOPS_PAT}"
        encoded_auth = base64.b64encode(auth_string.encode("ascii")).decode("ascii")
        headers = {
            'Authorization': f'Basic {encoded_auth}',
            'Content-Type': 'application/json',
            'User-Agent': 'Pipeline-Scheduler/1.0'
        }
    except Exception as e:
        print(f"❌ Authorization header oluşturulamadı: {e}")
        return []
    
    # API çağrısını yap
    try:
        print("📡 Azure DevOps API'sine bağlanıyor...")
        response = requests.get(api_url, headers=headers, timeout=30)
        
        # HTTP durum kodunu kontrol et
        if response.status_code == 401:
            print("❌ Yetkilendirme hatası (401) - PAT geçersiz veya süresi dolmuş")
            return []
        elif response.status_code == 403:
            print("❌ Erişim reddedildi (403) - PAT'in proje okuma yetkisi yok")
            return []
        elif response.status_code == 404:
            print("❌ Organization bulunamadı (404) - URL hatalı olabilir")
            return []
            
        response.raise_for_status()  # Diğer HTTP hatalarını yakala
        
        # JSON response'u parse et
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            print(f"❌ API response JSON formatında değil: {e}")
            print(f"Response içeriği: {response.text[:200]}...")
            return []
        
        # Proje listesini işle
        if 'value' not in data:
            print("❌ API response'unda 'value' anahtarı bulunamadı")
            print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
            return []
        
        projects = []
        for project in data.get('value', []):
            try:
                # Her projeyi güvenli şekilde işle
                project_info = {
                    'id': project.get('id', ''),
                    'name': project.get('name', 'Unknown'),
                    'description': project.get('description', ''),
                    'state': project.get('state', 'wellFormed')
                }
                
                # Zorunlu alanları kontrol et
                if not project_info['id'] or not project_info['name']:
                    print(f"⚠️  Eksik bilgi içeren proje atlandı: {project}")
                    continue
                    
                projects.append(project_info)
                
            except Exception as e:
                print(f"⚠️  Proje işlenirken hata: {e}, Proje: {project}")
                continue
        
        print(f"✅ {len(projects)} proje başarıyla alındı")
        return projects
        
    except requests.exceptions.Timeout as e:
        print(f"⏱️  Zaman aşımı hatası (30 saniye): {e}")
        print("Network bağlantısı yavaş olabilir veya server yanıt vermiyor")
        return []
    except requests.exceptions.ConnectionError as e:
        print(f"🌐 Bağlantı hatası: {e}")
        print("Azure DevOps server'ına ulaşılamıyor - Network/DNS sorunu olabilir")
        return []
    except requests.exceptions.HTTPError as e:
        print(f"📡 HTTP hatası: {e}")
        print(f"Response status code: {e.response.status_code if e.response else 'Unknown'}")
        if e.response:
            print(f"Response content: {e.response.text[:200]}...")
        return []
    except Exception as e:
        print(f"❌ Beklenmeyen hata: {e}")
        print(f"Hata detayı: {traceback.format_exc()}")
        return []

def fetch_pipelines_from_azure(project_name):
    """
    Belirtilen proje için Azure DevOps'tan tüm pipeline'ları (build definitions) çeker
    Eğer PAT yoksa demo veriler döner
    Network hatalarında boş liste döner
    """
    print(f"\n[FETCH PIPELINES] '{project_name}' projesinin pipeline'ları getiriliyor")
    
    # Proje adını kontrol et
    if not project_name or project_name.strip() == "":
        print("❌ Proje adı boş veya geçersiz")
        return []
    
    project_name = project_name.strip()
    
    # PAT kontrolü - yoksa demo veri döndür (Prod filtreli)
    if not AZURE_DEVOPS_PAT:
        print("⚠️  PAT bulunamadı, Prod filtreli demo verileri kullanılıyor")
        return [
            {"id": 584, "name": "Sample Prod Pipeline 1", "path": "\\", "project": project_name},
            {"id": 585, "name": "Sample Production Pipeline 2", "path": "\\", "project": project_name},
        ]
    
    # API URL'ini oluştur (proje adını URL encode et)
    try:
        # Proje adındaki özel karakterleri encode et
        encoded_project = requests.utils.quote(project_name, safe='')
        api_url = f"{AZURE_DEVOPS_ORG_URL}/{encoded_project}/_apis/build/definitions?api-version=6.0"
        print(f"🌐 API URL: {api_url}")
    except Exception as e:
        print(f"❌ API URL oluşturulamadı: {e}")
        return []
    
    # Authorization header'ı hazırla
    try:
        auth_string = f":{AZURE_DEVOPS_PAT}"
        encoded_auth = base64.b64encode(auth_string.encode("ascii")).decode("ascii")
        headers = {
            'Authorization': f'Basic {encoded_auth}',
            'Content-Type': 'application/json',
            'User-Agent': 'Pipeline-Scheduler/1.0'
        }
    except Exception as e:
        print(f"❌ Authorization header oluşturulamadı: {e}")
        return []
    
    # API çağrısını yap
    try:
        print(f"📡 '{project_name}' projesi için pipeline'lar alınıyor...")
        response = requests.get(api_url, headers=headers, timeout=30)
        
        # HTTP durum kodunu kontrol et
        if response.status_code == 401:
            print("❌ Yetkilendirme hatası (401) - PAT geçersiz")
            return []
        elif response.status_code == 403:
            print(f"❌ Erişim reddedildi (403) - '{project_name}' projesine erişim yetkisi yok")
            return []
        elif response.status_code == 404:
            print(f"❌ Proje bulunamadı (404) - '{project_name}' projesi mevcut değil")
            return []
            
        response.raise_for_status()  # Diğer HTTP hatalarını yakala
        
        # JSON response'u parse et
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            print(f"❌ API response JSON formatında değil: {e}")
            print(f"Response içeriği: {response.text[:200]}...")
            return []
        
        # Pipeline listesini işle
        if 'value' not in data:
            print("❌ API response'unda 'value' anahtarı bulunamadı")
            print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
            return []
        
        pipelines = []
        for definition in data.get('value', []):
            try:
                # Her pipeline'ı güvenli şekilde işle
                pipeline_info = {
                    'id': definition.get('id'),
                    'name': definition.get('name', 'Unknown Pipeline'),
                    'path': definition.get('path', '\\'),
                    'revision': definition.get('revision', 1),
                    'project': project_name,
                    'quality': definition.get('quality', 'definition'),
                    'type': definition.get('type', 'build')
                }
                
                # Zorunlu alanları kontrol et
                if pipeline_info['id'] is None or not pipeline_info['name']:
                    print(f"⚠️  Eksik bilgi içeren pipeline atlandı: {definition}")
                    continue
                
                # ID'nin sayı olduğunu kontrol et
                try:
                    pipeline_info['id'] = int(pipeline_info['id'])
                except (ValueError, TypeError):
                    print(f"⚠️  Geçersiz ID'li pipeline atlandı: {definition}")
                    continue
                
                # PROD FİLTRESİ: Sadece adında "prod" geçen pipeline'ları ekle (büyük-küçük harf duyarsız)
                pipeline_name = pipeline_info['name'].lower()
                if 'prod' not in pipeline_name:
                    print(f"🔍 Pipeline filtrelendi (Prod içermiyor): {pipeline_info['name']}")
                    continue
                    
                pipelines.append(pipeline_info)
                print(f"✅ Prod pipeline eklendi: {pipeline_info['name']}")
                
            except Exception as e:
                print(f"⚠️  Pipeline işlenirken hata: {e}, Pipeline: {definition}")
                continue
        
        print(f"✅ '{project_name}' projesi için {len(pipelines)} pipeline başarıyla alındı")
        return pipelines
        
    except requests.exceptions.Timeout as e:
        print(f"⏱️  Zaman aşımı hatası (30 saniye) - Proje: {project_name}: {e}")
        return []
    except requests.exceptions.ConnectionError as e:
        print(f"🌐 Bağlantı hatası - Proje: {project_name}: {e}")
        return []
    except requests.exceptions.HTTPError as e:
        print(f"📡 HTTP hatası - Proje: {project_name}: {e}")
        if e.response:
            print(f"Response status code: {e.response.status_code}")
            print(f"Response content: {e.response.text[:200]}...")
        return []
    except Exception as e:
        print(f"❌ Beklenmeyen hata - Proje: {project_name}: {e}")
        print(f"Hata detayı: {traceback.format_exc()}")
        return []

# =============================================================================
# DATA MANAGEMENT FUNCTIONS - Veri Yönetim Fonksiyonları  
# =============================================================================

def get_projects():
    """
    Proje listesini döner - önce cache'den kontrol eder, yoksa Azure DevOps'tan çeker
    Cache süresi dolmuşsa veya boşsa yeniden API çağrısı yapar
    """
    global projects_cache
    
    try:
        print("\n[GET PROJECTS] Proje listesi istendi")
        
        current_time = time.time()
        cache_age_hours = (current_time - projects_cache['last_updated']) / 3600
        
        print(f"📋 Cache durumu: {len(projects_cache['data'])} proje, Yaş: {cache_age_hours:.1f} saat")
        
        # Cache boş veya süresi dolmuşsa yenile
        if not projects_cache['data'] or cache_age_hours > CACHE_EXPIRY_HOURS:
            print("🔄 Cache yenileniyor (boş veya eski)...")
            projects = fetch_projects_from_azure()
            
            # Sadece veri varsa cache'i güncelle
            if projects:
                projects_cache['data'] = projects
                projects_cache['last_updated'] = current_time
                save_projects_cache()
                print(f"✅ Cache güncellendi: {len(projects)} proje")
            else:
                print("⚠️  API'den veri alınamadı, mevcut cache kullanılıyor")
        else:
            print("✅ Cache geçerli, mevcut veriler kullanılıyor")
        
        return projects_cache['data']
        
    except Exception as e:
        print(f"❌ get_projects hatası: {e}")
        print(f"Hata detayı: {traceback.format_exc()}")
        return []

def get_build_status(project_name, build_id):
    """
    Azure DevOps'tan belirli bir build'in durumunu sorgular
    Build status: notStarted, inProgress, completed
    Build result: succeeded, partiallySucceeded, failed, canceled
    """
    if not AZURE_DEVOPS_PAT or not build_id:
        return None
        
    try:
        # URL encode project name
        encoded_project = requests.utils.quote(project_name, safe='')
        api_url = f"{AZURE_DEVOPS_ORG_URL}/{encoded_project}/_apis/build/builds/{build_id}?api-version=6.0"
        
        # Authorization header
        auth_string = f":{AZURE_DEVOPS_PAT}"
        encoded_auth = base64.b64encode(auth_string.encode("ascii")).decode("ascii")
        headers = {
            'Authorization': f'Basic {encoded_auth}',
            'Content-Type': 'application/json',
            'User-Agent': 'Pipeline-Scheduler/1.0'
        }
        
        print(f"🔍 Build #{build_id} durumu kontrol ediliyor...")
        response = requests.get(api_url, headers=headers, timeout=30)
        
        if response.status_code == 404:
            print(f"❌ Build #{build_id} bulunamadı")
            return None
        elif response.status_code == 403:
            print(f"❌ Build #{build_id} erişim yetkisi yok")
            return None
            
        response.raise_for_status()
        build_data = response.json()
        
        # Build durumunu çıkar
        status = build_data.get('status', 'unknown')  # notStarted, inProgress, completed
        result = build_data.get('result')  # succeeded, failed, canceled, etc.
        start_time = build_data.get('startTime')
        finish_time = build_data.get('finishTime')
        
        print(f"📊 Build #{build_id} - Status: {status}, Result: {result}")
        
        return {
            'id': build_id,
            'status': status,
            'result': result,
            'startTime': start_time,
            'finishTime': finish_time,
            'url': build_data.get('_links', {}).get('web', {}).get('href', '#')
        }
        
    except requests.exceptions.Timeout:
        print(f"⏱️  Build status sorgusu zaman aşımına uğradı: Build #{build_id}")
        return None
    except requests.exceptions.ConnectionError:
        print(f"🌐 Build status sorgusunda bağlantı hatası: Build #{build_id}")
        return None
    except Exception as e:
        print(f"❌ Build status sorgu hatası: {e}")
        return None

def monitor_build_status(job_id, project_name, build_id):
    """
    Build durumunu izler ve job status'unu günceller
    Bu fonksiyon scheduler tarafından periyodik olarak çağrılır
    """
    print(f"\n[MONITOR] Job {job_id} için Build #{build_id} izleniyor...")
    
    # Job'ı bul
    job_to_update = next((job for job in scheduled_jobs if job['id'] == job_id), None)
    if not job_to_update:
        print(f"⚠️  Job {job_id} bulunamadı, izleme durduruluyor")
        return
    
    # Build durumunu al
    build_status = get_build_status(project_name, build_id)
    if not build_status:
        print(f"⚠️  Build #{build_id} durumu alınamadı")
        return
    
    # Status'a göre job'ı güncelle - detaylı bilgiyi status alanına koy
    if build_status['status'] == 'inProgress':
        if job_to_update['status'] != f"Pipeline çalışıyor... Build #{build_id}":
            job_to_update['status'] = f"Pipeline çalışıyor... Build #{build_id}"
            print(f"🔄 Job {job_id} durumu 'Running' olarak güncellendi")
    
    elif build_status['status'] == 'completed':
        # Build tamamlandı, result'a bak - detaylı mesajı status'a koy
        if build_status['result'] == 'succeeded':
            job_to_update['status'] = f"Pipeline başarıyla tamamlandı! Build #{build_id}"
            print(f"✅ Job {job_id} başarıyla tamamlandı")
            # Eğer bu job'a bağlı zincir (chain) işleri varsa sıradaki işi tetikle
            try:
                chain_queue = job_to_update.get('chain_queue', [])
                if chain_queue:
                    next_child_job_id = chain_queue.pop(0)
                    # Çocuk job'ı bul
                    child_job = next((j for j in scheduled_jobs if j['id'] == next_child_job_id), None)
                    if child_job:
                        # Çocuğun runtime parametrelerini hazırla
                        child_runtime_params = child_job.get('runtime_parameters') or {}
                        if not child_runtime_params and child_job.get('desktechID'):
                            child_runtime_params = {'desktechID': child_job['desktechID']}
                        # Kalan chain'i çocuğa devret (böylece başarıyla tamamlandıkça sırayla tetiklenecek)
                        child_job['chain_queue'] = chain_queue[:] if isinstance(chain_queue, list) else []
                        job_to_update['chain_queue'] = []
                        print(f"⛓️  Zincir tetikleniyor: Parent={job_id} -> Child={child_job['id']} ({child_job['pipeline_name']})")
                        # Hemen tetikle
                        trigger_pipeline(child_job['definition_id'], job_id=child_job['id'], runtime_parameters=child_runtime_params)
                    else:
                        print(f"⚠️  Zincir çocuğu bulunamadı: {next_child_job_id}")
            except Exception as chain_err:
                print(f"⚠️  Zincir tetikleme hatası: {chain_err}")
        elif build_status['result'] == 'failed':
            job_to_update['status'] = f"Pipeline başarısız oldu. Build #{build_id}"
            print(f"❌ Job {job_id} başarısız oldu")
        elif build_status['result'] == 'canceled':
            job_to_update['status'] = f"Pipeline iptal edildi. Build #{build_id}"
            print(f"🚫 Job {job_id} iptal edildi")
        else:
            job_to_update['status'] = f"Pipeline tamamlandı ({build_status['result']}). Build #{build_id}"
            print(f"✓ Job {job_id} tamamlandı: {build_status['result']}")
        
        # Build tamamlandıysa monitoring'i durdur
        try:
            monitor_job_id = f"monitor_{job_id}"
            if scheduler and scheduler.get_job(monitor_job_id):
                scheduler.remove_job(monitor_job_id)
                print(f"🛑 Job {job_id} için monitoring durdurudu")
        except Exception as e:
            print(f"⚠️  Monitoring job silinemedi: {e}")

def get_pipelines(project_name=None):
    """Get pipelines from cache or fetch from Azure DevOps if cache is expired.
    Returns only pipelines with 'prod' in their name (case-insensitive)."""
    global pipelines_cache
    
    if not project_name:
        project_name = AZURE_DEVOPS_PROJECT
    
    current_time = time.time()
    cache_age_hours = (current_time - pipelines_cache['last_updated']) / 3600
    
    # If cache is empty or expired, fetch from Azure DevOps
    if project_name not in pipelines_cache['data'] or cache_age_hours > CACHE_EXPIRY_HOURS:
        print(f"Cache expired or empty for project {project_name}, fetching pipelines from Azure DevOps...")
        pipelines = fetch_pipelines_from_azure(project_name)  # Bu fonksiyon zaten Prod filtreli veri dönüyor
        
        if pipelines:  # Only update cache if we got data
            pipelines_cache['data'][project_name] = pipelines
            pipelines_cache['last_updated'] = current_time
            save_pipelines_cache()
    
    # Cache'den al ve ekstra Prod filtresi uygula (güvenlik için)
    all_pipelines = pipelines_cache['data'].get(project_name, [])
    prod_pipelines = [p for p in all_pipelines if 'prod' in p['name'].lower()]
    
    if len(prod_pipelines) != len(all_pipelines):
        print(f"🔍 Cache'den {len(all_pipelines)} pipeline var, Prod filtresi sonrası {len(prod_pipelines)} pipeline dönüyor")
    
    return prod_pipelines

def get_pipeline_name_by_id(pipeline_id, project_name=None):
    """Get pipeline name by ID."""
    if not project_name:
        # Search in all projects
        for proj_name, pipelines in pipelines_cache['data'].items():
            for pipeline in pipelines:
                try:
                    if int(pipeline['id']) == int(pipeline_id):
                        return pipeline['name']
                except Exception:
                    if pipeline['id'] == pipeline_id:
                        return pipeline['name']
    else:
        pipelines = get_pipelines(project_name)
        for pipeline in pipelines:
            try:
                if int(pipeline['id']) == int(pipeline_id):
                    return pipeline['name']
            except Exception:
                if pipeline['id'] == pipeline_id:
                    return pipeline['name']
    return f"Pipeline {pipeline_id}"

def trigger_pipeline(definition_id, job_id=None, runtime_parameters=None):
    """Triggers a pipeline build in Azure DevOps."""
    # Find the project name for this pipeline
    project_name = None
    for proj_name, pipelines in pipelines_cache['data'].items():
        for pipeline in pipelines:
            if pipeline['id'] == definition_id:
                project_name = proj_name
                break
        if project_name:
            break
    
    if not project_name:
        project_name = AZURE_DEVOPS_PROJECT  # Fallback to default
    
    api_url = f"{AZURE_DEVOPS_ORG_URL}/{project_name}/_apis/build/builds?api-version=6.0"
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Basic {base64.b64encode(f":{AZURE_DEVOPS_PAT}".encode("ascii")).decode("ascii")}'
    }
    
    # Build definition detaylarını al (YAML mi Classic mi, defaultBranch nedir?)
    is_yaml_definition = True
    default_branch = "refs/heads/main"
    try:
        encoded_project = requests.utils.quote(project_name, safe='')
        def_url = f"{AZURE_DEVOPS_ORG_URL}/{encoded_project}/_apis/build/definitions/{definition_id}?api-version=6.0"
        def_resp = requests.get(def_url, headers=headers, timeout=30)
        if def_resp.ok:
            def_json = def_resp.json()
            process_type = def_json.get('process', {}).get('type')
            # Azure DevOps: 1 = designer (Classic), 2 = YAML
            is_yaml_definition = (process_type == 2)
            repo_info = def_json.get('repository', {})
            default_branch = repo_info.get('defaultBranch') or default_branch
            print(f"ℹ️  Definition #{definition_id}: is_yaml={is_yaml_definition}, default_branch={default_branch}")
        else:
            print(f"⚠️  Definition detayları alınamadı (HTTP {def_resp.status_code}), varsayılanlar kullanılacak")
    except Exception as def_err:
        print(f"⚠️  Definition detayları sorgusunda hata: {def_err}")
    
    body = {
        "definition": {
            "id": definition_id
        },
        # Varsayılan branch; definition'dan okumaya çalıştık, yoksa main
        "sourceBranch": default_branch
    }

    # YAML vs Classic için parametreleri uygun alanda ilet
    if runtime_parameters:
        try:
            if is_yaml_definition:
                body["templateParameters"] = runtime_parameters
                print(f"▶️  templateParameters eklendi: {runtime_parameters}")
            else:
                body["parameters"] = json.dumps(runtime_parameters)
                print(f"▶️  parameters eklendi (Classic): {body['parameters']}")
        except Exception as param_err:
            print(f"⚠️  Parametreler istek gövdesine eklenemedi: {param_err}")
    
    job_to_update = next((job for job in scheduled_jobs if job['id'] == job_id), None) if job_id else None

    try:
        response = requests.post(api_url, headers=headers, json=body)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        build_info = response.json()
        
        build_id = build_info.get('id')
        
        if job_to_update and build_id:
            job_to_update['status'] = f"Triggered successfully: #{build_id}"
            job_to_update['build_url'] = build_info.get('_links', {}).get('web', {}).get('href', '#')
            job_to_update['build_id'] = build_id  # Build ID'yi sakla
            job_to_update['project_name'] = project_name  # Project adını sakla
            
            # Build status monitoring başlat - her 30 saniyede bir kontrol et
            if scheduler:
                try:
                    monitor_job_id = f"monitor_{job_id}"
                    scheduler.add_job(
                        monitor_build_status,
                        'interval',
                        seconds=30,  # Her 30 saniyede kontrol et
                        args=[job_id, project_name, build_id],
                        id=monitor_job_id,
                        max_instances=1  # Aynı anda sadece bir instance çalışsın
                    )
                    print(f"🔍 Build #{build_id} için monitoring başlatıldı (her 30 saniye)")
                except Exception as monitor_error:
                    print(f"⚠️  Monitoring başlatılamadı: {monitor_error}")
        
        print(f"Successfully triggered build for definition {definition_id} in project {project_name}. Build ID: {build_id}")

    except requests.exceptions.RequestException as e:
        error_message = f"Failed to trigger pipeline in project {project_name}: {str(e)}"
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_details = e.response.json()
                # Derinlemesine validasyon detaylarını oku
                base_msg = error_details.get('message') or str(e)
                validation_msgs = []
                if isinstance(error_details, dict):
                    vr = error_details.get('validationResults') or error_details.get('ValidationResults')
                    if isinstance(vr, list):
                        for item in vr:
                            msg = item.get('message') or item.get('Message')
                            if msg:
                                validation_msgs.append(msg)
                if validation_msgs:
                    error_message = f"Pipeline trigger failed: {base_msg} | Details: {'; '.join(validation_msgs)}"
                else:
                    error_message = f"Pipeline trigger failed: {base_msg}"
            except Exception as parse_err:
                try:
                    # JSON parse edilemezse düz metni ekle
                    error_text = e.response.text[:500]
                    error_message = f"Pipeline trigger failed: HTTP {e.response.status_code} | {error_text}"
                except Exception:
                    error_message = f"Pipeline trigger failed: HTTP {getattr(e.response, 'status_code', 'unknown')}"
        
        if job_to_update:
            job_to_update['status'] = f"{error_message}"
        print(error_message)

# --- Routes ---
@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/schedule', methods=['POST'])
@login_required
def schedule_pipeline():
    """
    Pipeline zamanlama endpoint'i
    Geçmiş zaman ve şu andan 2 dakika öncesi için zamanlama yapılamaz
    """
    data = request.json
    try:
        definition_id = int(data['definition_id'])
        run_datetime_str = data['run_datetime']
        # desktechID parametresi: sadece pozitif sayısal değer kabul edilir
        desktech_id_raw = str(data.get('desktechID', '')).strip()
        if not re.fullmatch(r'^[1-9]\d*$', desktech_id_raw):
            return jsonify({
                'status': 'error',
                'message': 'desktechID parametresi pozitif sayısal bir değer olmalıdır.'
            }), 400
        run_datetime = datetime.fromisoformat(run_datetime_str)
        
        # Server-side datetime validation
        from datetime import timedelta
        now = datetime.now()
        min_allowed_time = now + timedelta(minutes=2)
        
        if run_datetime < min_allowed_time:
            min_time_str = min_allowed_time.strftime('%Y-%m-%d %H:%M')
            return jsonify({
                'status': 'error', 
                'message': f'⚠️ Zamanlama en az şu andan 2 dakika sonrası olmalıdır. En erken: {min_time_str}'
            }), 400
        
        job_id = f"{definition_id}_{run_datetime.strftime('%Y%m%d%H%M%S')}"

        # Add job to our in-memory list for tracking
        # Proje adını çöz (definition_id -> project mapping)
        project_name_for_def = AZURE_DEVOPS_PROJECT
        try:
            for proj_name, pdata in pipelines_cache['data'].items():
                if any(int(p['id']) == int(definition_id) for p in pdata.get('pipelines', [])):
                    project_name_for_def = proj_name
                    break
        except Exception:
            pass

        definition_url = f"{AZURE_DEVOPS_ORG_URL}/{project_name_for_def}/_build?definitionId={definition_id}"

        new_job = {
            'id': job_id,
            'definition_id': definition_id,
            'pipeline_name': get_pipeline_name_by_id(definition_id),
            'run_time': run_datetime.strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'Scheduled',
            'build_url': '#',
            'build_id': None,
            'project_name': project_name_for_def,
            'definition_url': definition_url,
            # Chain metadata
            'chain_queue': [],            # Bu iş başarıyla tamamlanınca sırayla tetiklenecek çocuk işlerin ID'leri
            'is_chained': False,          # Bu iş başka bir işin zinciri mi?
            'parent_job_id': None,        # Zincir ise ebeveyn iş ID'si
            'desktechID': desktech_id_raw,
            'runtime_parameters': { 'desktechID': desktech_id_raw }
        }
        scheduled_jobs.append(new_job)

        # Schedule the actual trigger
        scheduler.add_job(
            trigger_pipeline,
            'date',
            run_date=run_datetime,
            args=[definition_id, job_id, { 'desktechID': desktech_id_raw }],
            id=job_id
        )
        
        return jsonify({'status': 'success', 'job_id': job_id}), 200
    except (ValueError, KeyError) as e:
        return jsonify({'status': 'error', 'message': f'Invalid input: {e}'}), 400

@app.route('/jobs', methods=['GET'])
@login_required
def get_jobs():
    return jsonify(scheduled_jobs)

@app.route('/projects', methods=['GET'])
@login_required
def get_projects_endpoint():
    """Get all available projects."""
    projects = get_projects()
    return jsonify(projects)

@app.route('/pipelines', methods=['GET'])
@login_required
def get_pipelines_endpoint():
    """Get all available pipelines for a specific project."""
    project_name = request.args.get('project', AZURE_DEVOPS_PROJECT)
    pipelines = get_pipelines(project_name)
    return jsonify(pipelines)

@app.route('/refresh-pipelines', methods=['POST'])
@login_required
def refresh_pipelines():
    """Force refresh pipelines cache."""
    global pipelines_cache
    project_name = request.json.get('project') if request.json else AZURE_DEVOPS_PROJECT
    
    # Clear cache for specific project or all projects
    if project_name:
        if project_name in pipelines_cache['data']:
            del pipelines_cache['data'][project_name]
    else:
        pipelines_cache['data'] = {}
    
    pipelines_cache['last_updated'] = 0  # Force cache expiry
    pipelines = get_pipelines(project_name)
    return jsonify({'status': 'success', 'count': len(pipelines), 'project': project_name})

@app.route('/refresh-projects', methods=['POST'])
@login_required
def refresh_projects():
    """Force refresh projects cache."""
    global projects_cache
    projects_cache['last_updated'] = 0  # Force cache expiry
    projects = get_projects()
    return jsonify({'status': 'success', 'count': len(projects)})

@app.route('/cancel-job/<job_id>', methods=['POST'])
@login_required
def cancel_job(job_id):
    """Cancel a scheduled job."""
    global scheduled_jobs
    
    # Find the job in our list
    job_to_cancel = next((job for job in scheduled_jobs if job['id'] == job_id), None)
    
    if not job_to_cancel:
        return jsonify({'status': 'error', 'message': 'Job not found'}), 404
    
    try:
        # If it's a chained waiting job, it is not scheduled in APScheduler. Just detach from parent queue.
        if job_to_cancel.get('is_chained') and job_to_cancel.get('status') == 'Chained (Waiting)':
            parent_id = job_to_cancel.get('parent_job_id')
            if parent_id:
                parent_job = next((job for job in scheduled_jobs if job['id'] == parent_id), None)
                if parent_job and isinstance(parent_job.get('chain_queue'), list):
                    parent_job['chain_queue'] = [cid for cid in parent_job['chain_queue'] if cid != job_id]
            job_to_cancel['status'] = 'Cancelled'
            return jsonify({'status': 'success', 'message': 'Chained job cancelled successfully'})

        # For normal scheduled jobs, remove from scheduler
        if job_to_cancel.get('status') == 'Scheduled':
            scheduler.remove_job(job_id)
            job_to_cancel['status'] = 'Cancelled'
            return jsonify({'status': 'success', 'message': 'Job cancelled successfully'})

        return jsonify({'status': 'error', 'message': f"Job in status '{job_to_cancel.get('status')}' cannot be cancelled."}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error cancelling job: {str(e)}'}), 500

@app.route('/chain', methods=['POST'])
@login_required
def add_chain_job():
    """Add a chained pipeline to trigger after a parent scheduled job succeeds.
    Only allowed when parent job status is 'Scheduled'. Max 5 chained jobs.
    Expects JSON: { parent_job_id, definition_id, desktechID }
    """
    try:
        data = request.json or {}
        parent_job_id = data.get('parent_job_id')
        definition_id = int(data.get('definition_id'))
        desktech_id_raw = str(data.get('desktechID', '')).strip()
        # Validate desktechID
        if not re.fullmatch(r'^[1-9]\d*$', desktech_id_raw):
            return jsonify({'status': 'error', 'message': 'desktechID parametresi pozitif sayısal bir değer olmalıdır.'}), 400

        # Find parent job
        parent_job = next((job for job in scheduled_jobs if job['id'] == parent_job_id), None)
        if not parent_job:
            return jsonify({'status': 'error', 'message': 'Parent job not found'}), 404
        if parent_job.get('status') != 'Scheduled':
            return jsonify({'status': 'error', 'message': 'Chain only allowed for jobs in Scheduled status'}), 400

        # Enforce max 5 chained jobs
        if 'chain_queue' not in parent_job or not isinstance(parent_job['chain_queue'], list):
            parent_job['chain_queue'] = []
        if len(parent_job['chain_queue']) >= 5:
            return jsonify({'status': 'error', 'message': 'Maximum 5 chained pipelines allowed for a job'}), 400

        # Create child chained job (will be triggered upon parent success)
        from datetime import datetime as _dt
        child_job_id = f"{definition_id}_{_dt.now().strftime('%Y%m%d%H%M%S')}_ch"
        # Proje adını çöz ve definition linkini üret
        project_name_for_def = AZURE_DEVOPS_PROJECT
        try:
            for proj_name, pdata in pipelines_cache['data'].items():
                if any(int(p['id']) == int(definition_id) for p in pdata.get('pipelines', [])):
                    project_name_for_def = proj_name
                    break
        except Exception:
            pass
        definition_url = f"{AZURE_DEVOPS_ORG_URL}/{project_name_for_def}/_build?definitionId={definition_id}"

        child_job = {
            'id': child_job_id,
            'definition_id': definition_id,
            'pipeline_name': get_pipeline_name_by_id(definition_id),
            'run_time': 'On Parent Success',
            'status': 'Chained (Waiting)',
            'build_url': '#',
            'build_id': None,
            'project_name': project_name_for_def,
            'definition_url': definition_url,
            'is_chained': True,
            'parent_job_id': parent_job_id,
            'chain_queue': [],
            'desktechID': desktech_id_raw,
            'runtime_parameters': { 'desktechID': desktech_id_raw }
        }
        scheduled_jobs.append(child_job)
        parent_job['chain_queue'].append(child_job_id)

        return jsonify({'status': 'success', 'child_job_id': child_job_id, 'chain_count': len(parent_job['chain_queue'])}), 200
    except (ValueError, KeyError) as e:
        return jsonify({'status': 'error', 'message': f'Invalid input: {e}'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Unexpected error: {str(e)}'}), 500

# --- Login / Logout Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user_data = users.get(username)
        
        if user_data and user_data['password'] == password:
            user = User(username)
            login_user(user)
            flash('Giriş başarılı!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Geçersiz kullanıcı adı veya şifre.', 'error')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Başarıyla çıkış yaptınız.', 'success')
    return redirect(url_for('login'))

# Initialize cache on startup
load_projects_cache()
load_pipelines_cache()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
