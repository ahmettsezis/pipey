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

# Docker imajını build edin
docker build -t pipeline-scheduler:test .

# Container'ı çalıştırın
docker run -p 5000:5000 -e AZURE_DEVOPS_PAT="YOUR_PAT_HERE" pipeline-scheduler:test
```

Uygulama http://localhost:5000 adresinde çalışacaktır.

### 2. Kubernetes ile Deploy

```bash
# Azure DevOps PAT'ınızı secret olarak oluşturun
kubectl create secret generic azure-devops-pat --from-literal=pat='YOUR_PERSONAL_ACCESS_TOKEN'

# Deployment ve Service'i uygulayın
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml

# Port forwarding ile erişim sağlayın
kubectl port-forward service/pipeline-scheduler-service 8080:80
```

## Konfigürasyon

Aşağıdaki environment variable'ları kullanabilirsiniz:

- `AZURE_DEVOPS_ORG_URL`: Azure DevOps organizasyon URL'i 
- `AZURE_DEVOPS_PROJECT`: Proje adı 
- `AZURE_DEVOPS_PAT`: Personal Access Token (zorunlu)

## API Endpoints

- `GET /`: Ana sayfa
- `POST /schedule`: Pipeline zamanlama
- `GET /jobs`: Zamanlanmış işlerin listesi

## Kullanım

1. Web arayüzünde Pipeline Definition ID'sini girin (örn: 584)
2. Tetiklenmesini istediğiniz tarih ve saati seçin
3. "Schedule" butonuna tıklayın
4. İşin durumunu tabloda takip edin

## Geliştirme

```bash
# Bağımlılıkları kurun
pip install -r requirements.txt

# Development modunda çalıştırın
python app.py
```

## Teknolojiler

- **Backend**: Python, Flask, APScheduler
- **Frontend**: HTML, CSS, JavaScript
- **Containerization**: Docker
- **Orchestration**: Kubernetes
- **Web Server**: Gunicorn

If you want to learn more about creating good readme files then refer the following [guidelines](https://docs.microsoft.com/en-us/azure/devops/repos/git/create-a-readme?view=azure-devops). You can also seek inspiration from the below readme files:
- [ASP.NET Core](https://github.com/aspnet/Home)
- [Visual Studio Code](https://github.com/Microsoft/vscode)
- [Chakra Core](https://github.com/Microsoft/ChakraCore)