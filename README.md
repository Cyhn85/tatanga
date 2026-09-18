# TATANGA - 2. El Urun Arbitraj ve Satis Otomasyon Sistemi

## Vizyon
Dusuk fiyatli urun bul -> Al -> Kar koyup sat

## Sistem Yapisi

```
TATANGA/
|
+-- T1_TREND_HUNTER/      # Trend urun kesfi
+-- T2_PRICE_SCANNER/     # Siteler arasi fiyat tarama
+-- T3_ARBITRAGE_ENGINE/  # Arbitraj firsatlari
+-- T4_STOCK_MANAGER/     # Stoklu urun yonetimi
+-- T5_IMAGE_PROCESSOR/   # Resim isleme
+-- T6_LISTING_ENGINE/    # Ilan olusturma & yukleme
+-- T7_STORE_MONITOR/     # Magaza takibi
+-- T8_MESSAGE_CENTER/    # Mesajlasma & pazarlik
+-- T9_SHIPPING_HUB/      # Kargo yonetimi
+-- T10_ANALYTICS/        # Analitik & raporlar
|
+-- shared/               # Ortak dosyalar
+-- telegram_bot/         # Telegram bot
+-- activepieces/         # Otomasyon akislari
+-- logs/                 # Genel loglar
```

## Platformlar

- **Vinted.de** - 2 hesap
- **Kleinanzeigen.de** - 3 hesap
- **eBay.de** - css_berlin (50 puan)
- **Willhaben.at** - Gewerblich hesap
- **cssberlin.de** - Kendi web sitemiz

## Kargo Firmalari

- DHL
- Hermes
- DPD
- GLS

## Kurulum

```bash
cd TATANGA
pip install -r requirements.txt
```

## Calistirma

```bash
python main.py
```

## Telegram Kanallari

- #trendler - Trend urun bildirimleri
- #arbitraj - Arbitraj firsatlari
- #listeleme - Yeni ilan bildirimleri
- #satislar - Satis bildirimleri
- #mesajlar - Magaza mesajlari
- #kargo - Kargo takip
- #sistem - Hata/uyari
- #raporlar - Gunluk raporlar

## Hetzner Sunucu

- IP: 195.201.146.224
- Lokasyon: Nurnberg

## Lokasyon

- Berlin, 13593, Deutschland

---

**TATANGA** - Akilli 2. El Ticaret Sistemi
