"""
Kampanya ekonomisi — bir kampanyanin PARA KAYBETTIRIP kaybettirmedigini hesaplar.

NEDEN VAR: Komisyon geliri yok. Her satista kazanc yalnizca alis-satis farkindan
geliyor ve kargo bu farkin icinden cikiyor. "Ucretsiz kargo" gibi bir kampanya
bedava degildir: kargoyu biz odariz. Esik yanlis secilirse her siparis zarar
yazar ve bu, satis arttikca BUYUR.

Bu modul esigi TAHMIN ETMEZ, kataloktaki gercek fiyat ve maliyetlerden HESAPLAR.
Karar verirken en kotu durumu esas alir (tek urunluk siparis): sepette birden
fazla urun olursa kar zaten daha iyi olur, tersi olmaz.

Saf modul: DB/ag bilmez, urunler disaridan verilir -> izole test edilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Optional

# app.py'deki gercek degerlerle ayni (SHIPPING_COSTS["DE_DE"]["medium"], PACKAGING_COST, BROCHURE_COST)
DEFAULT_SHIPPING_EUR = 5.99
DEFAULT_PACKAGING_EUR = 1.70          # kutu/bant/kagit + brosur
# Bir siparisten en az bu kadar kar kalmali. Altina inersek is "cok calisip
# hicbir sey kazanmama" haline gelir; iade/hasar riskini de karsilamaz.
DEFAULT_MIN_PROFIT_EUR = 3.00

CANDIDATE_THRESHOLDS = (25, 30, 35, 40, 45, 50, 60, 70, 80)


@dataclass
class ProductMargin:
    product_id: str
    price: float
    cost: float
    margin: float          # kargo/paketleme oncesi brut fark


@dataclass
class CampaignEconomics:
    campaign: str
    affordable: bool
    threshold_eur: float
    shipping_eur: float
    packaging_eur: float
    min_profit_eur: float
    qualifying_products: int = 0
    worst_profit_after: Optional[float] = None    # kampanya sonrasi EN KOTU kar
    median_profit_after: Optional[float] = None
    losing_products: list[str] = field(default_factory=list)
    reason: str = ""
    recommendation: str = ""


def product_margins(products: list[dict], *, max_sane_price: float = 1000.0) -> list[ProductMargin]:
    """
    Urun basina brut fark = SATIS fiyati - toplam maliyet.

    ALAN ANLAMLARI (TATANGA products tablosu — karistirmasi kolay, dikkat):
      price                -> ALIS fiyati (kaynakta ne kadara duruyor)
      total_cost           -> alis + gelen kargo + paketleme + brosur
      estimated_sell_price -> bizim SATIS fiyatimiz
    Gelir olarak `price` kullanilirsa marj daima eksi cikar; dogru alan
    estimated_sell_price'dir.

    max_sane_price: kazimadan gelen bozuk kayitlari eler (kataloкta 499.000 EUR'luk
    kayit var — bunlar ortalamayi anlamsiz kilar).
    """
    out = []
    for p in products or []:
        revenue = p.get("estimated_sell_price") or 0
        cost = p.get("total_cost") or 0
        if revenue <= 0 or cost <= 0 or revenue > max_sane_price:
            continue
        out.append(ProductMargin(str(p.get("id", "")), float(revenue),
                                 float(cost), float(revenue) - float(cost)))
    return out


def evaluate_free_shipping(
    products: list[dict],
    *,
    threshold_eur: float,
    shipping_eur: float = DEFAULT_SHIPPING_EUR,
    packaging_eur: float = DEFAULT_PACKAGING_EUR,
    min_profit_eur: float = DEFAULT_MIN_PROFIT_EUR,
) -> CampaignEconomics:
    """
    "X EUR uzeri kargo bedava" kampanyasi bu katalogda surdurulebilir mi?

    En kotu durum varsayimi: musteri esigi ancak gecen TEK bir urun alir.
    Kalan kar = fiyat - alis maliyeti - paketleme - kargo.
    """
    result = CampaignEconomics(
        campaign=f"{threshold_eur:.0f} EUR uzeri ucretsiz kargo",
        affordable=False, threshold_eur=float(threshold_eur),
        shipping_eur=shipping_eur, packaging_eur=packaging_eur,
        min_profit_eur=min_profit_eur,
    )

    margins = product_margins(products)
    if not margins:
        result.reason = ("hesaplanamadi: hicbir urunde alis maliyeti (total_cost) yok — "
                         "maliyet bilinmeden kampanya karari verilemez")
        return result

    qualifying = [m for m in margins if m.price >= threshold_eur]
    result.qualifying_products = len(qualifying)
    if not qualifying:
        result.reason = (f"katalogda {threshold_eur:.0f} EUR ve uzeri urun yok — "
                         "kampanya hicbir siparise uygulanmaz")
        result.recommendation = "esigi dusurun ya da daha degerli urun kazinin"
        return result

    # total_cost paketlemeyi ZATEN iceriyor; kampanyanin EK maliyeti
    # yalnizca giden kargodur (normalde musteri oderdi).
    after = [m.margin - shipping_eur for m in qualifying]
    result.worst_profit_after = round(min(after), 2)
    result.median_profit_after = round(median(after), 2)
    result.losing_products = [m.product_id for m, kalan in zip(qualifying, after)
                              if kalan < min_profit_eur]

    result.affordable = result.worst_profit_after >= min_profit_eur
    if result.affordable:
        result.reason = (f"{len(qualifying)} urun uygun; en kotu durumda bile "
                         f"{result.worst_profit_after:.2f} EUR kar kaliyor "
                         f"(esik {min_profit_eur:.2f})")
        result.recommendation = "uygulanabilir"
    else:
        result.reason = (f"{len(result.losing_products)}/{len(qualifying)} uygun urunde "
                         f"kar {min_profit_eur:.2f} EUR esiginin altina duşuyor "
                         f"(en kotu: {result.worst_profit_after:.2f} EUR)")
        result.recommendation = ("esigi yukseltin ya da kampanyayi yalnizca marji "
                                 "yeterli urunlerle sinirlayin")
    return result


def recommend_free_shipping_threshold(
    products: list[dict],
    *,
    shipping_eur: float = DEFAULT_SHIPPING_EUR,
    packaging_eur: float = DEFAULT_PACKAGING_EUR,
    min_profit_eur: float = DEFAULT_MIN_PROFIT_EUR,
    candidates: tuple = CANDIDATE_THRESHOLDS,
) -> dict:
    """
    Kataloga bakarak EN DUSUK surdurulebilir esigi bulur.

    Esik dusuk olsun isteriz (daha cok siparis kapsar, daha cekici olur) ama
    zarar ettirmemeli. Bu yuzden adaylar kucukten buyuge taranir ve zarar
    ettirmeyen ILK esik onerilir.
    """
    denemeler = []
    onerilen = None
    for threshold in candidates:
        sonuc = evaluate_free_shipping(
            products, threshold_eur=threshold, shipping_eur=shipping_eur,
            packaging_eur=packaging_eur, min_profit_eur=min_profit_eur)
        denemeler.append(sonuc)
        if sonuc.affordable and onerilen is None:
            onerilen = sonuc

    return {
        "recommended": onerilen,
        "all": denemeler,
        "note": ("En kotu durum (tek urunluk siparis) esas alindi. Sepette birden "
                 "fazla urun olursa kar daha yuksek olur — bu hesap guvenli tarafta."),
    }
