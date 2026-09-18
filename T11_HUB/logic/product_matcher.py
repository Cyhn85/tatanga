"""
Urun eslestirme (kategori kapisi + marka + model olcegi).

Bu modul, capraz-platform arbitrajinda "ayni urun mu?" sorusunu gercekci sekilde
yanitlar. Kural:
  1) KATEGORI KAPISI: iki ilan ayni kanonik kategoride degilse ASLA eslesmez
     (North Face mont != North Face duffel canta != North Face ayakkabi).
  2) MARKA: kanonik marka ayni olmali (takma adlar normalize edilir).
  3) MODEL: katalogdaki model cizgisi eslesir; yoksa baslik token'lari (Jaccard).

match_key() ayni urunler icin ayni anahtari uretir; arbitrage_engine bunu kullanir.
Salt hesap, DB/dis servis gerektirmez.
"""

from __future__ import annotations

import re
from typing import Optional

from .brand_catalog import BRAND_MODELS, CATEGORY_KEYWORDS, canonical_brand

# Model/token uretiminde atilacak gurultu
_STOP = {
    "the", "and", "und", "mit", "fur", "size", "gr", "eur", "neu", "new", "top",
    "sehr", "gut", "wie", "neuwertig", "original", "echt", "vintage", "gebraucht",
    "used", "damen", "herren", "kinder", "unisex", "herren", "grosse", "big",
}
_SIZE_TOKENS = {"xs", "s", "m", "l", "xl", "xxl", "xxxl"} | {str(n) for n in range(34, 48)}


def infer_category(title: Optional[str], category: Optional[str]) -> Optional[str]:
    """
    Kanonik kategori kovasini belirler. Once urunun kendi category alanina, sonra
    basliga bakar. Hicbiri eslesmezse None (bu durumda eslestirme temkinli davranir).
    """
    for source in (category, title):
        if not source:
            continue
        text = source.lower()
        for bucket, kws in CATEGORY_KEYWORDS.items():
            if any(kw in text for kw in kws):
                return bucket
    return None


def _model_key(brand: Optional[str], title: Optional[str]) -> str:
    """Katalog model cizgisi eslesirse onu; yoksa ayirt edici token'lari dondurur."""
    text = (title or "").lower()
    if brand and brand in BRAND_MODELS:
        for model in sorted(BRAND_MODELS[brand], key=len, reverse=True):
            if model in text:
                # alfanumerige indirge: "base camp" ve "basecamp" ayni anahtar olsun
                return re.sub(r"[^a-z0-9]", "", model)
    # token fallback
    if brand:
        text = text.replace(brand, " ")
    tokens = re.findall(r"[a-z0-9]+", text)
    keep = sorted({t for t in tokens if len(t) >= 3 and t not in _STOP and t not in _SIZE_TOKENS})
    return "-".join(keep[:4])


_CLOTHING_SIZES = {"xs", "s", "m", "l", "xl", "xxl", "xxxl", "xxxxl"}


def extract_size(title: Optional[str], size_field: Optional[str] = None) -> str:
    """
    Beden/kapasite anahtari uretir. Once explicit size alanina, yoksa BASLIKTAN
    cikarir. Boyle olunca beden fiyati belirledigi (ör. 50L vs 150L duffel) ama
    size alani bos gelen urunler ayri kovalara duser -> sahte spread engellenir.
    Sira: explicit -> litre kapasite -> giysi bedeni -> ayakkabi (EU 34-48).
    """
    if size_field:
        s = size_field.strip().lower().replace(" ", "")
        if s:
            return s
    t = (title or "").lower()
    # litre kapasite (canta/duffel): "50l", "50 l", "50 liter"
    m = re.search(r"(\d{2,3})\s?(?:l\b|liter|litre|ltr)", t)
    if m:
        return m.group(1) + "l"
    # giysi bedeni tokeni
    for tok in re.findall(r"[a-z]+", t):
        if tok in _CLOTHING_SIZES:
            return tok
    # ayakkabi EU beden (standalone 34-48)
    m = re.search(r"\b(3[4-9]|4[0-8])\b", t)
    if m:
        return "eu" + m.group(1)
    return ""


def _size_bucket(size: Optional[str]) -> str:
    return (size or "").strip().lower().replace(" ", "")


def match_key(
    *,
    brand: Optional[str],
    title: Optional[str],
    size: Optional[str] = None,
    category: Optional[str] = None,
) -> Optional[str]:
    """
    Kanonik eslesme anahtari: "<kategori>|<marka>|<model>|<beden>".
    Kategori veya marka/model belirlenemezse None (eslestirmeye dahil edilmez).
    """
    cat = infer_category(title, category)
    brand_c = canonical_brand(brand) or canonical_brand(title)
    model = _model_key(brand_c, title)
    if cat is None or (not brand_c and not model):
        return None
    # beden/kapasite: size alani bossa basliktan cikar -> varyantlar ayrisir
    size_key = extract_size(title, size)
    return f"{cat}|{brand_c or '?'}|{model}|{size_key}"


def same_product(a: dict, b: dict) -> bool:
    """
    Iki urun sozlugunu (brand/title/size/category alanlariyla) karsilastirir.
    Kategori kapisi + ayni match_key esasli. Hizli, deterministik.
    """
    ka = match_key(brand=a.get("brand"), title=a.get("title"),
                   size=a.get("size"), category=a.get("category"))
    kb = match_key(brand=b.get("brand"), title=b.get("title"),
                   size=b.get("size"), category=b.get("category"))
    return ka is not None and ka == kb
