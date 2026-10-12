# Kleinanzeigen sayfa krokisi (2026-10-12, tarayicida F12 ile cikarildi)

Rol: ALIS tarafi. Satis olcumu burada yapilmaz.

## Erisim
- Sunucudan (Hetzner) curl_cffi chrome ile 200 (liste ~720 KB, ilan ~236 KB). Vinted engeli burada yok.
- robots.txt: `/s-...` (arama) ve `/s-anzeige/...` (ilan) YASAK DEGIL. Yasak: /m-*.html (hesap islemleri), /messages/, /checkout.html, /zur-merkliste.html -> bunlara asla gidilmez.
- Cerez: "Pay or OK" duvari (Alle akzeptieren / Pur abonelik). Ilan HTML'i duvarin arkasinda zaten yuklu; toplayici cerez onayi VERMEZ, duvara tiklamaz.
- "Suche speichern", "Folgen", merkliste: giris ister -> kullanilmaz (login yok kurali).

## Arama URL'si
`/s-<kategori-slug>/[seite:N/]<anahtar>/k0c<kategori>[+filtre+filtre]`
- Kategoriler: c160 Herrenbekleidung, c154 Damenbekleidung, c158 Herrenschuhe, c159 Damenschuhe (ust: c153 Mode & Beauty; c156 Taschen, c157 Uhren sonra).
- Kondisyon (bizim ilk 3): `+global.zustand:new_with_tag,new,like_new` (virgulle birlesir; dogrulandi: Carhartt 7.337 -> 5.948).
  Diger degerler: ok = Gut, alright = In Ordnung (alinmaz).
- Tur: `+kleidung_herren.art_s:jacken_maentel|hosen|pullover|shirts|hemden|jeans|...` (kategori yolu da eklenir: `/s-kleidung-herren/jacken_maentel/...`)
- Beden: `+kleidung_herren.groesse_s:s|m|l|xl|...`; Kargo: `+kleidung_herren.versand_s:ja|nein` (nein = Nur Abholung)
- Satici: `/anbieter:privat/` veya `/anbieter:gewerblich/` yol parcasi; Direkt kaufen: `/direktkaufen:aktiv/`
- Siralama varsayilan: SORTING_DATE (en yeni once). Sayfa basina 25 ilan.

## Liste karti
- `#srchrslt-adtable > li[data-clickable=card] > article[data-adid][data-href]`
- Kart icinde `<script type=application/ld+json>`: title, description (kisa), contentUrl (gorsel; SAKLANMAZ).
- Metin sirasi: gorsel sayisi | PLZ + yer | tarih ("Heute, 10:34" / "Gestern" / gg.aa.yyyy) | baslik | aciklama | fiyat ("100 €", "VB", "Zu verschenken") | beden | rozetler ("Direkt kaufen", "Versand möglich", "Nur Abholung")
- Reklam satirlari: ilan olmayan bos `li` (31 li'den 5'i) -> atlanir.

## TUZAKLAR
1. TOP ilan (mor "TOP" rozeti, `svg path[fill="#5A33AE"]`): tarih YOK, sira disi, sayfalar arasi tekrar eder -> zaman cizgisini bozmasin: tarih ilan sayfasindan alinir, data-adid ile tekillestirilir.
2. Fiyat "VB" (pazarlik) / "Zu verschenken" / bos -> sayisal fiyat yoksa fiyat istatistigine girmez.
3. Aciklamada kusur ("Stofffehler", "Fleck", "Loch") olsa bile Zustand "Sehr Gut" secilmis olabilir -> kusur kelimeleri isaretlenir (eleme degil, kural: isaretle).
4. Toplu ilan ("Konvolut", "Paket", "Set") ve aksesuar karisimi (Cap, Mütze) -> tip katmani ayirir.
5. Gewerblich (ticari) saticilar fiyatlari farkli -> satici tipi ayri alan.

## Ilan sayfasi `/s-anzeige/<slug>/<adid>-<kat>-<yer>`
- `#viewad-title`, `#viewad-price` ("100 €", JS'de `viewAdPrice = 100.00`), `#viewad-locality` (PLZ - eyalet - sehir)
- `#viewad-details li`: Art, Marke, Größe, Farbe, Zustand (yapilandirilmis!)
- `#viewad-extra-info`: yayin tarihi (gg.aa.yyyy)
- Kargo: `.boxedarticle--details--shipping` ("+ Versand ab 0,99 €")
- Satici: "Privater Nutzer"/"Gewerblicher Nutzer", "Aktiv seit gg.aa.yyyy", "TOP Zufriedenheit" (guven isareti; yeni hesap = risk isareti)
- Silinen ilan: kontrol edilecek (404 / yonlendirme) -> satildi/silindi AYRIMI YAPILAMAZ; Kleinanzeigen'de satis olcumu yok, yalnizca "ilan suresi" olculur.
