"""
Kategori tabanli kazima plani — "once neyi tara" sorusunun cevabi.

FELSEFE DEGISIKLIGI: Bugune kadar kazima ANAHTAR KELIME odakliydi ("columbia
herren jacke"). Bu, tek bir markanin tek bir urununu derinlemesine tarar ama
PAZARIN TAMAMINI hicbir zaman gormez. Istatistik icin gereken tam tersi:
GENIS ama INCE. 50 kategoriden her birinde 2.000 gozlem, tek kategoride
100.000 gozlemden cok daha degerlidir — cunku kategoriler ARASI karsilastirma
ancak boyle mumkun olur.

VERI EKONOMISI (kullanicinin asil istegi):
  Gozlem satiri  ~93 bayt  -> 500.000 gozlem = 46 MB
  Tam urun satiri ~4.700 bayt -> 500.000 urun = 2,3 GB
  Yani ayni bilgi 50 kat daha ucuza saklanir. Ay(lar) boyunca biriken
  gozlem, birkac gunluk tam urun verisinden daha degerli hale gelir.

KAPSAMA GARANTISI: Sadece "en iyi" kategoriye gitmek, digerlerini kor birakir
ve sistem kendi onyargisini dogrular. Bu yuzden plan iki bolumden olusur:
  - KESIF payi: en az kapsanan kategoriler (adil rotasyon)
  - SOMURU payi: Thompson ile secilen, kanitlanmis iyi kategoriler
Oran zamanla degisir: veri azken kesif agir basar, biriktikce somuru.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

# cssberlin giyim kategorileriyle hizali, PLATFORM ARAMASINDA ISE YARAYAN
# kok terimler. Her kategori icin cok dilli karsiliklar keyword_localizer
# tarafindan uretilir; burada KANONIK ad tutulur.
CLOTHING_TREE: dict[str, list[str]] = {
    "jacken":    ["jacke", "winterjacke", "regenjacke", "daunenjacke", "softshelljacke"],
    "mantel":    ["mantel", "parka", "trenchcoat"],
    "fleece":    ["fleecejacke", "fleece pullover"],
    "pullover":  ["pullover", "hoodie", "sweatshirt", "strickjacke"],
    "hemden":    ["hemd", "bluse"],
    "tshirts":   ["t-shirt", "poloshirt"],
    "hosen":     ["hose", "jeans", "chino", "jogginghose"],
    "kleider":   ["kleid", "rock"],
    "schuhe":    ["sneaker", "stiefel", "halbschuhe"],
    "taschen":   ["tasche", "rucksack"],
    "sport":     ["sportjacke", "trainingsanzug", "laufschuhe"],
    "accessoires": ["muetze", "schal", "handschuhe", "guertel"],
}

GENDERS = ["herren", "damen", "kinder"]

# Kesif/somuru dengesi: toplam gozlem sayisina gore kesif payi.
# Baslangicta neredeyse tamamen kesif; veri biriktikce somuruye kayar.
def exploration_ratio(total_observations: int) -> float:
    """
    0 gozlem   -> 1.00 (tamamen kesif)
    10.000     -> ~0.50
    100.000    -> ~0.17
    Hicbir zaman 0 olmaz: pazar degisir, kor kalmamak icin surekli kesif sart.
    """
    if total_observations <= 0:
        return 1.0
    oran = 10_000 / (10_000 + total_observations)
    return round(max(0.15, min(1.0, oran)), 3)


@dataclass
class ScrapeTask:
    """Tek bir kazima gorevi — kategori x cinsiyet x terim."""
    category: str
    gender: str
    term: str
    priority: float = 0.0
    reason: str = ""
    platforms: list[str] = field(default_factory=list)

    @property
    def query(self) -> str:
        """Platforma gonderilecek ham sorgu (yerellestirme sonra uygulanir)."""
        return f"{self.term} {self.gender}".strip()

    @property
    def key(self) -> str:
        return f"{self.category}|{self.gender}|{self.term}"


def all_tasks(categories: Optional[Sequence[str]] = None,
              genders: Optional[Sequence[str]] = None) -> list[ScrapeTask]:
    """Plandaki TUM gorevleri uretir (kapsama hesabinin paydasi)."""
    kats = categories or list(CLOTHING_TREE.keys())
    cins = genders or GENDERS
    gorevler = []
    for k in kats:
        for terim in CLOTHING_TREE.get(k, [k]):
            for c in cins:
                # Cocuk kategorisinde bazi terimler anlamsiz — yine de
                # URETILIR: "yok" oldugunu ancak olcerek ogreniriz.
                gorevler.append(ScrapeTask(category=k, gender=c, term=terim))
    return gorevler


def plan_next_round(coverage: dict[str, int],
                    performance: Optional[dict[str, tuple[int, int]]] = None,
                    *, batch_size: int = 12,
                    rng=None) -> list[ScrapeTask]:
    """
    Siradaki kazima turunu planlar.

    coverage    : gorev anahtari -> o gorevden toplanan gozlem sayisi
    performance : gorev anahtari -> (satilan, toplam) — varsa somuru icin

    Donen liste kesif ve somuru gorevlerinin KARISIMIDIR; oran toplam
    gozlem sayisina gore otomatik ayarlanir.
    """
    import random
    from .demand_stats import Candidate, rank_by_thompson

    r = rng or random.Random()
    gorevler = all_tasks()
    toplam_gozlem = sum(coverage.values()) if coverage else 0
    kesif_orani = exploration_ratio(toplam_gozlem)
    kesif_adet = max(1, round(batch_size * kesif_orani))
    somuru_adet = max(0, batch_size - kesif_adet)

    # --- KESIF: en az kapsanan gorevler ---
    # Esit kapsamada rastgele sec ki her turda ayni sira olusmasin.
    sirali = sorted(gorevler, key=lambda g: (coverage.get(g.key, 0), r.random()))
    kesif = []
    for g in sirali[:kesif_adet]:
        n = coverage.get(g.key, 0)
        g.priority = 1.0
        g.reason = (f"kesif: bu gorevde {n} gozlem var (en az kapsanan)"
                    if n else "kesif: hic taranmamis")
        kesif.append(g)

    # --- SOMURU: kanitlanmis iyi gorevler (Thompson) ---
    somuru: list[ScrapeTask] = []
    if somuru_adet and performance:
        indeks = {g.key: g for g in gorevler}
        adaylar = [
            Candidate(key=k, successes=s, failures=max(0, t - s))
            for k, (s, t) in performance.items() if k in indeks
        ]
        if adaylar:
            secilen = {g.key for g in kesif}
            for sira in rank_by_thompson(adaylar, rng=r, limit=len(adaylar)):
                if len(somuru) >= somuru_adet:
                    break
                if sira.key in secilen:
                    continue
                g = indeks[sira.key]
                g.priority = round(sira.thompson_draw, 3)
                g.reason = (f"somuru: {sira.trials} gozlemde satis orani "
                            f"%{sira.raw_rate*100:.0f} (Wilson alt %{sira.lower_bound*100:.0f})")
                somuru.append(g)

    return kesif + somuru


def coverage_report(coverage: dict[str, int]) -> dict:
    """
    Kapsama karnesi: plan ne kadar tamamlandi, nerede kor nokta var.
    Panelde "3 kategori hic taranmadi" demeyi mumkun kilar.
    """
    gorevler = all_tasks()
    toplam = len(gorevler)
    taranan = sum(1 for g in gorevler if coverage.get(g.key, 0) > 0)
    kat_gozlem: dict[str, int] = {}
    kat_gorev: dict[str, int] = {}
    for g in gorevler:
        kat_gozlem[g.category] = kat_gozlem.get(g.category, 0) + coverage.get(g.key, 0)
        kat_gorev[g.category] = kat_gorev.get(g.category, 0) + 1
    bos = sorted(k for k, v in kat_gozlem.items() if v == 0)
    return {
        "toplam_gorev": toplam,
        "taranan_gorev": taranan,
        "kapsama_yuzde": round(100 * taranan / toplam, 1) if toplam else 0.0,
        "toplam_gozlem": sum(coverage.values()) if coverage else 0,
        "kesif_orani": exploration_ratio(sum(coverage.values()) if coverage else 0),
        "kategori_gozlem": dict(sorted(kat_gozlem.items(), key=lambda x: -x[1])),
        "hic_taranmayan_kategoriler": bos,
    }
