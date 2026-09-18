"""
Kalite / defekt filtresi (saf, additive).

GERCEK VERI BULGUSU: products.condition alani bos geliyor. Bu yuzden kalite/durum
metinden (baslik + aciklama) cozulur. Amac: iade riski tasiyan DEFEKTLI urunlerin
bize dusmemesi + "sehr gut / neu / neuwertig" gibi urunleri one cikarmak (daha
kaliteli site izlenimi).

Sert kural: defekt sinyali varsa urun REDDEDILIR (accept=False).
Yumusak kural: durum sinyaline gore 0-100 kalite skoru (siralama/tercih icin).
Marka hedefte mi bilgisi eklenir ama ASLA tek basina eleme sebebi degildir
(kullanici "25 marka ile sinirlama" istemedi).
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel

from .brand_catalog import canonical_brand

# Iade riski = kesin eleme. Almanca + birkac EN/TR karsilik.
DEFECT_KEYWORDS: tuple[str, ...] = (
    "defekt", "defect", "kaputt", "kaput", "broken", "riss", "rissen", "gerissen",
    "loch", "locher", "löcher", "fleck", "flecken", "verfleckt", "beschadigt",
    "beschädigt", "bastler", "ersatzteil", "reparatur", "reparieren", "zu reparieren",
    "fehlt", "fehlend", "nicht funktionsfahig", "nicht funktionsfähig", "kratzer",
    "verschlissen", "vergilbt", "stark abgenutzt", "hasarli", "kusurlu", "ariza",
    "arizali", "as is", "as-is", "not working", "for parts",
)

# Pozitif durum sinyalleri (skoru yukseltir)
POSITIVE_CONDITION: tuple[str, ...] = (
    "neuwertig", "wie neu", "nagelneu", "neu mit etikett", "mit etikett",
    "ungetragen", "ungenutzt", "einwandfrei", "tadellos", "sehr gut", "top zustand",
    "top-zustand", "neu ", "brandneu", "sifir", "sıfır", "etiketli",
)

# Zayif durum (skoru dusurur ama elemez)
WEAK_CONDITION: tuple[str, ...] = (
    "stark gebraucht", "viele gebrauchsspuren", "deutliche gebrauchsspuren",
    "abgenutzt", "getragen", "gut erhalten aber", "leichte gebrauchsspuren",
)


class QualityVerdict(BaseModel):
    accept: bool                 # False ise defekt -> bize dusmesin
    is_defective: bool
    quality_score: int           # 0-100
    condition_label: str         # "neu" | "sehr_gut" | "gut" | "belirsiz" | "defekt"
    has_target_brand: bool
    reasons: list[str] = []


def _contains_any(text: str, words) -> Optional[str]:
    for w in words:
        # kelime sinirina duyarli basit eslesme
        if w in text:
            return w
    return None


def assess(
    title: Optional[str],
    description: Optional[str] = None,
    condition: Optional[str] = None,
    brand: Optional[str] = None,
) -> QualityVerdict:
    """Bir urunun metninden kalite/defekt degerlendirmesi uretir."""
    blob = " ".join(x for x in (title, description, condition) if x).lower()
    blob = re.sub(r"\s+", " ", blob)
    reasons: list[str] = []

    # 1) Defekt -> kesin eleme
    defect_hit = _contains_any(blob, DEFECT_KEYWORDS)
    if defect_hit:
        return QualityVerdict(
            accept=False, is_defective=True, quality_score=0,
            condition_label="defekt", has_target_brand=bool(canonical_brand(brand) or canonical_brand(title)),
            reasons=[f"defekt sinyali: '{defect_hit}'"],
        )

    # 2) Durum skoru
    score = 55  # notr taban (durum bilgisi yoksa kabul et, orta skor)
    label = "belirsiz"
    pos = _contains_any(blob, POSITIVE_CONDITION)
    if pos:
        score = 90
        label = "neu" if any(k in blob for k in ("neu", "etiket", "sifir", "sıfır", "ungetragen")) else "sehr_gut"
        reasons.append(f"pozitif durum: '{pos.strip()}'")
    weak = _contains_any(blob, WEAK_CONDITION)
    if weak:
        score = min(score, 40)
        label = "gut" if label == "belirsiz" else label
        reasons.append(f"zayif durum: '{weak}'")

    has_brand = bool(canonical_brand(brand) or canonical_brand(title))
    if has_brand:
        score = min(100, score + 5)
        reasons.append("hedef marka")

    return QualityVerdict(
        accept=True, is_defective=False, quality_score=score,
        condition_label=label, has_target_brand=has_brand, reasons=reasons,
    )


def should_keep(
    title: Optional[str],
    description: Optional[str] = None,
    condition: Optional[str] = None,
    brand: Optional[str] = None,
    *,
    min_quality: int = 0,
) -> bool:
    """
    Kazima sirasinda hizli karar: defektli DAIMA elenir; ayrica min_quality
    esigi altindakiler elenir (varsayilan 0 = sadece defektlileri ele).
    """
    v = assess(title, description, condition, brand)
    return v.accept and v.quality_score >= min_quality
