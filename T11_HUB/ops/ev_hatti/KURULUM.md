# Ev hatti: Vinted gozlemcisini ev internetinden calistirmak

**Durum (2026-10-13):** yol hazir, KURULMADI. Gozlemcide destek var ama `config.json` icinde `"mod": "kapali"`.

## Neden
Sunucu IP'si (Hetzner, veri merkezi) Vinted'de gidip gelen sekilde engelleniyor (10-12 Ekim: 7 pazarin hepsinde 403).
Ev internetinin (Vodafone kablo) IP'si bir ev kullanicisi IP'si: engellenme olasiligi cok daha dusuk.

## Kural (kullanici karari 2026-10-13)
- Vinted hesabi ARTIK yalnizca telefondan, MOBIL VERIYLE (WiFi kapali) kullanilir.
- Bu PC'de / ev WiFi'sinde Vinted hesabina GIRIS YAPILMAZ (PC'deki oturumlar kapatildi).
- Gozlemci ev hattinda da giris yapmaz, hesap kullanmaz; yalnizca herkese acik sayfalari okur.

## Nasil calisir
```
Sunucu (gozlemci, tum veri ve mantik)  --istek-->  127.0.0.1:1080 (SOCKS)  ==SSH tuneli==>  PC  -->  Vinted
```
PC yalnizca cikis kapisidir. Veri sunucuda kalir, PC arsivi her zamanki gibi cek.py ile ceker.

## Kurulum adimlari (kullanici "kur" dediginde)
1. Tuneli elle bir kez dene (PowerShell):
   ```
   powershell -ExecutionPolicy Bypass -File C:\Users\cyhnsrgc\Desktop\tatanga\T11_HUB\ops\ev_hatti\ev_hatti.ps1
   ```
2. Sunucuda tunelin acik oldugunu ve cikisin ev IP'si oldugunu dogrula:
   ```
   ssh root@195.201.146.224 "curl -s --socks5-hostname 127.0.0.1:1080 https://api.ipify.org"
   ```
   Beklenen: ev IP'si (Vodafone, 31.16.x.x), sunucu IP'si (195.201.146.224) DEGIL.
3. Gozlemcide ev hattini ac: `/opt/tatanga-observer/config.json` icinde `"ev_hatti": {"mod": "tercih", ...}`,
   sonra `systemctl restart tatanga-observer`.
4. Saglama: `cd /opt/tatanga-observer && ./venv/bin/python saglama.py` -> **T16** ev / sunucu istek dagilimini gosterir.
5. Kalici yap: Gorev Zamanlayici'da "TATANGA Ev Hatti" gorevi (oturum acilinca, gizli pencere, ev_hatti.ps1).

## Modlar
- `kapali`: yalnizca sunucu IP (bugunku davranis).
- `tercih`: tunel varsa ev, yoksa sunucu. PC kapaliyken gozlemci yavas da olsa calisir. **Onerilen.**
- `zorunlu`: tunel yoksa bekler (sunucu IP'si hic kullanilmaz).

Hat degisince gozlemci, onceki IP'ye ait pazar beklemelerini ve genel duraklamayi kaldirir (sunucu IP'sinin
cezasi ev hattina tasinmaz). Duraklama sirasinda en gec 5 dakikada bir tuneli yoklar.

## IP yenileme hakkinda
Vodafone kablo hatlarinda modemi yeniden baslatmak cogu zaman YENI IP VERMEZ (IP modemin donanim adresine bagli).
Bu yuzden "5-6 saatte bir fis cekme" plani bu hatta guvenilir degil; dusuk ve insan gibi hiz ana korumadir.
Ev hatti acildiktan sonra ilk hafta gunluk butce 2500'de tutulur, engel gorulmezse kademeli artirilir.
