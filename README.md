# Azure DevOps Pipeline Scheduler

Bu proje, Azure DevOps pipeline'larını belirli tarih ve saatlerde tetiklemek ve durumlarını izlemek için geliştirilmiş bir web uygulamasıdır. Kubernetes üzerinde çalışacak şekilde tasarlanmıştır.

## Özellikler

- 📅 Pipeline'ları gelecekteki bir tarih ve saatte zamanlama
- 📊 Zamanlanmış işlerin durumunu gerçek zamanlı izleme
- 🔄 Otomatik durum güncellemeleri (her 5 saniyede bir)
- 🎨 Modern ve kullanıcı dostu web arayüzü
- 🐳 Docker ve Kubernetes desteği

## Gereksinimler

- Docker
- Kubernetes cluster (isteğe bağlı)
- Azure DevOps Personal Access Token (Build yetkisi ile)

## Hızlı Başlangıç

### 1. Docker ile Çalıştırma

```bash
# Projeyi klonlayın
git clone <repository-url>
cd pipey

# appsettings.Test.json dosyanızı gerçek değerlerle doldurun (aşağıdaki Konfigürasyon bölümüne bakın)

# Docker imajını build edin
docker build -t pipeline-scheduler:test .

# Konfigürasyon dosyasını read-only olarak container'a mount ederek çalıştırın
docker run -p 5000:5000 \
  -v "$(pwd)/appsettings.Test.json:/app/appsettings.Test.json:ro" \
  pipeline-scheduler:test
```

Uygulama http://localhost:5000 adresinde çalışacaktır.

### 2. Kubernetes ile Deploy

```bash
# appsettings.Test.json içeriğini hazırlayın (Konfigürasyon bölümündeki örneğe göre)

# JSON'u secret olarak oluşturun
kubectl create secret generic pipey-appsettings \
  --from-file=appsettings.Test.json=./appsettings.Test.json

# NOT: Deployment manifestinde bu secret'ı /app/appsettings.Test.json olarak mount etmeyi unutmayın
# Ardından manifestleri uygulayın
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml

# Port forwarding ile erişim sağlayın
kubectl port-forward service/pipeline-scheduler-service 8080:80
```

## Konfigürasyon

Uygulama sadece `appsettings.Test.json` dosyasından yapılandırma okur (ENV fallback kapalıdır).

Örnek JSON:

```json
{
  "azureDevOps": {
    "pat": "<PAT>",
    "AZURE_DEVOPS_ORG_URL": "https://dev.azure.com/<org>/<collectionOrOrg>",
    "AZURE_DEVOPS_PROJECT": "<ProjectName>"
  }
}
```

Notlar:
- Placeholder değerler (ör. `YourVariable`) geçersiz sayılır.
- PAT sağlanmışsa `AZURE_DEVOPS_ORG_URL` ve `AZURE_DEVOPS_PROJECT` zorunludur; eksikse uygulama başlangıçta hata ile durur (fail-fast).

## Kimlik Doğrulama

- Uygulama girişi zorunludur. Varsayılan olarak `app.py` içinde tanımlı geçici kullanıcılar kullanılır.
- Örnek kullanıcı: `admin / password`
- Production için kurumsal kimlik sağlayıcısı (OIDC/SAML) önerilir.

## API Endpoints

- `GET /` (login required): Ana sayfa
- `POST /schedule`: Pipeline zamanlama
- `GET /jobs`: Zamanlanmış işlerin listesi
- `GET /projects`: Projeler
- `GET /pipelines?project=<name>`: Belirli proje için pipeline listesi (prod filtresi aktif)
- `POST /refresh-projects`: Proje cache yenile
- `POST /refresh-pipelines`: Pipeline cache yenile (body: `{ project: "..." }`)
- `POST /cancel-job/<job_id>`: Zamanlanmış işi iptal et (Chained (Waiting) için de desteklenir)
- `POST /chain`: Scheduled parent job'a chained iş ekle (max 5)
- `GET /login`, `POST /login`: Giriş sayfası
- `GET /logout`: Çıkış

## Kullanım

1. Web arayüzünde önce projeyi, sonra pipeline'ı seçin.
   - Pipeline listesi yalnızca adında `prod` geçenleri gösterir (güvenlik filtresi).
2. "Scheduled Run Time" alanında en az 2 dakika sonrası olacak şekilde bir zaman seçin.
3. "Desktech ID" alanını pozitif tam sayı olarak doldurun.
4. "Schedule" ile işi planlayın. Liste 5 saniyede bir otomatik güncellenir.
5. İsteğe bağlı: Scheduled iş satırındaki "+Chain" ile en fazla 5 adet chained iş ekleyebilirsiniz.
   - Chained (Waiting) işler parent başarıyla tamamlandığında otomatik tetiklenir.
   - Chained (Waiting) işler ayrıca tek tek iptal edilebilir.

## Geliştirme

```bash
# Bağımlılıkları kurun
pip install -r requirements.txt

# Development modunda çalıştırın
python app.py  # appsettings.Test.json dosyanızın kökte mevcut olduğundan emin olun
```

## Teknolojiler

- **Backend**: Python, Flask, APScheduler
- **Frontend**: HTML, CSS, JavaScript
- **Containerization**: Docker
- **Orchestration**: Kubernetes
- **Web Server**: Gunicorn
