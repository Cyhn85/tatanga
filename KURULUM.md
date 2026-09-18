# TATANGA — Kurulum ve Proje Haritası

TATANGA, ikinci el ürünleri (ağırlıklı Vinted) kazıyan, kârlılığını hesaplayan, görsellerini işleyen,
SEO metni üreten ve uygun ürünleri cssberlin.de'ye yayınlayan bir sistemdir.
**Asıl çalışan sistem `T11_HUB/` (Komuta Merkezi, http://localhost:8501).** Diğer klasörler
(T1–T10, `shared`, `telegram_bot`, `videocu_v1`, `activepieces`) önceki modüller, yardımcılar ve arşivdir.

## Parçalar
| Parça | Nereden | Nereye |
|---|---|---|
| Kod | Bu repo (`git clone`) | örn. `C:\tatanga` |
| Veri (veritabanı `hub.db`, görseller, token'lar, ses modelleri) | `TATANGA_data.zip` | `C:\tatanga\T11_HUB\data\` |
| Video çıktıları (isteğe bağlı, test videoları) | `TATANGA_video_ciktilari.zip` | `C:\tatanga\videocu_v1\output\` |
| Gizli ayarlar | `.env` + 4 dosya (Ceyhun'dan Drive ile) | `.env` → `C:\tatanga\T11_HUB\.env`; `credentials.py` → `shared\config\`; `config.py`, `QUICKSTART.md`, `TELEGRAM_BOT_GUIDE.md` → `videocu_v1\` |

## Kurulum (Windows, PowerShell)
1. Gerekenler: **Python 3.11**, **Git**, **Google Chrome**, video için **ffmpeg** (`winget install ffmpeg`).
2. Kodu al: `git clone <repo-linki> C:\tatanga`
3. `TATANGA_data.zip` → `C:\tatanga\T11_HUB\data\` içine aç (klasör yapısı: `data\hub.db` ...).
4. `.env` dosyasını `C:\tatanga\T11_HUB\.env` olarak koy (şablon: `T11_HUB\.env.example`).
5. Sanal ortam ve paketler:
   ```
   cd C:\tatanga
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r T11_HUB\requirements.txt
   ```
6. Başlat: `T11_HUB\start_hub.bat` → tarayıcıda http://localhost:8501
   - İlk çalıştırmada rembg ~170 MB model indirir (normal).
   - Çıktılar: `Masaüstü\CSS_Berlin_Output\`

## Canlı yayın (cssberlin.de)
Yayın köprüsü hazır: `.env` içindeki `CSSBERLIN_API_URL` (`https://cssberlin.de/api/products/import`)
ve `CSSBERLIN_API_KEY` dolu olduğu sürece arayüzdeki "Yayınla" butonu ürünü doğrudan siteye gönderir.
Bu satırlara dokunmayın.
- Site aynı kaynak linkinden gelen ürünü tekrar oluşturmaz, mevcut ilanı günceller.
- Her bilgisayarın kendi `hub.db`'si vardır; ürünler aşağıdaki senkronla ortak havuzda birleşir, hepsi aynı siteye yayınlanır.
- YouTube/sosyal medya token'ları Ceyhun'un hesabına bağlıdır.

## Ürün senkronu (iki bilgisayar, tek havuz)
Her Hub 10 dakikada bir kendi ürünlerini sunucudaki ortak havuza gönderir, diğer Hub'ın ürünlerini çeker.
- `.env`'e iki satır: `TATANGA_SYNC_URL=https://cssberlin.de/tatanga-sync` ve `TATANGA_SYNC_KEY=<sana özel anahtar>`. Anahtar kişiye özeldir, paylaşılmaz.
- Senkron **yayın yapmaz**. Karşıdan gelen ürünler `synced` durumuyla görünür; bu makinede otomatik yayın, fiyat indirimi, siteden kaldırma veya sosyal paylaşım tetiklemez.
- Tekilleştirme kaynak linkine göre: bir linki havuza ilk gönderen o ürünün sahibidir, sadece sahibi güncelleyebilir.
- Elle hemen çalıştırmak için: `cd C:\tatanga\T11_HUB` ve `..\venv\Scripts\python -m core.product_sync`
- İki bilgisayarda zaten ortak olan eski ürünlerde her makine kendi kopyasını korur; yeni kazınan ürünler iki yönde akar.

## Proje haritası (T11_HUB)
- `app.py` — FastAPI uygulaması, tüm API uçları ve arayüz (port 8501)
- `core/` — state machine, event bus, manager (deterministik orkestrasyon)
- `logic/` — arbitraj motoru, ürün eşleştirme, marka kataloğu, kargo optimizasyonu, kalite filtresi, kategori planı, talep istatistikleri, kampanya motoru
- `scrapers/` — platform kazıyıcıları (Selenium + undetected-chromedriver)
- `processors/` — SEO (Groq LLM veya şablon), arka plan kaldırma (rembg), yayın
- `media/` — görsel işleme, video oluşturma, ses (Piper)
- `social/` — YouTube entegrasyonu
- `data/hub.db` — SQLite (aiosqlite, tek yazar)
- `data/scheduler_settings.json` — zamanlayıcı; takip listesi 10 dk'da bir kontrol edilir

## Bilinen sorunlar
- eBay kazıyıcısı 403 ile engelleniyor; Sellpy 0 sonuç dönüyor (site yapısı değişmiş olabilir).
- Groq ücretsiz kotası dolunca SEO yavaşlar → `POST /api/products/bulk-seo {"template": true}` (şablon SEO, API'siz).
- Eşzamanlı BG + SEO + kaynak kontrolü SQLite kilit çakışması yaratabilir (3 deneme mantığı var).

## GPT ile çalışırken
GPT'ye her seferinde tek adım yaptırın ve her komutun çıktısını yapıştırıp kontrol ettirin.
Projeyi anlatırken bu dosyayı ve ardından `tatanga mimarisi.txt`, `sistem tasarim.txt`, `T11_HUB/app.py` dosyalarını verin.
