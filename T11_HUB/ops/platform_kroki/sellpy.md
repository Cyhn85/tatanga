# Sellpy sayfa krokisi (2026-10-12, tarayicida incelendi)

Rol: ALIS tarafi (kullanici beklentisi: en dusuk fiyatlar). Sabit fiyat, profesyonel fotograf, 30 gun iade hakki.

## Yapi
- Tamamen JavaScript (SPA). Ham HTML 5 KB iskelet: duz HTTP isteginde ilan verisi YOK (arama da ilan sayfasi da).
- Arama: Algolia (vxbnwnp8xq-dsn.algolia.net, i490mw2atb-dsn.algolia.net) - tarayici kendi gomulu salt-okuma anahtariyla sorar.
- Ilan detayi: Parse GraphQL (sellpy-parse-prod.herokuapp.com/graphql?_=buyerPDPQuery).
- Tarayicida render edilen arama sayfasi schema.org Product JSON-LD uretir: name ("Marke, Art, Größe: X"), brand, color, material, offers.price/priceCurrency/availability. itemCondition genel (UsedCondition) -> kondisyon derecesi ilan sayfasindan.
- URL: /search?query=<anahtar>, ilan /item/<id>. Filtre tiklamasi URL'yi degistirmiyor (durum JS icinde).

## Kondisyon (ilan sayfasi + filtre)
- Dereceler: Neuwertig > Sehr gut > Gut > Akzeptabel ("ausgiebig benutzt, Mängel"). Carhartt: Neuwertig 137, Sehr gut 1.486, Gut 3.701.
- BIZ: yalnizca Neuwertig (+ varsa Neu mit Etikett) ve Sehr gut. Gut/Akzeptabel alinmaz.
- Kusur etiketi ayrica yaziliyor (ornek: "Schmutzig (Ganzer Artikel)") -> risk isareti icin altin deger.

## Maliyet bilgisi (ilan sayfasindan)
- Versand ab 5,99 EUR; ilk sipariste 30 EUR ustu ucretsiz; Rueckversand ab 4,49 EUR; 30 Tage Rueckgaberecht.

## robots.txt
- Allow: /. Yasak: /sale/*, /order/*, /payment/*, /claims/*, /store/*/*/search*, favori listeleri. /search ve /item serbest.

## Toplama secenekleri (karar bekliyor)
1. Gercek tarayici (Playwright/Chromium, insansi gezinme): sitenin gosterdigini okur; agir (~300 MB RAM), yavas, en guvenli yorum.
2. Sitenin kendi Algolia aramasini dogrudan sormak: hizli, kucuk veri; ama arayuzu atlamak kullanim sartlari acisindan gri alan.
-> Oneri: 1 (insansi, dusuk hiz).

## Tuzaklar
- Cerez/GTM/Facebook izleyicileri: toplayici reddeder/yuklemez.
- "Schnelle Lieferung" rozeti, influencer magazalari, "Sellpy Edits" vitrinleri: arama sonucu degil -> atlanir.
- Ayni urun (2mXS7xrdIq) kartta 3 link olarak tekrarlaniyor -> id ile tekillestirilir.
