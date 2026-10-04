#!/usr/bin/env python3
"""
Gozlem verisinden fiyat iskeletini cikarir. Hicbir seye karar vermez, sadece olcer.

MANTIK: Fiyat ~ Taban(marka+model) x Kondisyon x Pazar x Beden
Taban her model icin ayridir ama carpanlar TUM modellerde ortaktir. Bu yuzden carpanlar
butun veriden (binlerce ilan) hesaplanir, model tabani ise o carpanlara bolunerek
5-10 ilanla bile cikarilabilir. Carpansiz yaklasim her model icin ayri istatistik
isterdi ve asla yeterli veri olmazdi.

Carpanlar ortanca oranlarla hesaplanir (ortalama degil): birkac aykiri ilan sonucu bozmasin.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import statistics
from collections import Counter, defaultdict

DB_FILE = "/opt/tatanga-observer/observe.db"
MIN_GROUP = 8          # bir carpan/taban icin gereken en az ilan sayisi
MIN_MODEL = 8          # model tabani icin gereken en az ilan sayisi

# Kondisyonlarin diller arasi karsiligi (tek olcege indirgeme)
CONDITION_MAP = {
    "neu, mit etikett": "yeni_etiketli", "neuf avec étiquette": "yeni_etiketli",
    "nuovo con cartellino": "yeni_etiketli", "nieuw met prijskaartje": "yeni_etiketli",
    "neu": "yeni", "neuf sans étiquette": "yeni", "nuovo senza cartellino": "yeni",
    "nieuw zonder prijskaartje": "yeni",
    "sehr gut": "cok_iyi", "très bon état": "cok_iyi", "ottime": "cok_iyi",
    "heel goed": "cok_iyi",
}
REFERENCE_CONDITION = "cok_iyi"
REFERENCE_MARKET = "DE"

# Model adayi olamayacak kelimeler: renk, beden, kondisyon, genel giysi sozcukleri
STOP = set("""
jacke jacken mantel veste vestes giacca jas jassen winterjacke sommerjacke regenjacke
herren damen homme femme uomo donna heren dames kinder enfant unisex
schwarz weiss weiß blau rot grun grün grau beige braun rosa gelb navy noir blanc bleu rouge
vert gris nero bianco blu verde zwart wit blauw groen rood
neu neuf nuovo nieuw gut gute guter sehr très bon etat état top zustand condition
gr gre grosse größe taille taglia maat size xs s m l xl xxl xxxl
mit und ohne avec sans con senza met zonder the and de la le les il of
vintage original echt selten rare neuwertig getragen wie super schön schoen nice
jacket coat parka bomber daunenjacke steppjacke fleecejacke softshell windbreaker
""".split())

_WORD = re.compile(r"[a-z0-9][a-z0-9\-\.]{1,}")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def norm_condition(raw: str | None) -> str | None:
    return CONDITION_MAP.get((raw or "").strip().lower())


def size_group(raw: str | None) -> str | None:
    """Beden gruplari: ulkeden ulkeye numara farkli, harf bedenler ortak."""
    s = (raw or "").upper()
    for tag in ("XXL", "XXS", "XS", "XL", "S", "M", "L"):
        if re.search(rf"\b{tag}\b", s):
            return tag
    return None


def samples(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT brand, title, size, condition, price, country FROM catalog_samples "
        "WHERE is_child=0 AND price > 0"
    ).fetchall()
    out = []
    for r in rows:
        cond = norm_condition(r["condition"])
        if not cond:
            continue
        out.append({
            "brand": (r["brand"] or "").strip().lower(),
            "title": (r["title"] or "").lower(),
            "cond": cond,
            "market": r["country"],
            "size": size_group(r["size"]),
            "price": float(r["price"]),
        })
    return out


def ratio_factor(data: list[dict], key: str, reference: str) -> dict[str, float]:
    """
    Bir boyutun carpanlari: her markada o boyutun ortanca fiyati referansa bolunur,
    sonra markalar arasi ortanca alinir. Boylece marka karmasi sonucu bozmaz.
    """
    per_brand: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for d in data:
        if d[key]:
            per_brand[d["brand"]][d[key]].append(d["price"])
    ratios: dict[str, list[float]] = defaultdict(list)
    for brand, groups in per_brand.items():
        base = groups.get(reference)
        if not base or len(base) < MIN_GROUP:
            continue
        base_med = statistics.median(base)
        for value, prices in groups.items():
            if len(prices) >= MIN_GROUP and base_med > 0:
                ratios[value].append(statistics.median(prices) / base_med)
    return {v: round(statistics.median(r), 3) for v, r in ratios.items() if len(r) >= 2}


def model_candidates(data: list[dict], brand: str, top: int = 15) -> list[tuple[str, int]]:
    """Marka basliklarinda sik tekrarlayan kelime/ikili: model adayi."""
    counts: Counter = Counter()
    brand_words = set(_WORD.findall(brand))
    for d in data:
        if d["brand"] != brand or not d["title"]:
            continue
        words = [w for w in _WORD.findall(d["title"])
                 if w not in STOP and w not in brand_words and not w.isdigit() and len(w) > 2]
        counts.update(set(words))
        counts.update({f"{a} {b}" for a, b in zip(words, words[1:])})
    return [(w, c) for w, c in counts.most_common(top) if c >= 3]


def model_base(data: list[dict], brand: str, model: str, cond_f, market_f, size_f) -> dict | None:
    """Modelin taban fiyati: her ilani kendi carpanlarina bolup ortancasini al."""
    vals = []
    for d in data:
        if d["brand"] != brand or model not in d["title"]:
            continue
        divisor = cond_f.get(d["cond"], 1.0) * market_f.get(d["market"], 1.0) * size_f.get(d["size"], 1.0)
        if divisor > 0:
            vals.append(d["price"] / divisor)
    if len(vals) < MIN_MODEL:
        return None
    vals.sort()
    return {
        "n": len(vals),
        "taban": round(statistics.median(vals), 1),
        "p25": round(vals[len(vals) // 4], 1),
        "p75": round(vals[3 * len(vals) // 4], 1),
        "dagilim": round((vals[3 * len(vals) // 4] - vals[len(vals) // 4]) / statistics.median(vals), 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Fiyat iskeleti olcumu")
    ap.add_argument("--brand", help="tek markanin model tablosu")
    args = ap.parse_args()

    conn = connect()
    data = samples(conn)
    print(f"ornek havuzu: {len(data)} ilan, {len({d['brand'] for d in data})} marka\n")
    if len(data) < 100:
        print("UYARI: ornek sayisi cok dusuk, carpanlar guvenilir degil.\n")

    cond_f = ratio_factor(data, "cond", REFERENCE_CONDITION)
    market_f = ratio_factor(data, "market", REFERENCE_MARKET)
    size_f = ratio_factor(data, "size", "M")
    print(f"KONDISYON carpanlari (referans: {REFERENCE_CONDITION}=1.0)")
    for k, v in sorted(cond_f.items(), key=lambda x: -x[1]):
        print(f"   {k:16} {v}")
    print(f"\nPAZAR carpanlari (referans: {REFERENCE_MARKET}=1.0)")
    for k, v in sorted(market_f.items(), key=lambda x: -x[1]):
        print(f"   {k:16} {v}")
    print("\nBEDEN carpanlari (referans: M=1.0)")
    for k, v in sorted(size_f.items(), key=lambda x: -x[1]):
        print(f"   {k:16} {v}")

    brands = [args.brand.lower()] if args.brand else [
        b for b, c in Counter(d["brand"] for d in data).most_common(8)]
    for brand in brands:
        print(f"\n=== {brand.upper()} model adaylari")
        for model, count in model_candidates(data, brand):
            base = model_base(data, brand, model, cond_f, market_f, size_f)
            if base:
                print(f"   {model:26} n={base['n']:3}  taban={base['taban']:7} €  "
                      f"P25={base['p25']:6} P75={base['p75']:6}  dagilim={base['dagilim']}")
            else:
                print(f"   {model:26} gecen={count:3}  (taban icin yetersiz veri)")


if __name__ == "__main__":
    main()
