#!/usr/bin/env python3
"""
Gozlem verisinden fiyat iskeletini cikarir. Hicbir seye karar vermez, sadece olcer.

MANTIK: Fiyat ~ Taban(marka+model) x Kondisyon x Pazar x Beden
Taban her model icin ayridir ama carpanlar TUM modellerde ortaktir. Carpanlar butun
veriden (binlerce ilan) hesaplanir, model tabani o carpanlara bolunerek 5-10 ilanla bile
cikarilabilir. Carpanlar ortanca oranlarla hesaplanir: birkac aykiri ilan sonucu bozmasin.

Komutlar (her biri kisa cikti verir):
    analyze.py                    carpanlar (kondisyon / pazar / beden)
    analyze.py --kapsam           marka basina modele eslesen ilan orani      [B2 saglama]
    analyze.py --modeller Nike    markanin model tablosu: n, taban, P25/P75, satis
    analyze.py --kesif Nike       sozlukte OLMAYAN sik gecen adaylar (sozlugu guncel tutmak icin)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import statistics
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "observe.db")
MODELS_FILE = os.path.join(BASE_DIR, "models.json")
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"

MIN_GROUP = 8          # bir carpan icin gereken en az ilan sayisi
MIN_MODEL = 8          # model tabani icin gereken en az ilan sayisi
REFERENCE_CONDITION = "cok_iyi"
REFERENCE_MARKET = "DE"


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))


def norm_text(text: str) -> str:
    """Kucuk harf, aksansiz, tire/nokta/alt cizgi bosluk: 'Omni-Heat' == 'omni heat'."""
    t = strip_accents((text or "").lower())
    t = re.sub(r"[-_./+]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# Kondisyonlarin diller arasi karsiligi. Anahtarlar norm_text ile karsilastirilir.
CONDITION_MAP = {
    "neu, mit etikett": "yeni_etiketli", "neuf avec etiquette": "yeni_etiketli",
    "nuovo con cartellino": "yeni_etiketli", "nieuw met prijskaartje": "yeni_etiketli",
    "ny med prislapp": "yeni_etiketli",
    "neu": "yeni", "neuf sans etiquette": "yeni", "nuovo senza cartellino": "yeni",
    "nieuw zonder prijskaartje": "yeni", "ny utan prislapp": "yeni",
    "sehr gut": "cok_iyi", "tres bon etat": "cok_iyi", "ottime": "cok_iyi", "ottime condizioni": "cok_iyi",
    "heel goed": "cok_iyi", "mycket bra": "cok_iyi", "mycket bra skick": "cok_iyi",
}
CONDITION_MAP = {norm_text(k): v for k, v in CONDITION_MAP.items()}


def norm_condition(raw: str | None) -> str | None:
    return CONDITION_MAP.get(norm_text(raw or ""))


def size_group(raw: str | None) -> str | None:
    s = (raw or "").upper()
    for tag in ("XXL", "XXS", "XS", "XL", "S", "M", "L"):
        if re.search(rf"\b{tag}\b", s):
            return tag
    return None


# ----------------------------------------------------------------- kur (ECB)

def _tls_context():
    """
    Windows'taki Python'da sertifika deposu eksik olabiliyor (PC'de ECB istegi bu yuzden
    dusuyordu). Varsa certifi paketi kullanilir; dogrulama hicbir durumda kapatilmaz.
    """
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fx_rates(conn: sqlite3.Connection) -> dict[str, float]:
    """
    ECB gunluk referans kurlari: 1 EUR = X birim. Gunde bir kez indirilir, meta'da saklanir.
    Indirilemezse son kayitli kur kullanilir ve bu ACIKCA yazdirilir.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = conn.execute("SELECT value FROM meta WHERE key='fx_rates'").fetchone()
    cached = json.loads(row[0]) if row else None
    if cached and cached.get("day") == today:
        return cached["rates"]
    try:
        with urllib.request.urlopen(ECB_URL, timeout=20, context=_tls_context()) as resp:
            root = ET.fromstring(resp.read())
        rates = {"EUR": 1.0}
        for node in root.iter():
            if node.get("currency") and node.get("rate"):
                rates[node.get("currency")] = float(node.get("rate"))
        conn.execute("INSERT INTO meta (key, value) VALUES ('fx_rates', ?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (json.dumps({"day": today, "rates": rates}),))
        conn.commit()
        return rates
    except Exception as exc:
        if cached:
            print(f"UYARI: ECB kuru alinamadi ({type(exc).__name__}), {cached['day']} kuru kullaniliyor")
            return cached["rates"]
        print(f"UYARI: ECB kuru alinamadi, EUR disi ilanlar disarida birakildi")
        return {"EUR": 1.0}


# ----------------------------------------------------------------- urun tipi (dilden bagimsiz)
# Ikinci el mont basliklarinda model adi nadirdir, TIP neredeyse her zaman yazilir
# (doudoune, polaire, parka...). Model yoksa fiyati en cok ayristiran bilgi tiptir.
TYPES = {
    "kaz_tuyu":   ["doudoune", "daunenjacke", "daunen", "piumino", "donsjas", "donsjasje", "dunjacka", "puffer",
                   "pufferjacke", "down jacket", "plumifero", "steppjacke", "doudoune sans manche"],
    "kislik":     ["winterjacke", "winterjas", "giubbotto invernale", "giacca invernale", "veste d hiver",
                   "veste hiver", "vinterjacka", "winter jacket", "wintercoat"],
    "deri":       ["lederjacke", "veste en cuir", "giacca di pelle", "giubbotto di pelle", "leren jas",
                   "skinnjacka", "leather jacket", "biker", "perfecto", "echtleder"],
    "kayak":      ["skijacke", "giacca da sci", "veste de ski", "ski jacket", "skijas", "skidjacka",
                   "snowboardjacke", "snowboard"],
    "polar":      ["polaire", "fleece", "fleecejacke", "pile", "teddy", "sherpa", "fleecepullover"],
    "parka":      ["parka", "winterparka"],
    "yagmurluk":  ["regenjacke", "impermeable", "impermeabile", "regenjas", "regnjacka", "hardshell",
                   "waterproof", "rain jacket"],
    "softshell":  ["softshell", "softshelljacke"],
    "ruzgarlik":  ["windbreaker", "coupe vent", "windjacke", "giacca a vento", "windjack", "vindjacka",
                   "k way", "anorak"],
    "yelek":      ["weste", "gilet", "smanicato", "bodywarmer", "vast", "sans manches", "sans manche", "vest"],
    "kaban":      ["mantel", "manteau", "manteaux", "cappotto", "trenchcoat", "trench", "wintermantel", "coat"],
    "bomber":     ["bomber", "bomberjacke", "blouson aviateur", "college jacke", "varsity"],
    "esofman":    ["trainingsjacke", "track jacket", "track top", "survetement", "veste de survetement",
                   "tuta", "trainingsanzug"],
    "kot_ceket":  ["jeansjacke", "veste en jean", "veste en denim", "denim jacket", "giacca di jeans", "spijkerjas",
                   "jeansjacka", "giubbotto di jeans", "denim", "jeans jacke"],
    "kapusonlu":  ["hoodie", "kapuzenpullover", "sweat a capuche", "felpa con cappuccio", "huvtroja", "hoody"],
    "sweatshirt": ["sweatshirt", "sweat", "felpa", "crewneck", "rundhals sweat"],
    "triko":      ["strickpullover", "pull en laine", "maglione", "gebreide trui", "stickad troja", "cardigan",
                   "strickjacke", "knit", "laine", "wolle", "wool", "cashmere", "kaschmir", "torsade",
                   "pullover", "pulli", "pull", "trui", "troja", "jumper"],
    "sneaker":    ["sneaker", "sneakers", "baskets", "turnschuhe", "turnschuh", "scarpe da ginnastica",
                   "sportschoenen", "gympaskor", "trainers"],
    "bot":        ["stiefel", "boots", "bottes", "bottines", "stivali", "stivaletti", "laarzen", "kangor",
                   "boot", "chelsea boots", "schnurstiefel"],
    "kosu":       ["laufschuhe", "running", "chaussures de course", "scarpe da corsa", "hardloopschoenen",
                   "lopskor", "runner"],
    "trekking":   ["wanderschuhe", "randonnee", "trekking", "hiking", "wandelschoenen", "vandringskangor"],
    "sandalet":   ["sandalen", "sandales", "sandali", "sandaler", "slides", "pantoletten", "claquettes", "ciabatte"],
}
_TYPE_PATS = sorted(
    [(re.compile(rf"(?<![a-z0-9]){re.escape(norm_text(a))}(?![a-z0-9])"), len(norm_text(a)), t)
     for t, aliases in TYPES.items() for a in aliases],
    key=lambda p: -p[1],
)


def match_type(title_norm: str) -> str | None:
    return next((t for pat, _, t in _TYPE_PATS if pat.search(title_norm)), None)


# ----------------------------------------------------------------- model sozlugu

class ModelMatcher:
    """
    Marka icinde baslik -> model. En uzun eslesen yazim kazanir ('retro nuptse' > 'nuptse',
    'air max 90' > 'air max'). Model yoksa seri (Omni-Heat, GORE-TEX) atanir.
    """

    def __init__(self, path: str = MODELS_FILE):
        raw = json.load(open(path, encoding="utf-8"))
        self.by_brand: dict[str, dict[str, list[tuple[re.Pattern, int, str]]]] = {}
        self.code_pats: dict[str, list[re.Pattern]] = {}
        for brand, spec in raw.items():
            if brand.startswith("_"):
                continue
            self.code_pats[brand.lower()] = [re.compile(p) for p in spec.get("codes", [])]
            entry = {}
            for kind in ("models", "lines"):
                pats = []
                for canonical, aliases in spec.get(kind, {}).items():
                    for alias in aliases:
                        a = norm_text(alias)
                        if a:
                            pats.append((re.compile(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])"), len(a), canonical))
                pats.sort(key=lambda p: -p[1])
                entry[kind] = pats
            self.by_brand[brand.lower()] = entry
        self.raw = raw

    def match(self, brand: str, title: str) -> tuple[str | None, str | None]:
        spec = self.by_brand.get(brand.lower())
        if not spec or not title:
            return None, None
        t = norm_text(title)
        model = next((c for pat, _, c in spec["models"] if pat.search(t)), None)
        line = next((c for pat, _, c in spec["lines"] if pat.search(t)), None)
        return model, line

    def code(self, brand: str, *texts: str | None) -> str | None:
        """
        Stil kodu: renk dahil birebir kimlik (CW2288-111 = AF1 beyaz). Bosluk/tire farki
        ayni kod sayilir. Bulunan ilk kod doner; metinler baslik, aciklama sirasiyla verilir.
        """
        for text in texts:
            if not text:
                continue
            up = text.upper()
            for pat in self.code_pats.get(brand.lower(), []):
                m = pat.search(up)
                if m:
                    return re.sub(r"[\s]", "-", m.group(0))
        return None

    def canonical_models(self, brand: str) -> list[str]:
        for b, spec in self.raw.items():
            if b.lower() == brand.lower():
                return list(spec.get("models", {}))
        return []


# ----------------------------------------------------------------- veri

def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DB_FILE)
    conn.row_factory = sqlite3.Row
    # PC arsivinde meta tablosu yok: kur onbellegi icin gerekli
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    return conn


# PC arsivinde anlamsiz olan (sunucu isletimine ait) testler: analizi durdurmaz
OPERATIONAL_CHECKS = {"T6", "T8", "T9", "T10", "T13"}


def samples(conn: sqlite3.Connection, matcher: ModelMatcher, rates: dict[str, float]) -> tuple[list[dict], Counter]:
    rows = conn.execute(
        "SELECT cell, title, size, condition, price, country, COALESCE(currency,'EUR') currency "
        "FROM catalog_samples WHERE is_child=0 AND price > 0"
    ).fetchall()
    out, unknown_cond = [], Counter()
    for r in rows:
        cond = norm_condition(r["condition"])
        if not cond:
            unknown_cond[r["condition"]] += 1
            continue
        rate = rates.get(r["currency"])
        if not rate:
            continue
        brand, category, _ = (r["cell"].split("|") + ["", ""])[:3]
        if category.startswith("model:"):
            category = "model"      # B3 dar arama hucreleri tek grupta
        model, line = matcher.match(brand, r["title"] or "")
        title_n = norm_text(r["title"] or "")
        out.append({
            "brand": brand.lower(), "category": category, "title": title_n,
            "cond": cond, "market": r["country"], "size": size_group(r["size"]),
            "price": float(r["price"]) / rate, "model": model, "line": line, "type": match_type(title_n),
            "code": matcher.code(brand, r["title"]),
        })
    return out, unknown_cond


def ratio_factor(data: list[dict], key: str, reference: str) -> dict[str, tuple[float, int]]:
    """
    Bir boyutun carpani: her (marka, kategori) grubunda o boyutun ortanca fiyati referansa
    bolunur, gruplar arasi ortanca alinir. Kategori ayrimi sart: ayakkabi ile montu karistirmak
    kondisyon carpanini kategori karisimina gore kaydirirdi.
    """
    per_group: dict[tuple, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for d in data:
        if d[key]:
            per_group[(d["brand"], d["category"])][d[key]].append(d["price"])
    ratios: dict[str, list[float]] = defaultdict(list)
    counts: Counter = Counter()
    for groups in per_group.values():
        base = groups.get(reference)
        if not base or len(base) < MIN_GROUP:
            continue
        base_med = statistics.median(base)
        for value, prices in groups.items():
            if len(prices) >= MIN_GROUP and base_med > 0:
                ratios[value].append(statistics.median(prices) / base_med)
                counts[value] += len(prices)
    return {v: (round(statistics.median(r), 3), counts[v]) for v, r in ratios.items() if len(r) >= 2}


def factors(data):
    return (ratio_factor(data, "cond", REFERENCE_CONDITION),
            ratio_factor(data, "market", REFERENCE_MARKET),
            ratio_factor(data, "size", "M"))


def normalized_prices(rows: list[dict], cond_f, market_f, size_f) -> list[float]:
    vals = []
    for d in rows:
        div = (cond_f.get(d["cond"], (1.0, 0))[0] * market_f.get(d["market"], (1.0, 0))[0]
               * size_f.get(d["size"], (1.0, 0))[0])
        if div > 0:
            vals.append(d["price"] / div)
    return sorted(vals)


def band(vals: list[float]) -> dict:
    med = statistics.median(vals)
    p25, p75 = vals[len(vals) // 4], vals[3 * len(vals) // 4]
    return {"n": len(vals), "taban": round(med, 1), "p25": round(p25, 1), "p75": round(p75, 1),
            "dagilim": round((p75 - p25) / med, 2) if med else None}


def grade(b: dict) -> str:
    if b["n"] >= 20 and b["dagilim"] is not None and b["dagilim"] <= 0.5:
        return "A"
    if b["n"] >= MIN_MODEL and b["dagilim"] is not None and b["dagilim"] <= 0.8:
        return "B"
    return "C"


def sold_by_model(conn: sqlite3.Connection, matcher: ModelMatcher) -> Counter:
    out: Counter = Counter()
    for r in conn.execute("SELECT cell, title FROM listings WHERE state='sold' AND title IS NOT NULL"):
        brand = r["cell"].split("|")[0]
        model, _ = matcher.match(brand, r["title"])
        if model:
            out[(brand.lower(), model)] += 1
    return out


# ----------------------------------------------------------------- raporlar

def report_factors(data, unknown_cond):
    cond_f, market_f, size_f = factors(data)
    for title, f, ref in (("KONDISYON", cond_f, REFERENCE_CONDITION), ("PAZAR", market_f, REFERENCE_MARKET),
                          ("BEDEN", size_f, "M")):
        print(f"{title} (referans {ref}=1.0): " +
              "  ".join(f"{k}={v[0]}(n{v[1]})" for k, v in sorted(f.items(), key=lambda x: -x[1][0])))
    if unknown_cond:
        print("TANINMAYAN kondisyon etiketi (sozluge eklenmeli):",
              ", ".join(f"{k}={v}" for k, v in unknown_cond.most_common(6)))


def report_coverage(data, matcher, conn=None):
    coded = [d for d in data if d["code"]]
    shoes = [d for d in data if d["category"] == "schuhe"]
    print(f"STIL KODU (baslikta): {len(coded)} ilan | ayakkabida %"
          f"{100*sum(1 for d in shoes if d['code'])/max(len(shoes),1):.0f} (n{len(shoes)})"
          + (f" | ornek: {', '.join(sorted({d['code'] for d in coded})[:6])}" if coded else ""))
    if conn is not None:
        rows = conn.execute("SELECT cell, title, description FROM listings WHERE description IS NOT NULL").fetchall()
        hit = sum(1 for r in rows if matcher.code(r["cell"].split("|")[0], r["title"], r["description"]))
        print(f"STIL KODU (baslik+aciklama, takipteki ilanlar): {hit}/{len(rows)}")
    by_brand: dict[str, list[dict]] = defaultdict(list)
    for d in data:
        by_brand[d["brand"]].append(d)
    rows = []
    for brand, items in by_brand.items():
        n = len(items)
        m = sum(1 for d in items if d["model"])
        l = sum(1 for d in items if not d["model"] and d["line"])
        t = sum(1 for d in items if not d["model"] and not d["line"] and d["type"])
        hit_models = {d["model"] for d in items if d["model"]}
        rows.append((brand, n, m, l, t, len(hit_models), len(matcher.canonical_models(brand))))
    rows.sort(key=lambda r: -r[1])
    tot = sum(r[1] for r in rows) or 1
    tm, tl, tt = (sum(r[i] for r in rows) for i in (2, 3, 4))
    defined = tm + tl + tt
    print(f"KAPSAM: {tot} ilan | model %{100*tm/tot:.0f}  seri %{100*tl/tot:.0f}  tip %{100*tt/tot:.0f}"
          f"  => tanimli %{100*defined/tot:.0f}  (gecme olcutu: tanimli %60)")
    by_cat = defaultdict(lambda: [0, 0])
    for d in data:
        by_cat[d["category"]][0] += 1
        by_cat[d["category"]][1] += bool(d["model"])
    print("kategoriye gore model orani: " + "  ".join(f"{c} %{100*v[1]/v[0]:.0f}(n{v[0]})" for c, v in by_cat.items()))
    print(f"{'marka':20}{'ilan':>6}{'model':>7}{'seri':>6}{'tip':>6}{'tanimsiz':>9}{'goruleN':>9}")
    for brand, n, m, l, t, hit, total in rows[:30]:
        print(f"{brand:20}{n:>6}{100*m/n:>6.0f}%{100*l/n:>5.0f}%{100*t/n:>5.0f}%{100*(n-m-l-t)/n:>8.0f}%"
              f"{hit:>5}/{total:<4}")


def report_models(data, matcher, conn, brand):
    cond_f, market_f, size_f = factors(data)
    sold = sold_by_model(conn, matcher)
    items = [d for d in data if d["brand"] == brand.lower()]
    groups: dict[str, list[dict]] = defaultdict(list)
    for d in items:
        if d["model"]:
            groups[d["model"]].append(d)
    print(f"{brand.upper()}: {len(items)} ilan, {sum(len(g) for g in groups.values())} modele eslesti")
    print(f"{'model':22}{'n':>5}{'taban':>8}{'P25':>7}{'P75':>7}{'dag.':>6}{'not':>4}{'satis':>6}")
    rows = []
    for model, g in groups.items():
        vals = normalized_prices(g, cond_f, market_f, size_f)
        if len(vals) < 3:
            continue
        b = band(vals)
        rows.append((model, b, grade(b) if b["n"] >= MIN_MODEL else "-", sold[(brand.lower(), model)]))
    for model, b, g, s in sorted(rows, key=lambda r: -r[1]["n"])[:25]:
        print(f"{model:22}{b['n']:>5}{b['taban']:>8}{b['p25']:>7}{b['p75']:>7}{str(b['dagilim']):>6}{g:>4}{s:>6}")

    # Model adi olmayan ilanlar icin bir alt kademe: marka x tip tabani
    types: dict[str, list[dict]] = defaultdict(list)
    for d in items:
        if not d["model"] and d["type"]:
            types[d["type"]].append(d)
    trows = []
    for t, g in types.items():
        vals = normalized_prices(g, cond_f, market_f, size_f)
        if len(vals) >= MIN_MODEL:
            b = band(vals)
            trows.append((t, b, grade(b)))
    if trows:
        print(f"-- model adi olmayanlar, TIP tabani --")
        for t, b, g in sorted(trows, key=lambda r: -r[1]["n"])[:12]:
            print(f"{t:22}{b['n']:>5}{b['taban']:>8}{b['p25']:>7}{b['p75']:>7}{str(b['dagilim']):>6}{g:>4}")
    missing = [m for m in matcher.canonical_models(brand) if m not in groups]
    if missing:
        print(f"hic gorulmeyen ({len(missing)}): {', '.join(missing[:12])}")


_WORD = re.compile(r"[a-z0-9]{2,}")
GENERIC = set("""
jacke veste giacca jas jacka schuhe chaussures scarpe schoenen skor pullover pull trui maglione troja
herren damen homme femme uomo donna heren dames dam herr unisex taille groesse grosse maat size taglia
neu neuf nuovo nieuw ny sehr gut tres bon etat zustand top vintage original schwarz noir nero zwart svart
weiss blanc bianco wit vit blau bleu blu blauw bla grau gris grigio grijs gra beige braun marron rot rouge
sneaker sneakers baskets turnschuhe stiefel boots bottes winter sommer hiver mit avec con met med und et
""".split())


def report_discovery(data, brand):
    """Sozlukte karsiligi olmayan basliklarda sik gecen kelime ikilileri: yeni model adayi."""
    counts: Counter = Counter()
    markets: dict[str, set] = defaultdict(set)
    bw = set(_WORD.findall(norm_text(brand)))
    type_words = {w for aliases in TYPES.values() for a in aliases for w in norm_text(a).split()}
    for d in data:
        if d["brand"] != brand.lower() or d["model"]:
            continue
        words = [w for w in _WORD.findall(d["title"])
                 if w not in GENERIC and w not in bw and w not in type_words]
        for term in set(words) | {f"{a} {b}" for a, b in zip(words, words[1:])}:
            counts[term] += 1
            markets[term].add(d["market"])
    cands = [(t, c) for t, c in counts.most_common(60) if c >= 5 and len(markets[t]) >= 2]
    print(f"{brand.upper()} sozluk disi adaylar (en az 5 ilan, en az 2 pazar):")
    print("  " + ", ".join(f"{t}({c})" for t, c in cands[:25]) if cands else "  yok")


MIN_SALES_GROUP = 8     # satis orani icin grupta gereken en az takipli ilan


def tracked(conn: sqlite3.Connection, matcher: ModelMatcher, rates: dict[str, float]) -> list[dict]:
    """Takip edilen ilanlar ve sonuclari. Tekrar yayinlar satis/kayip sayilmaz, disarida birakilir."""
    out = []
    for r in conn.execute(
            "SELECT cell, title, description, state, price, final_price, COALESCE(currency,'EUR') currency, "
            "days_to_close, COALESCE(close_uncertain,0) unc, close_window, favourites, condition, country "
            "FROM listings WHERE state IN ('active','sold','gone')"):
        brand, category, _ = (r["cell"].split("|") + ["", ""])[:3]
        if category.startswith("model:"):
            category = "model"
        rate = rates.get(r["currency"]) or 0
        if not rate:
            continue
        model, line = matcher.match(brand, r["title"] or "")
        price = (r["final_price"] if r["state"] == "sold" and r["final_price"] else r["price"]) or 0
        exact = r["state"] == "sold" and not r["unc"] and (r["close_window"] or 99) <= 7
        out.append({
            "brand": brand, "category": category, "model": model, "line": line,
            "type": match_type(norm_text(r["title"] or "")), "state": r["state"],
            "price": price / rate, "days": r["days_to_close"] if exact else None,
            "fav": r["favourites"] or 0, "cond": norm_condition(r["condition"]), "market": r["country"],
        })
    return out


def _sales_rows(items: list[dict], key) -> list[dict]:
    groups: dict = defaultdict(list)
    for d in items:
        k = key(d)
        if k:
            groups[k].append(d)
    rows = []
    for k, g in groups.items():
        n = len(g)
        if n < MIN_SALES_GROUP:
            continue
        sold = [d for d in g if d["state"] == "sold"]
        gone = sum(1 for d in g if d["state"] == "gone")
        days = sorted(d["days"] for d in sold if d["days"] is not None)
        prices = sorted(d["price"] for d in sold)
        rows.append({
            "key": k, "n": n, "sold": len(sold), "rate": len(sold) / n,
            "close_share": len(sold) / max(len(sold) + gone, 1),
            "days": statistics.median(days) if days else None, "n_days": len(days),
            "price": statistics.median(prices) if prices else None,
            "fav": statistics.median(d["fav"] for d in g),
        })
    rows.sort(key=lambda r: (-r["rate"], -r["sold"]))
    return rows


def _print_sales(title: str, rows: list[dict], limit: int) -> None:
    print(f"\n{title}")
    print(f"{'':30}{'takip':>6}{'satis':>6}{'oran':>6}{'gun':>6}{'(n)':>5}{'fiyat':>8}{'fav':>5}")
    for r in rows[:limit]:
        label = " · ".join(str(x) for x in r["key"]) if isinstance(r["key"], tuple) else str(r["key"])
        days = f"{r['days']:.1f}" if r["days"] is not None else "-"
        price = f"{r['price']:.0f}€" if r["price"] is not None else "-"
        print(f"{label[:30]:30}{r['n']:>6}{r['sold']:>6}{r['rate']*100:>5.0f}%{days:>6}{r['n_days']:>5}"
              f"{price:>8}{r['fav']:>5.0f}")


def report_sales(conn, matcher, rates) -> None:
    """
    Gercek sonuclardan siralama: takibe alinan ilanin ne kadari satildi, kac gunde, kaca.
    Oran = satilan / takip edilen. Gun yalnizca satis ani kesin bilinen satislardan.
    Grupta en az MIN_SALES_GROUP takipli ilan yoksa grup gosterilmez (sans eseri sonuc olmasin).
    """
    items = tracked(conn, matcher, rates)
    sold = sum(1 for d in items if d["state"] == "sold")
    exact = sum(1 for d in items if d["days"] is not None)
    first = conn.execute("SELECT MIN(first_seen) FROM listings").fetchone()[0]
    print(f"SATIS RAPORU: {len(items)} takipli ilan, {sold} satis ({exact} tanesinde satis gunu kesin) | "
          f"ilk kayit {first[:10] if first else '-'}")
    print("Uyari: oran, takip suresi farkli ilanlari karsilastirir; erken veri, yon gosterir, kesin degildir.")
    _print_sales("MARKA", _sales_rows(items, lambda d: d["brand"]), 15)
    _print_sales("KATEGORI", _sales_rows(items, lambda d: d["category"]), 6)
    _print_sales("MARKA x TIP (model adi olmayanlar dahil)",
                 _sales_rows(items, lambda d: (d["brand"], d["type"]) if d["type"] else None), 15)
    _print_sales("MARKA x MODEL", _sales_rows(items, lambda d: (d["brand"], d["model"]) if d["model"] else None), 10)
    _print_sales("PAZAR", _sales_rows(items, lambda d: d["market"]), 7)
    _print_sales("KONDISYON", _sales_rows(items, lambda d: d["cond"]), 3)


PLAN_FILE = os.path.join(BASE_DIR, "model_cells.json")
PLAN_PER_TIER = {"core": 3, "watch": 1}


def write_plan(data, matcher) -> None:
    """
    B3 dar arama plani: her markadan veride en cok gorulen modeller (en az 3 ilan),
    yer kalirsa sozlugun basindaki (en bilinen) modellerle tamamlanir. Gozlemci bu dosyayi
    okuyup bu modelleri tum pazarlarda ayrica arar: gercek arz sayisi + yogun emsal.
    """
    cfg = json.load(open(os.path.join(BASE_DIR, "config.json"), encoding="utf-8"))
    seen = Counter((d["brand"], d["model"]) for d in data if d["model"])
    plan = []
    for tier, per_brand in PLAN_PER_TIER.items():
        for brand in cfg["brands"].get(tier, []):
            observed = [m for (b, m), c in seen.most_common() if b == brand.lower() and c >= 3]
            chosen = observed[:per_brand]
            for m in matcher.canonical_models(brand):
                if len(chosen) >= per_brand:
                    break
                if m not in chosen:
                    chosen.append(m)
            search = cfg.get("brand_search", {}).get(brand, brand)
            for m in chosen:
                plan.append({"brand": brand, "model": m, "query": f"{search} {m}",
                             "kaynak": "veri" if m in observed else "sozluk"})
    json.dump({"olusturma": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "hucreler": plan},
              open(PLAN_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    by_src = Counter(p["kaynak"] for p in plan)
    print(f"PLAN: {len(plan)} model ({by_src['veri']} veriden, {by_src['sozluk']} sozlukten) -> {PLAN_FILE}")
    print("  " + ", ".join(p["query"] for p in plan[:15]) + " ...")


def main() -> None:
    ap = argparse.ArgumentParser(description="Fiyat iskeleti olcumu")
    ap.add_argument("--kapsam", action="store_true")
    ap.add_argument("--modeller", metavar="MARKA")
    ap.add_argument("--kesif", metavar="MARKA")
    ap.add_argument("--plan", action="store_true", help="B3 dar arama planini yaz (model_cells.json)")
    ap.add_argument("--satislar", action="store_true", help="gercek satis sonuclarina gore siralama")
    ap.add_argument("--zorla", action="store_true", help="durdurucu saglama hatasina ragmen calis")
    ap.add_argument("--db", default=os.environ.get("TATANGA_DB"),
                    help="veritabani yolu (PC arsivi icin: <tatanga>/istatistik/arsiv.db)")
    args = ap.parse_args()

    conn = connect(args.db)
    pc_mode = bool(args.db)
    from saglama import FAIL, run_checks
    blockers = [(code, text) for lvl, code, text in run_checks(conn) if lvl == FAIL
                and not (pc_mode and code in OPERATIONAL_CHECKS)]
    if blockers and not args.zorla:
        print("ANALIZ DURDURULDU — saglama testleri gecmedi:")
        for code, text in blockers:
            print(f"   {code} {text}")
        return

    matcher = ModelMatcher()
    rates = fx_rates(conn)
    data, unknown_cond = samples(conn, matcher, rates)
    print(f"havuz: {len(data)} ilan | kur: SEK={rates.get('SEK', '-')}")

    if args.kapsam:
        report_coverage(data, matcher, conn)
    elif args.modeller:
        report_models(data, matcher, conn, args.modeller)
    elif args.kesif:
        report_discovery(data, args.kesif)
    elif args.plan:
        write_plan(data, matcher)
    elif args.satislar:
        report_sales(conn, matcher, rates)
    else:
        report_factors(data, unknown_cond)


if __name__ == "__main__":
    main()
