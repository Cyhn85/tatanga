"""
Marka / model / kategori katalogu (veri-odakli, genisletilebilir).

Amac: capraz-platform eslestirmede gercekcilik. Ayni marka gorununce mont/canta/
ayakkabiyi karistirmamak icin KATEGORI KAPISI, ve ayni urunu tanimak icin MARKA +
MODEL olcegi. Bu dosyadaki tohum veri koda dokunmadan data/brand_catalog.json ile
genisletilebilir (kullanici kendi markalarini/modellerini ekleyebilir).
"""

from __future__ import annotations

import json
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent
_OVERRIDE_FILE = _BASE_DIR / "data" / "brand_catalog.json"

# Kanonik marka -> takma adlar (normalize icin). Hepsi kucuk harf karsilastirilir.
BRAND_ALIASES: dict[str, list[str]] = {
    "the north face": ["north face", "tnf", "thenorthface"],
    "nike": ["nike"],
    "adidas": ["adidas", "adidas originals"],
    "patagonia": ["patagonia"],
    "stone island": ["stone island", "stoneisland"],
    "arcteryx": ["arc'teryx", "arcteryx", "arc teryx"],
    "carhartt": ["carhartt", "carhartt wip"],
    "levis": ["levi's", "levis", "levi strauss"],
    "moncler": ["moncler"],
    "canada goose": ["canada goose"],
    "new balance": ["new balance", "nb"],
    "puma": ["puma"],
    "vans": ["vans"],
    "converse": ["converse"],
    "dr martens": ["dr. martens", "dr martens", "doc martens"],
    "ralph lauren": ["ralph lauren", "polo ralph lauren"],
    "tommy hilfiger": ["tommy hilfiger", "tommy"],
    "lacoste": ["lacoste"],
    "columbia": ["columbia"],
    "jack wolfskin": ["jack wolfskin"],
    "napapijri": ["napapijri"],
    "cp company": ["c.p. company", "cp company"],
    "uniqlo": ["uniqlo"],
    "champion": ["champion"],
    "gucci": ["gucci"],
    "prada": ["prada"],
    "louis vuitton": ["louis vuitton", "lv"],
}

# Kanonik marka -> bilinen model cizgileri (varsa model anahtari bunlardan uretilir).
BRAND_MODELS: dict[str, list[str]] = {
    "the north face": ["base camp", "basecamp", "nuptse", "denali", "borealis",
                       "resolve", "mcmurdo", "himalayan", "duffel", "jester"],
    "nike": ["air max", "air force", "dunk", "jordan", "blazer", "vapormax",
             "pegasus", "tech fleece"],
    "adidas": ["superstar", "stan smith", "gazelle", "samba", "ultraboost",
               "campus", "forum", "firebird"],
    "new balance": ["550", "574", "990", "991", "992", "993", "997", "998", "2002"],
    "carhartt": ["detroit", "michigan", "active", "og chore", "nimbus"],
    "stone island": ["ghost", "shadow project", "nylon metal"],
    "patagonia": ["nano puff", "retro x", "synchilla", "torrentshell", "baggies"],
    "moncler": ["maya", "montgenevre", "grenoble"],
    "dr martens": ["1460", "1461", "jadon", "chelsea"],
}

# Kategori kapisi: baslik/kategori anahtar kelimeleri -> kanonik kategori kovasi.
# Ayni kovada degilse ESLESME YOK (mont asla canta/ayakkabi ile eslesmez).
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "jacket":   ["jacke", "jacket", "mantel", "coat", "parka", "daunenjacke",
                 "puffer", "weste", "vest", "anorak", "windbreaker", "mont"],
    "bag":      ["tasche", "bag", "rucksack", "backpack", "duffel", "duffle",
                 "reisetasche", "handtasche", "umhangetasche", "canta"],
    "shoes":    ["schuh", "schuhe", "shoe", "shoes", "sneaker", "sneakers",
                 "stiefel", "boots", "trainers", "ayakkabi"],
    "trousers": ["hose", "jeans", "trousers", "pants", "chino", "cargo", "pantolon"],
    "sweat":    ["hoodie", "kapuzen", "sweatshirt", "sweater", "pullover", "pulli",
                 "sweat", "esofman", "jumper", "strick"],
    "shirt":    ["hemd", "shirt", "t-shirt", "tshirt", "poloshirt", "polo", "bluse", "top"],
    "accessory":["mutze", "cap", "hat", "beanie", "schal", "scarf", "handschuh",
                 "gloves", "gurtel", "belt", "socken", "aksesuar"],
}


def _load_overrides() -> None:
    """Varsa data/brand_catalog.json'dan tohum veriyi genisletir (merge)."""
    if not _OVERRIDE_FILE.exists():
        return
    try:
        data = json.loads(_OVERRIDE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    for brand, aliases in (data.get("brand_aliases") or {}).items():
        BRAND_ALIASES.setdefault(brand.lower(), [])
        for a in aliases:
            if a.lower() not in BRAND_ALIASES[brand.lower()]:
                BRAND_ALIASES[brand.lower()].append(a.lower())
    for brand, models in (data.get("brand_models") or {}).items():
        BRAND_MODELS.setdefault(brand.lower(), [])
        for m in models:
            if m.lower() not in BRAND_MODELS[brand.lower()]:
                BRAND_MODELS[brand.lower()].append(m.lower())
    for cat, kws in (data.get("category_keywords") or {}).items():
        CATEGORY_KEYWORDS.setdefault(cat, [])
        for k in kws:
            if k.lower() not in CATEGORY_KEYWORDS[cat]:
                CATEGORY_KEYWORDS[cat].append(k.lower())


_load_overrides()

# Hizli arama icin ters indeksler
_ALIAS_TO_BRAND: dict[str, str] = {}
for _canon, _aliases in BRAND_ALIASES.items():
    _ALIAS_TO_BRAND[_canon] = _canon
    for _a in _aliases:
        _ALIAS_TO_BRAND[_a] = _canon


def canonical_brand(raw: str | None) -> str | None:
    """Ham marka/baslik icinden kanonik markayi bulur (takma ad eslemesiyle)."""
    if not raw:
        return None
    text = raw.strip().lower()
    # once tam alias eslesmesi
    if text in _ALIAS_TO_BRAND:
        return _ALIAS_TO_BRAND[text]
    # sonra metin icinde gecen en uzun alias
    best = None
    for alias, canon in _ALIAS_TO_BRAND.items():
        if alias in text and (best is None or len(alias) > len(best[0])):
            best = (alias, canon)
    return best[1] if best else None
