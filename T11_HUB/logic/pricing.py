"""
cssberlin fiyatlama: yuvarlama kurali + kendi sitemiz icin maliyet modeli.

NEDEN AYRI MODUL:
app.py'deki analyze_profit() HARICI platformlar (eBay, Vinted...) icin
hesap yapiyor — onlarin komisyonlarini kullaniyor ve `base_cost * 1.40`
gibi carpanlardan `183.31` gibi kusuratli sayilar uretiyor. Kendi sitemizde
platform komisyonu YOK, onun yerine Stripe odeme komisyonu ve kargo
politikamiz var. Ve vitrindeki fiyat kusuratli olmamali.

Kaynak: websitenew/src/config/shipping-policy.ts
  - 50 EUR ustu: kargo bedava (musteri 0 oder, biz 5.99 odemis oluruz)
  - 50 EUR alti: musteri 4.99 oder, biz 5.99 oderiz -> net 1.00 bize kalir
"""

from __future__ import annotations
from dataclasses import dataclass, asdict

# --- Sabitler (app.py ile ayni degerler, tek kaynak burada tutulur) ---
PACKAGING_COST = 1.50          # kutu, bant, kagit
BROCHURE_COST = 0.20           # CSS Berlin brosuru
OUTBOUND_SHIPPING_COST = 5.99  # DE ici gonderim, bizim odedigimiz (medium)

# Site kargo politikasi (shipping-policy.ts ile birebir)
FREE_SHIPPING_THRESHOLD_EUR = 50.0
DEFAULT_SHIPPING_FEE_EUR = 4.99

# Stripe EU kart: %1.4 + 0.25 EUR
PAYMENT_FEE_RATE = 0.014
PAYMENT_FEE_FIXED = 0.25


def yuvarla(fiyat: float) -> float:
    """Vitrin fiyatina yuvarla — Alman perakende geleneği: hep ,90 ile biter.

    Kusuratli `183.31` yerine `189.90` gosterir. Her zaman YUKARI yuvarlar,
    boylece hesaplanan minimum fiyatin altina asla dusmez.

        12.34  -> 12.90
        47.10  -> 49.90
        183.31 -> 189.90
        213.80 -> 219.90
    """
    if fiyat <= 0:
        return 0.0

    import math
    # .90 ekleneceginden, tam sayi kismi en az bu olmali
    n = math.ceil(round(fiyat - 0.90, 6))
    if n < 1:
        return 0.90

    # 20 EUR altinda her tam sayi bir basamak (8.90, 12.90, 16.90)
    # 20 EUR ustunde 5'lik merdiven: ...24.90, 29.90, ..., 184.90, 189.90
    # Boylece yukari yuvarlama hicbir zaman 5 EUR'dan fazla siçramaz.
    if fiyat < 20:
        return round(n + 0.90, 2)
    while n % 5 != 4:
        n += 1
    return round(n + 0.90, 2)


@dataclass
class Maliyet:
    """Bir urunun bize maliyeti ve verilen satis fiyatindaki kari."""
    alis: float                 # urun alis fiyati (EUR)
    gelen_kargo: float          # kaynak ulkeden bize
    paketleme: float            # kutu + brosur
    sabit_maliyet: float        # alis + gelen_kargo + paketleme (satis fiyatindan bagimsiz)

    satis_fiyati: float         # vitrin fiyati
    giden_kargo_net: float      # bizim ustlendigimiz gonderim (musteri katkisi dusulmus)
    odeme_komisyonu: float      # Stripe
    toplam_maliyet: float       # sabit + giden_kargo_net + odeme_komisyonu
    kar: float                  # satis_fiyati - toplam_maliyet
    marj_yuzde: float           # kar / satis_fiyati * 100

    def dict(self) -> dict:
        return {k: (round(v, 2) if isinstance(v, float) else v)
                for k, v in asdict(self).items()}


def sabit_maliyet(alis: float, gelen_kargo: float) -> float:
    """Satis fiyatindan bagimsiz maliyet: alis + gelen kargo + paketleme."""
    return round(alis + gelen_kargo + PACKAGING_COST + BROCHURE_COST, 2)


def hesapla(alis: float, gelen_kargo: float, satis_fiyati: float) -> Maliyet:
    """Verilen satis fiyati icin tam maliyet ve kar dokumunu cikar."""
    paketleme = PACKAGING_COST + BROCHURE_COST
    sabit = sabit_maliyet(alis, gelen_kargo)

    # Giden kargo: 50 EUR ustunde musteri odemez, tamami bize kalir.
    if satis_fiyati >= FREE_SHIPPING_THRESHOLD_EUR:
        giden_net = OUTBOUND_SHIPPING_COST
    else:
        giden_net = max(0.0, OUTBOUND_SHIPPING_COST - DEFAULT_SHIPPING_FEE_EUR)

    odeme = round(satis_fiyati * PAYMENT_FEE_RATE + PAYMENT_FEE_FIXED, 2)
    toplam = round(sabit + giden_net + odeme, 2)
    kar = round(satis_fiyati - toplam, 2)
    marj = round(kar / satis_fiyati * 100, 1) if satis_fiyati > 0 else 0.0

    return Maliyet(
        alis=round(alis, 2), gelen_kargo=round(gelen_kargo, 2),
        paketleme=round(paketleme, 2), sabit_maliyet=sabit,
        satis_fiyati=round(satis_fiyati, 2), giden_kargo_net=round(giden_net, 2),
        odeme_komisyonu=odeme, toplam_maliyet=toplam, kar=kar, marj_yuzde=marj,
    )


def onerilen_fiyat(alis: float, gelen_kargo: float, hedef_marj: float = 0.35) -> float:
    """Hedef marja ulasan en dusuk YUVARLANMIS vitrin fiyati.

    hedef_marj satis fiyatina orandir (0.35 = fiyatin %35'i kar).
    Yuvarlama yukari oldugu icin gercek marj hep hedefin ustunde cikar.
    """
    sabit = sabit_maliyet(alis, gelen_kargo)
    # kar = satis - sabit - giden - odeme;  odeme = satis*r + f
    # marj hedefi: kar >= satis * m
    # satis - sabit - giden - satis*r - f >= satis*m
    # satis * (1 - r - m) >= sabit + giden + f
    payda = 1 - PAYMENT_FEE_RATE - hedef_marj
    if payda <= 0:
        return 0.0

    # giden kargo esige bagli — once ucuz varsayimla dene, esik asilirsa duzelt
    for giden in (max(0.0, OUTBOUND_SHIPPING_COST - DEFAULT_SHIPPING_FEE_EUR),
                  OUTBOUND_SHIPPING_COST):
        ham = (sabit + giden + PAYMENT_FEE_FIXED) / payda
        fiyat = yuvarla(ham)
        # varsayim tutarli mi: ucuz kargo varsayimi ancak esik altinda gecerli
        if giden < OUTBOUND_SHIPPING_COST and fiyat < FREE_SHIPPING_THRESHOLD_EUR:
            return fiyat
        if giden == OUTBOUND_SHIPPING_COST:
            return fiyat
    return yuvarla(ham)
