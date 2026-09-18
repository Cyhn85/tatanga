"""
Talep zekasi — NEYI kazayacagimizi kazimadan ONCE belirler.

BUGUNKU EKSIK: Kazima anahtar kelimeyi INSANDAN aliyor. "columbia herren jacke"
yazilir, sistem kazir. Ama o urunun ALICISI var mi, kimse olcmuyor. Sonuc:
katalog doluyor, satis olmuyor.

BU MODUL NE YAPAR: Bir aday urun/marka icin dort gercek sinyali birlestirip
"once bunu kaz" siralamasi uretir. Sinyallerin hicbiri tahmin degil, olcum:

  1. SATIS ORANI (sell-through) = satilan / (satilan + aktif)
     Yeniden satis piyasasinda talebin tek en guclu gostergesi. 100 aktif
     ilan + 5 satis = olu kategori. 20 aktif + 40 satis = talep var.

  2. SATIS HIZI (velocity) = son N gunde satilan adet / gun
     Oran yuksek ama hacim dusukse (3 aktif, 3 satis = %50) kategori kucuktur;
     hiz bunu ayirir.

  3. FIYAT ISTIKRARI = medyan / ortalama sapma
     Fiyatlar cok dagilmissa (10 EUR - 400 EUR) medyan yaniltir, kar hesabi
     guvenilmez olur. Dar bantli kategoriler ongorulebilirdir.

  4. REKABET = aktif ilan sayisi
     Talep yuksek + arz dusuk = "acilan kapi". Talep yuksek + arz cok yuksek
     = fiyat kirilir, marj erir.

ORNEKLEM KAPISI: outcome_learning ile ayni felsefe — az veriyle karar verilmez.
MIN_OBSERVATIONS altinda skor URETILMEZ, "veri yetersiz" denir.

Saf modul: ag/DB bilmez. Veriyi cagiran taraf toplar, burasi sadece OLCER.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Optional

# Bir aday hakkinda skor uretebilmek icin gereken en az ilan gozlemi
# (aktif + satilan toplami). Altinda kalirsa "bilmiyorum" denir.
MIN_OBSERVATIONS = 12

# Satis orani esikleri (yeniden satis piyasasi gercekleri)
STR_STRONG = 0.35      # %35+ satis orani: guclu talep
STR_WEAK = 0.12        # %12 alti: olu kategori

# Rekabet: bu kadar aktif ilanin ustunde arz bollugu var demektir
CROWDED_ACTIVE = 250

# Skor agirliklari — toplami 1.0. Satis orani en agir cunku talebin
# dogrudan olcumu; digerleri onu duzeltir.
W_SELL_THROUGH = 0.45
W_VELOCITY = 0.25
W_PRICE_STABILITY = 0.15
W_LOW_COMPETITION = 0.15


@dataclass
class MarketSample:
    """Bir aday icin toplanan HAM olcum. Tahmin yok, sayim var."""
    query: str
    platform: str = ""
    active_count: int = 0
    sold_count: int = 0
    window_days: int = 30
    sold_prices: list[float] = field(default_factory=list)
    active_prices: list[float] = field(default_factory=list)
    category: str = ""

    @property
    def observations(self) -> int:
        return self.active_count + self.sold_count


@dataclass
class DemandScore:
    query: str
    score: float = 0.0                 # 0-100, yalnizca confident ise anlamli
    confident: bool = False
    sell_through: float = 0.0
    velocity_per_day: float = 0.0
    median_sold_price: Optional[float] = None
    price_spread: Optional[float] = None    # 0=cok dar, 1+=cok dagilmis
    active_count: int = 0
    sold_count: int = 0
    verdict: str = "unknown"           # hunt | watch | avoid | unknown
    reasons: list[str] = field(default_factory=list)


def _price_spread(prices: list[float]) -> Optional[float]:
    """Fiyat dagilimi: ceyrekler arasi mesafe / medyan. Medyan 0 ise None."""
    temiz = [p for p in prices if p and p > 0]
    if len(temiz) < 4:
        return None
    temiz.sort()
    medyan = statistics.median(temiz)
    if medyan <= 0:
        return None
    q1 = temiz[len(temiz) // 4]
    q3 = temiz[(3 * len(temiz)) // 4]
    return round((q3 - q1) / medyan, 3)


def score_sample(sample: MarketSample) -> DemandScore:
    """
    Ham olcumu 0-100 talep skoruna cevirir.
    Yeterli gozlem yoksa skor URETMEZ — sifir dondurup "iyi degil" demek,
    "bilmiyorum" ile "kotu"yu karistirmak olurdu.
    """
    d = DemandScore(
        query=sample.query,
        active_count=sample.active_count,
        sold_count=sample.sold_count,
    )

    if sample.observations < MIN_OBSERVATIONS:
        d.verdict = "unknown"
        d.reasons.append(
            f"yetersiz gozlem ({sample.observations}/{MIN_OBSERVATIONS}) — "
            "bu kategori hakkinda konusmak icin erken")
        return d

    d.confident = True

    # 1) Satis orani
    toplam = sample.sold_count + sample.active_count
    d.sell_through = round(sample.sold_count / toplam, 3) if toplam else 0.0
    str_puan = min(d.sell_through / STR_STRONG, 1.0)

    # 2) Satis hizi (gun basina). log olcegi: 1/gun ile 10/gun arasi fark,
    # 0 ile 1 arasindaki farktan daha az onemlidir.
    gun = max(sample.window_days, 1)
    d.velocity_per_day = round(sample.sold_count / gun, 3)
    hiz_puan = min(math.log1p(d.velocity_per_day * 7) / math.log1p(20), 1.0)

    # 3) Fiyat istikrari — dar bant iyi
    d.price_spread = _price_spread(sample.sold_prices or sample.active_prices)
    if d.price_spread is None:
        istikrar_puan = 0.5          # bilinmiyor -> notr, odul de ceza da yok
        d.reasons.append("fiyat dagilimi olculemedi (yetersiz fiyat verisi)")
    else:
        # spread 0.3 ve alti cok iyi, 1.5 ustu cok kotu
        istikrar_puan = max(0.0, min(1.0, (1.5 - d.price_spread) / 1.2))

    # 4) Rekabet — az arz iyi
    rekabet_puan = max(0.0, 1.0 - (sample.active_count / CROWDED_ACTIVE))

    d.score = round(100 * (
        W_SELL_THROUGH * str_puan
        + W_VELOCITY * hiz_puan
        + W_PRICE_STABILITY * istikrar_puan
        + W_LOW_COMPETITION * rekabet_puan
    ), 1)

    fiyatlar = [p for p in (sample.sold_prices or []) if p and p > 0]
    if fiyatlar:
        d.median_sold_price = round(statistics.median(fiyatlar), 2)

    # --- Karar ---
    if d.sell_through < STR_WEAK:
        d.verdict = "avoid"
        d.reasons.append(
            f"satis orani %{d.sell_through*100:.0f} — {sample.active_count} aktif ilana "
            f"karsilik {sample.sold_count} satis; talep yok")
    elif d.sell_through >= STR_STRONG and d.score >= 55:
        d.verdict = "hunt"
        d.reasons.append(
            f"satis orani %{d.sell_through*100:.0f}, gunde {d.velocity_per_day} satis, "
            f"{sample.active_count} rakip ilan")
    else:
        d.verdict = "watch"
        d.reasons.append(
            f"satis orani %{d.sell_through*100:.0f} — ne guclu ne olu; "
            "daha fazla gozlemle netlesir")

    if sample.active_count > CROWDED_ACTIVE:
        d.reasons.append(
            f"arz bol ({sample.active_count} aktif ilan) — fiyat kirilma riski")
    if d.price_spread is not None and d.price_spread > 1.2:
        d.reasons.append(
            f"fiyatlar cok dagilmis (yayilim {d.price_spread}) — kar hesabi guvenilmez")
    return d


def rank_candidates(samples: list[MarketSample], *, limit: int = 20) -> list[DemandScore]:
    """
    Adaylari kazima onceligine gore sirala.

    'unknown' olanlar ELENMEZ — listenin sonuna konur. Cunku veri yoklugu
    "kotu firsat" demek degil; kesif kazimasiyla veri toplanmasi gerekir.
    Sistemi sadece bildigi seylere kilitlemek yeni kapilari kapatir.
    """
    skorlar = [score_sample(s) for s in samples]
    oncelik = {"hunt": 0, "watch": 1, "unknown": 2, "avoid": 3}
    skorlar.sort(key=lambda d: (oncelik.get(d.verdict, 9), -d.score))
    return skorlar[:limit]


def explain(score: DemandScore) -> str:
    """Insan-okunur tek satirlik gerekce (panelde ve logda gosterilir)."""
    if not score.confident:
        return f"{score.query}: {score.reasons[0] if score.reasons else 'veri yok'}"
    return (f"{score.query}: {score.verdict.upper()} (skor {score.score}) — "
            + "; ".join(score.reasons))
