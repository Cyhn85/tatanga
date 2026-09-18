"""
Talep istatistigi — seyrek veriyle DOGRU karar vermenin matematigi.

PROBLEM: "Herren > Jacken > Columbia > Beden L > 50-100 EUR" hucresinde 3
gozlem var. Ham oran 2/3 = %67 der. Ayni oran 200/300 hucresinde de %67.
Ikisine ayni muameleyi yapmak, ilkinde tesadufu gercek saniyor demektir.
Arbitrajda bu dogrudan para kaybi.

UC ARAC, UC AYRI SORU ICIN:

1) WILSON GUVEN ARALIGI — "bu oran ne kadar guvenilir?"
   Normal yaklasim (p ± 1.96·sqrt(p(1-p)/n)) kucuk n'de ve p 0/1'e yakinken
   COKER: 0/5 gozlemde aralik [0,0] cikar, yani "kesinlikle hic satmaz" der.
   Wilson bu iki durumda da dogru davranir; alt sinirini kullanmak
   "kotumser ama durust" bir siralama verir. Reddit/Amazon gibi sistemlerin
   "en iyi yorum" siralamasi da bu yontemle yapilir.

2) THOMPSON ORNEKLEMESI (Beta-Bernoulli) — "siradaki kazimayi nereye?"
   Sadece en yuksek orana gidersek (sömürü) hic denemedigimiz kategorileri
   asla ogrenemeyiz. Sadece rastgele gezersek (kesif) para kaybederiz.
   Thompson her kategorinin Beta(a,b) posterior'undan bir ORNEK cekip en
   yuksegini secer: belirsiz kategoriler dogal olarak ara sira secilir,
   veri biriktikce secim keskinlesir. Epsilon-greedy'den ustundur cunku
   belirsizligi miktarina gore odullendirir, sabit bir oranla degil.

3) HIYERARSIK HAVUZLAMA (partial pooling) — "3 gozlemli hucrede ne yapalim?"
   Hucre kendi basina konusamiyorsa UST kirilimdan guc odunc alir:
   marka+beden -> marka -> kategori -> genel. Tam havuzlama (hepsini ayni
   say) ile havuzlamama (her hucre yalniz) arasindaki dogru orta yol.
   Odunc alinan agirlik gozlem sayisiyla azalir: veri geldikce hucre
   kendi sesiyle konusmaya baslar.

Saf modul: DB/ag bilmez, rastgelelik disaridan verilebilir -> izole test.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field
from typing import Optional, Sequence

# Wilson icin z: %95 guven -> 1.96, %90 -> 1.645
Z_95 = 1.959964
Z_90 = 1.644854

# Hiyerarsik havuzlamada "kendi sesiyle konusma" esigi. Bu kadar gozlemde
# ust kirilimin agirligi ~%50'ye duser. Kucuk tutmak hucreyi erken serbest
# birakir (gurultu), buyuk tutmak fazla bastirir (gercek farki gizler).
POOLING_STRENGTH = 15.0


def wilson_interval(successes: int, trials: int, z: float = Z_95) -> tuple[float, float]:
    """
    Bir oranin Wilson guven araligi.
    0 basari veya 0 basarisizlikta bile ANLAMLI aralik verir (normal
    yaklasimin coktugu yer tam burasi).
    """
    if trials <= 0:
        return (0.0, 1.0)          # hicbir sey bilmiyoruz -> tum aralik
    p = successes / trials
    z2 = z * z
    payda = 1 + z2 / trials
    merkez = (p + z2 / (2 * trials)) / payda
    yayilim = (z / payda) * math.sqrt(p * (1 - p) / trials + z2 / (4 * trials * trials))
    return (max(0.0, round(merkez - yayilim, 4)), min(1.0, round(merkez + yayilim, 4)))


def wilson_lower(successes: int, trials: int, z: float = Z_95) -> float:
    """
    Siralama icin kotumser (alt sinir) tahmin.
    NEDEN ALT SINIR: 1/1 = %100 ile 90/100 = %90 arasinda ikincisi daha iyi
    bir bahistir. Alt sinir bunu dogru siralar (%2.5 vs %82).
    """
    return wilson_interval(successes, trials, z)[0]


@dataclass
class BetaPosterior:
    """
    Beta-Bernoulli posterior. alpha = basari + 1, beta = basarisizlik + 1
    (Jeffreys yerine uniform onsel: hicbir sey bilmiyorken her oran esit
    olasi — is baslangicinda dogru varsayim).
    """
    successes: int = 0
    failures: int = 0
    prior_a: float = 1.0
    prior_b: float = 1.0

    @property
    def alpha(self) -> float:
        return self.prior_a + self.successes

    @property
    def beta(self) -> float:
        return self.prior_b + self.failures

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def n(self) -> int:
        return self.successes + self.failures

    def sample(self, rng: Optional[random.Random] = None) -> float:
        r = rng or random
        return r.betavariate(self.alpha, self.beta)


@dataclass
class Candidate:
    """Kazima adayi: bir kategori/marka/beden/fiyat hucresi."""
    key: str
    successes: int = 0        # satilan
    failures: int = 0         # satilmayan (hala aktif veya kaldirilmis)
    label: str = ""
    parent_keys: list[str] = field(default_factory=list)   # ust kirilimlar

    @property
    def trials(self) -> int:
        return self.successes + self.failures


@dataclass
class Ranked:
    key: str
    label: str
    raw_rate: float
    pooled_rate: float
    lower_bound: float
    upper_bound: float
    trials: int
    thompson_draw: float = 0.0
    confidence: str = "dusuk"      # dusuk | orta | yuksek
    note: str = ""


def pooled_rate(cell: Candidate, parents: dict[str, Candidate]) -> float:
    """
    Hiyerarsik havuzlama: hucrenin oranini ust kirilimlara dogru cekerek
    duzeltir. Cekme miktari gozlem sayisiyla TERS orantili.

    w = n / (n + POOLING_STRENGTH)
    tahmin = w * kendi_orani + (1-w) * ust_orani

    n=0   -> tamamen ust kirilim (bilgi yok, atadan miras)
    n=15  -> yari yariya
    n=150 -> neredeyse tamamen kendi verisi
    """
    if cell.trials <= 0 and not cell.parent_keys:
        return 0.0
    # Ust kirilimlari en yakindan en uzaga birlestir
    ust_basari, ust_deneme = 0, 0
    for pk in cell.parent_keys:
        p = parents.get(pk)
        if p:
            ust_basari += p.successes
            ust_deneme += p.trials
    ust_oran = (ust_basari / ust_deneme) if ust_deneme else 0.25   # genel onsel
    if cell.trials <= 0:
        return round(ust_oran, 4)
    kendi = cell.successes / cell.trials
    w = cell.trials / (cell.trials + POOLING_STRENGTH)
    return round(w * kendi + (1 - w) * ust_oran, 4)


def rank_by_thompson(candidates: Sequence[Candidate],
                     parents: Optional[dict[str, Candidate]] = None,
                     *, rng: Optional[random.Random] = None,
                     limit: int = 25) -> list[Ranked]:
    """
    Kazima onceligi: Thompson ornekleme ile kesif/somuru dengesi.

    Her adayin posterior'undan bir ornek cekilir ve ona gore siralanir.
    Sonuc her cagrida biraz DEGISIR — bu bir kusur degil, tasarim: sistem
    ara sira belirsiz kategorileri deneyerek ogrenmeye devam eder.
    Deterministik siralama isteniyorsa rank_by_lower_bound kullanilir.
    """
    r = rng or random
    ust = parents or {}
    cikti: list[Ranked] = []
    for c in candidates:
        post = BetaPosterior(successes=c.successes, failures=c.failures)
        alt, ust_sinir = wilson_interval(c.successes, c.trials)
        ham = (c.successes / c.trials) if c.trials else 0.0
        guven = ("yuksek" if c.trials >= 50 else
                 "orta" if c.trials >= 15 else "dusuk")
        havuz = pooled_rate(c, ust)
        not_ = ""
        if c.trials == 0:
            not_ = "hic gozlem yok — ust kirilimdan miras alindi, kesif icin secilebilir"
        elif c.trials < 15:
            not_ = (f"{c.trials} gozlem az; ham oran %{ham*100:.0f} ama havuzlanmis "
                    f"tahmin %{havuz*100:.0f} (ust kirilimdan duzeltildi)")
        cikti.append(Ranked(
            key=c.key, label=c.label or c.key,
            raw_rate=round(ham, 4), pooled_rate=havuz,
            lower_bound=alt, upper_bound=ust_sinir,
            trials=c.trials, thompson_draw=round(post.sample(r), 4),
            confidence=guven, note=not_,
        ))
    cikti.sort(key=lambda x: -x.thompson_draw)
    return cikti[:limit]


def rank_by_lower_bound(candidates: Sequence[Candidate],
                        parents: Optional[dict[str, Candidate]] = None,
                        *, limit: int = 25) -> list[Ranked]:
    """
    Deterministik, kotumser siralama (rapor/panel icin).
    Thompson her cagrida degisir; insana gosterilen tabloda kararlilik gerekir.
    """
    ust = parents or {}
    cikti = []
    for c in candidates:
        alt, ust_sinir = wilson_interval(c.successes, c.trials)
        ham = (c.successes / c.trials) if c.trials else 0.0
        cikti.append(Ranked(
            key=c.key, label=c.label or c.key,
            raw_rate=round(ham, 4), pooled_rate=pooled_rate(c, ust),
            lower_bound=alt, upper_bound=ust_sinir, trials=c.trials,
            confidence=("yuksek" if c.trials >= 50 else
                        "orta" if c.trials >= 15 else "dusuk"),
        ))
    cikti.sort(key=lambda x: (-x.lower_bound, -x.trials))
    return cikti[:limit]


def required_sample_size(p_estimate: float, margin: float = 0.10,
                         z: float = Z_95) -> int:
    """
    "Bu kategoride ne kadar veri toplayinca karar verebilirim?"
    Istenen hata payi icin gereken gozlem sayisi. Panelde
    "23 gozlem daha gerekiyor" demeyi mumkun kilar — belirsizligi
    somut bir ise donusturur.
    """
    p = min(max(p_estimate, 0.01), 0.99)
    return max(1, math.ceil((z * z * p * (1 - p)) / (margin * margin)))


def price_band(price_eur: float, edges: Sequence[float] = (15, 30, 50, 80, 120, 200)) -> str:
    """
    Fiyat bandi etiketi. Esitlik degil, PAZAR mantigi: ikinci el giyimde
    karar noktalari 15/30/50/80/120/200 EUR civarinda kumelenir.
    Esit genislikte bantlar (0-50, 50-100...) ucuz bandi asiri doldurur
    ve istatistigi kullanissiz kilar.
    """
    p = float(price_eur or 0)
    onceki = 0.0
    for e in edges:
        if p < e:
            return f"{int(onceki)}-{int(e)}"
        onceki = e
    return f"{int(edges[-1])}+"


# Beden normalizasyonu: platformlar farkli yaziyor (L / Large / 52 / EU 52).
# Istatistikte bunlari ayri hucre saymak veriyi bosuna boler.
_SIZE_MAP = {
    "xxs": "XXS", "xs": "XS", "s": "S", "m": "M", "l": "L",
    "xl": "XL", "xxl": "XXL", "xxxl": "3XL", "3xl": "3XL", "4xl": "4XL",
    "small": "S", "medium": "M", "large": "L",
    "x-large": "XL", "xlarge": "XL", "x-small": "XS",
}
# Alman erkek konfeksiyon numarasi -> harf beden.
# ARALIKLAR CAKISMAMALI: onceki surumde 50-52 "L" ve 52-56 "XL" ust uste
# biniyordu, 52 yanlislikla L cikiyordu. Alman standardi:
# 44=XS 46=S 48=M 50=L 52=XL 54=XXL 56+=3XL
_NUM_TO_LETTER = [
    (range(40, 46), "XS"), (range(46, 48), "S"), (range(48, 50), "M"),
    (range(50, 52), "L"), (range(52, 54), "XL"), (range(54, 56), "XXL"),
    (range(56, 64), "3XL"),
]


def normalize_size(raw: str) -> str:
    """Beden etiketini tek olcege indirger; cozulemezse 'bilinmiyor'."""
    s = (raw or "").strip().lower()
    if not s:
        return "bilinmiyor"
    s = s.replace("größe", "").replace("grosse", "").replace("size", "")
    s = s.replace("gr.", "").replace("eu", "").strip(" .:-/")
    if s in _SIZE_MAP:
        return _SIZE_MAP[s]
    # "48/50 (m)" gibi bilesikler: parantez icindeki harfi tercih et
    m = re.search(r"\(([a-z]{1,4})\)", s)
    if m and m.group(1) in _SIZE_MAP:
        return _SIZE_MAP[m.group(1)]
    m = re.search(r"\b(\d{2})\b", s)
    if m:
        n = int(m.group(1))
        for aralik, harf in _NUM_TO_LETTER:
            if n in aralik:
                return harf
    ilk = s.split("/")[0].split()[0] if s.split() else ""
    return _SIZE_MAP.get(ilk, "bilinmiyor")
