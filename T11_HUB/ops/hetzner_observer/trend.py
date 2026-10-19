#!/usr/bin/env python3
"""
TREND + ONCULUK (eldeki veriyle, bekleme yok). PC'de calisir; arsivleri yalniz OKUR.

    python trend.py [--arsiv <arsiv.db>] [--alis <alis_arsiv.db>] [--csv <klasor>]

NE OLCULUR (her olcu kazima cabasindan BAGIMSIZ secildi; ham ilan sayisi bizim ne kadar taradigimiza bagli
oldugundan trend sayilmaz):
  fiyat   : yeni ilanlarin medyan fiyati (Vinted / Kleinanzeigen / eBay / Sellpy). Kondisyon karisimi degisince
            medyan yanlis oynamasin diye marka x kategori x KONDISYON katmaninda olculur, katmanlar birlestirilir.
  satis7  : Vinted'de takibe giren ilanlarin 7 gun icinde satilma orani (giris penceresine gore kohort).
            7 gunu tamamlamadan izi kaybolan ilan paydaya girmez (sansur).
Pencere: her kaynagin SON VERI GUNU D'ye gore [D-6, D] ("son 7") ve [D-13, D-7] ("onceki 7"). Tarihler cikti da yazar.
Guven: degisimin %90 bootstrap araligi 1'i (degisim yok) disarida birakiyor VE her iki pencerede >= 30 olcum ->
"guclu"; >= 15 olcum -> "orta"; aksi "zayif". Zayif trend karar sinyali DEGILDIR.
Fiyatta bir haftalik degisim x0,67 - x1,5 disindaysa "karisim degisimi (trend degil)": penceredeki urun karisimi
degismistir (ayni model adi altinda mont/pantolon, luks markada farkli urunler), piyasa fiyati degil.

ONCULUK (Wikipedia ilgisi -> ikinci el talebi):
  - wiki ilgi trendi: son 7 / onceki 7 gun ve gecen yilin ayni gunleri (365 gunluk gecmis var).
  - test: markalar arasi Spearman korelasyonu (wiki yillik ilgi degisimi <-> Vinted 7 gun satis orani ve eBay sifir
    urun talebi), permutasyon p-degeri ile. ZAMAN GECIKMELI test (ilgi once mi artiyor?) icin en az 8 haftalik
    kesintisiz satis serisi gerekir; eldeki seri bundan kisa -> rapor "henuz test edilemez" der, uydurmaz.
Cikti: capraz.db -> trend, onculuk tablolari; trend.csv, onculuk.csv.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import random
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import analyze as A  # noqa: E402
import capraz as C  # noqa: E402
import motor as M  # noqa: E402

ROOT = C.ROOT
MIN_STRATUM = 5           # katman basina pencere basina en az ilan
BOOT = 400
STRONG_N, MID_N = 30, 15
LAG_WEEKS_NEED = 8
FMT = "%Y-%m-%d"
random.seed(7)


def windows(last_day: str) -> tuple[tuple[str, str], tuple[str, str]]:
    d = datetime.strptime(last_day[:10], FMT)
    son = ((d - timedelta(days=6)).strftime(FMT), d.strftime(FMT))
    onc = ((d - timedelta(days=13)).strftime(FMT), (d - timedelta(days=7)).strftime(FMT))
    return onc, son


def which(day: str, onc, son) -> int | None:
    day = day[:10]
    if onc[0] <= day <= onc[1]:
        return 0
    if son[0] <= day <= son[1]:
        return 1
    return None


MIX_LIMIT = (0.67, 1.5)    # bir haftada bundan buyuk medyan fiyat degisimi piyasa trendi degil, urun karisimi degisimidir


def label(n0: int, n1: int, lo: float | None, hi: float | None, change: float | None = None,
          price: bool = False) -> str:
    if price and change is not None and not (MIX_LIMIT[0] <= change <= MIX_LIMIT[1]):
        return "karisim degisimi (trend degil)"
    sig = lo is not None and (lo > 1 or hi < 1)
    if min(n0, n1) >= STRONG_N and sig:
        return "guclu"
    if min(n0, n1) >= MID_N and sig:
        return "orta"
    return "zayif"


def price_change(strata: dict) -> tuple | None:
    """strata: katman -> ([onceki fiyatlar], [son fiyatlar]). Katman log-oranlarinin agirlikli ortalamasi + bootstrap."""
    use = {k: v for k, v in strata.items() if len(v[0]) >= MIN_STRATUM and len(v[1]) >= MIN_STRATUM}
    if not use:
        return None

    def est(sample):
        num = den = 0.0
        for a, b in sample.values():
            w = min(len(a), len(b))
            num += w * math.log(statistics.median(b) / statistics.median(a))
            den += w
        return math.exp(num / den)

    point = est(use)
    # Bootstrap katman basina en fazla 150 cekilisle (medyanin belirsizligi icin yeterli; buyuk katmanda araligi
    # bir miktar GENISLETIR -> tutucu). Tum ornekle 400 tekrar dakikalar suruyordu.
    def draw(v):
        m = min(len(v), 150)
        return [random.choice(v) for _ in range(m)]
    boots = sorted(est({k: (draw(a), draw(b)) for k, (a, b) in use.items()}) for _ in range(200))
    n0 = sum(len(a) for a, _ in use.values())
    n1 = sum(len(b) for _, b in use.values())
    med0 = statistics.median([x for a, _ in use.values() for x in a])
    med1 = statistics.median([x for _, b in use.values() for x in b])
    return point, boots[10], boots[189], n0, n1, med0, med1, len(use)


def ratio_ci(k0: int, n0: int, k1: int, n1: int) -> tuple | None:
    """Iki oran (k/n) arasindaki oran degisimi, %90 araligi (log oran, delta yontemi; buyuk orneklerde hizli ve dogru)."""
    if not n0 or not n1 or not k0 or not k1:
        return None
    p0, p1 = k0 / n0, k1 / n1
    se = math.sqrt((1 - p0) / k0 + (1 - p1) / k1)
    r = p1 / p0
    return r, r * math.exp(-1.645 * se), r * math.exp(1.645 * se)


def spearman(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    n = len(xs)
    if n < 8:
        return None

    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        for pos, i in enumerate(order):
            r[i] = pos
        return r

    def rho(a, b):
        ma, mb = statistics.mean(a), statistics.mean(b)
        num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
        return num / den if den else 0.0

    rx, ry = ranks(xs), ranks(ys)
    r0 = rho(rx, ry)
    perm = sum(abs(rho(rx, random.sample(ry, n))) >= abs(r0) for _ in range(2000))
    return r0, (perm + 1) / 2001


# ---------------------------------------------------------------- kaynaklar
def vinted_items(conn, rates):
    """(gun, marka, grup, kondisyon, fiyat EUR) - Vinted katalog ornekleri (yeni ilanlar)."""
    for r in conn.execute("SELECT ts, cell, brand, condition, price, COALESCE(currency,'EUR') cur, size, is_child "
                          "FROM catalog_samples WHERE price > 0"):
        brand, cat, _ = (r["cell"].split("|") + ["", ""])[:3]
        if r["is_child"]:
            continue
        tier = A.norm_condition(r["condition"])
        rate = rates.get(r["cur"]) or 0
        if not tier or not rate:
            continue
        grp = cat.replace("model:", "model ") if cat.startswith("model:") else C.CAT_MAP.get(cat, cat)
        yield r["ts"], brand, grp, tier, r["price"] / rate


def alis_items(alis, rates):
    """
    (kaynak, yayin gunu, marka, grup, kondisyon, fiyat EUR). Tarih = platformun GERCEK yayin tarihi (eBay created,
    Sellpy first_offered, KA posted); bizim ilk gorme tarihimiz kazima takvimine bagli oldugundan kullanilmaz.
    HAYATTA KALMA YANLILIGI: eski pencerede yalniz satilmadan kalan (genelde pahali) ilanlar gorunur -> sahte fiyat
    dususu. Bu yuzden HER IKI pencerede de yalniz yayindan sonra <= 2 gun icinde yakalanan ilanlar sayilir.
    """
    fresh = "julianday(first_seen) - julianday({d}) <= 2"
    for r in alis.execute("SELECT posted d, brand, cat, zustand, COALESCE(detail_price, price) p FROM ka_ads "
                          "WHERE COALESCE(marke_ok,1)=1 AND posted IS NOT NULL AND " + fresh.format(d="posted")):
        tier = C.KA_COND.get((r["zustand"] or "").strip().lower())
        if tier and r["p"] and r["p"] >= C.BAIT_PRICE:
            yield "Kleinanzeigen", r["d"], r["brand"], r["cat"], tier, float(r["p"])
    for r in alis.execute("SELECT created d, brand, cat, condition_id, price, COALESCE(currency,'EUR') cur FROM eb_items "
                          "WHERE created IS NOT NULL AND " + fresh.format(d="created")):
        tier = C.EB_COND.get(str(r["condition_id"]))
        rate = rates.get(r["cur"]) or 0
        if tier and rate and r["price"]:
            yield "eBay", r["d"], r["brand"], r["cat"], tier, r["price"] / rate
    for r in alis.execute("SELECT first_offered d, brand, cat, condition, price FROM sp_items "
                          "WHERE COALESCE(brand_ok,1)=1 AND first_offered IS NOT NULL AND " + fresh.format(d="first_offered")):
        tier = C.SP_COND.get(r["condition"] or "")
        if tier and r["price"]:
            yield "Sellpy", r["d"], r["brand"], r["cat"], tier, float(r["price"])


def supply_trends(source: str, items: list[tuple]) -> list[dict]:
    """items: (gun, marka, grup, kondisyon, fiyat). Fiyat ve pay trendleri (marka x grup ve marka)."""
    if not items:
        return []
    last = max(i[0] for i in items)[:10]
    onc, son = windows(last)
    strata = defaultdict(lambda: defaultdict(lambda: ([], [])))   # anahtar -> katman -> (onceki, son)
    counts = defaultdict(lambda: [0, 0])
    totals = [0, 0]
    for day, brand, grp, tier, price in items:
        w = which(day, onc, son)
        if w is None or not brand:
            continue
        b = brand.strip()
        totals[w] += 1
        counts[b][w] += 1
        strata[(b, grp)][tier][w].append(price)
        strata[(b, "*")][(grp, tier)][w].append(price)
    out = []
    for (brand, grp), st in strata.items():
        pc = price_change(st)
        if pc:
            ch, lo, hi, n0, n1, m0, m1, ks = pc
            out.append({"kaynak": source, "olcu": "fiyat", "marka": brand, "grup": grp, "onceki": f"{onc[0]}..{onc[1]}",
                        "son": f"{son[0]}..{son[1]}", "deger_onceki": round(m0, 2), "deger_son": round(m1, 2),
                        "degisim": round(ch, 3), "ci_lo": round(lo, 3), "ci_hi": round(hi, 3), "n_onceki": n0,
                        "n_son": n1, "guven": label(n0, n1, lo, hi, ch, price=True), "aciklama": f"{ks} kondisyon katmani"})
    # "pay" olcusu 2026-10-19'da KALDIRILDI: markanin yeni ilan payi hangi hucrelerin o pencerede tarandigina
    # bagli (gozlemci kesintisinde Dr. Martens x70 gibi sahte trend uretti). Arz hizi icin hucre-ziyaret basina
    # yeni ilan olcusu gerekir; o zamana kadar yalniz fiyat ve satis orani raporlanir.
    return out


def sellthrough(conn) -> tuple[list[dict], dict]:
    """
    Vinted 7 gun satilma olasiligi, KAPLAN-MEIER ile (motor.py ile ayni kurallar): izi 7 gunden once kaybolan ilan
    o ana kadar risk altinda sayilir. (Ilk surum bu ilanlari paydadan atiyordu; gozlemci kesintisinde satilmayanlar
    duserken erken yakalanan satislar kaldi ve oran %18'den %61'e yapay sisti.)
    """
    rows = []
    for r in conn.execute("SELECT cell, first_seen, state, days_to_close, COALESCE(last_active_at, last_check) seen "
                          "FROM listings WHERE cohort IS NOT 'baseline' AND first_seen IS NOT NULL "
                          "AND state IN ('active','sold','gone','expired')"):
        if r["state"] == "sold":
            t, ev = r["days_to_close"], 1
        elif r["state"] == "gone":
            t, ev = r["days_to_close"], 0
        elif r["state"] == "expired":
            t, ev = 90.0, 0
        else:
            t, ev = M._days(r["first_seen"], r["seen"]), 0
        if t is None or t < 0:
            continue
        brand, cat, _ = (r["cell"].split("|") + ["", ""])[:3]
        cat = "model" if cat.startswith("model:") else C.CAT_MAP.get(cat, cat)
        rows.append((r["first_seen"][:10], brand, cat, {"t": max(t, 0.01), "event": ev}))
    overall = {}
    by_brand = defaultdict(list)
    for _, b, _, it in rows:
        by_brand[b.lower()].append(it)
    for b, its in by_brand.items():
        km = M.kaplan_meier(its)[7]
        if km["ok"]:
            overall[b] = (km["p"], len(its))
    if not rows:
        return [], overall
    onc, son = windows(max(r[0] for r in rows))
    agg = defaultdict(lambda: ([], []))
    for day, b, cat, it in rows:
        w = which(day, onc, son)
        if w is None:
            continue
        for key in ((b, "*"), (b, cat), ("*", "*")):
            agg[key][w].append(it)
    out = []
    for (b, cat), (a0, a1) in agg.items():
        if len(a0) < 10 or len(a1) < 10:
            continue
        k0, k1 = M.kaplan_meier(a0)[7], M.kaplan_meier(a1)[7]
        if not (k0["ok"] and k1["ok"]) or k0["p"] <= 0 or k1["p"] <= 0:
            continue
        ch = k1["p"] / k0["p"]
        se = math.sqrt((k0["half"] / 1.96 / k0["p"]) ** 2 + (k1["half"] / 1.96 / k1["p"]) ** 2)
        lo, hi = ch * math.exp(-1.645 * se), ch * math.exp(1.645 * se)
        out.append({"kaynak": "Vinted", "olcu": "satis7", "marka": b, "grup": cat, "onceki": f"{onc[0]}..{onc[1]}",
                    "son": f"{son[0]}..{son[1]}", "deger_onceki": round(k0["p"], 3), "deger_son": round(k1["p"], 3),
                    "degisim": round(ch, 3), "ci_lo": round(lo, 3), "ci_hi": round(hi, 3), "n_onceki": len(a0),
                    "n_son": len(a1), "guven": label(len(a0), len(a1), lo, hi),
                    "aciklama": "giris kohortu, Kaplan-Meier 7 gun satilma olasiligi"})
    return out, overall


def wiki(conn) -> tuple[list[dict], dict]:
    try:
        ents = {r["qid"]: r for r in conn.execute("SELECT * FROM wiki_entities")}
        views = defaultdict(lambda: defaultdict(int))
        for r in conn.execute("SELECT qid, day, SUM(views) v FROM wiki_views GROUP BY qid, day"):
            views[r["qid"]][r["day"]] += r["v"]
    except sqlite3.OperationalError:
        return [], {}
    out, per_brand = [], {}
    for qid, days in views.items():
        e = ents.get(qid)
        if not e or not days:
            continue
        last = datetime.strptime(max(days), FMT)

        def tot(a, b):
            return sum(days.get((last - timedelta(days=i)).strftime(FMT), 0) for i in range(a, b))

        s7, p7 = tot(0, 7), tot(7, 14)
        # gecen yilin ayni 7 gunu (mevsim etkisini ayirir)
        y7 = sum(days.get((last - timedelta(days=365 + i)).strftime(FMT), 0) for i in range(0, 7))
        name = f"{e['brand']}" + (f" {e['model']}" if e["model"] else "")
        yoy = (s7 / y7) if y7 else None
        out.append({"kaynak": "Wikipedia", "olcu": "ilgi", "marka": e["brand"], "grup": e["model"] or "*",
                    "onceki": "onceki 7 gun", "son": f"son 7 gun (..{last:%Y-%m-%d})", "deger_onceki": p7,
                    "deger_son": s7, "degisim": round(s7 / p7, 3) if p7 else None,
                    "ci_lo": None, "ci_hi": None, "n_onceki": p7, "n_son": s7,
                    "guven": "olcum (sayim)" if p7 >= 500 else "zayif (az goruntulenme)",
                    "aciklama": f"gecen yil ayni hafta {y7}" + (f", yillik x{yoy:.2f}" if yoy else "")})
        if e["kind"] == "marka" and yoy:
            per_brand[e["brand"].lower()] = (yoy, name)
    return out, per_brand


def sifir_demand(path: str) -> dict:
    try:
        db = sqlite3.connect(path)
        d = defaultdict(float)
        for marka, haftalik in db.execute("SELECT marka, haftalik_talep FROM sifir_talep"):
            d[marka.lower()] += haftalik
        return d
    except sqlite3.OperationalError:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arsiv", default=os.path.join(ROOT, "arsiv.db"))
    ap.add_argument("--alis", default=os.path.join(ROOT, "alis_arsiv.db"))
    ap.add_argument("--csv", metavar="KLASOR")
    args = ap.parse_args()
    conn = A.connect(args.arsiv)
    rates = A.fx_rates(conn)
    alis = sqlite3.connect(args.alis)
    alis.row_factory = sqlite3.Row

    rows = supply_trends("Vinted", list(vinted_items(conn, rates)))
    by_src = defaultdict(list)
    for src, *rest in alis_items(alis, rates):
        by_src[src].append(tuple(rest))
    for src, items in by_src.items():
        rows += supply_trends(src, items)
    st_rows, st_overall = sellthrough(conn)
    rows += st_rows
    wiki_rows, wiki_brand = wiki(conn)
    rows += wiki_rows

    # ---- onculuk: markalar arasi korelasyon
    sifir = sifir_demand(os.path.join(ROOT, "capraz.db"))
    onc_rows = []
    pairs = [(wiki_brand[b][0], p) for b, (p, n) in st_overall.items() if b in wiki_brand and n >= 20]
    sp = spearman([math.log(x) for x, _ in pairs], [y for _, y in pairs])
    onc_rows.append({"test": "wiki yillik ilgi degisimi <-> Vinted 7 gun satis orani (markalar arasi)", "n_marka": len(pairs),
                     "rho": round(sp[0], 3) if sp else None, "p": round(sp[1], 4) if sp else None,
                     "sonuc": ("anlamli" if sp and sp[1] < 0.05 else "anlamli degil") if sp else "olculemez (< 8 marka)"})
    pairs2 = [(wiki_brand[b][0], v) for b, v in sifir.items() if b in wiki_brand]
    sp2 = spearman([math.log(x) for x, _ in pairs2], [y for _, y in pairs2])
    onc_rows.append({"test": "wiki yillik ilgi degisimi <-> eBay sifir urun haftalik talebi (markalar arasi)",
                     "n_marka": len(pairs2), "rho": round(sp2[0], 3) if sp2 else None,
                     "p": round(sp2[1], 4) if sp2 else None,
                     "sonuc": ("anlamli" if sp2 and sp2[1] < 0.05 else "anlamli degil") if sp2 else "olculemez (< 8 marka)"})
    weeks = conn.execute("SELECT COUNT(DISTINCT strftime('%Y-%W', closed_at)) FROM listings WHERE state='sold'").fetchone()[0]
    onc_rows.append({"test": "zaman gecikmeli onculuk (ilgi satistan once mi artiyor?)", "n_marka": None, "rho": None,
                     "p": None, "sonuc": f"henuz test edilemez: satis serisi {weeks} hafta, gereken >= {LAG_WEEKS_NEED} "
                                         "kesintisiz hafta"})

    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    db = sqlite3.connect(os.path.join(ROOT, "capraz.db"))
    db.execute("DROP TABLE IF EXISTS trend")
    cols = ["kaynak", "olcu", "marka", "grup", "onceki", "son", "deger_onceki", "deger_son", "degisim", "ci_lo", "ci_hi",
            "n_onceki", "n_son", "guven", "aciklama"]
    db.execute(f"CREATE TABLE trend ({', '.join(c + ' TEXT' if c in ('kaynak','olcu','marka','grup','onceki','son','guven','aciklama') else c + ' REAL' for c in cols)}, ts TEXT)")
    db.executemany(f"INSERT INTO trend VALUES ({','.join('?' * (len(cols) + 1))})", [[r[c] for c in cols] + [ts] for r in rows])
    db.execute("DROP TABLE IF EXISTS onculuk")
    db.execute("CREATE TABLE onculuk (test TEXT, n_marka INTEGER, rho REAL, p REAL, sonuc TEXT, ts TEXT)")
    db.executemany("INSERT INTO onculuk VALUES (?,?,?,?,?,?)",
                   [(r["test"], r["n_marka"], r["rho"], r["p"], r["sonuc"], ts) for r in onc_rows])
    db.commit()

    print(f"TREND: {len(rows)} olcu satiri")
    for src in ("Vinted", "Kleinanzeigen", "eBay", "Sellpy", "Wikipedia"):
        sub = [r for r in rows if r["kaynak"] == src]
        strong = [r for r in sub if r["guven"] in ("guclu", "orta")]
        print(f"  {src:13} {len(sub):4} satir | guclu/orta {len(strong)}" + (f" | pencere {sub[0]['onceki']} -> {sub[0]['son']}" if sub else ""))
        for r in sorted(strong, key=lambda r: -abs(math.log(r["degisim"] or 1)))[:6]:
            print(f"     {r['olcu']:7} {r['marka'][:16]:16} {str(r['grup'])[:16]:16} x{r['degisim']:.2f} "
                  f"[{r['ci_lo']}-{r['ci_hi']}] n {r['n_onceki']}/{r['n_son']} {r['guven']}")
    print("ONCULUK:")
    for r in onc_rows:
        print(f"  {r['test']}: n={r['n_marka']} rho={r['rho']} p={r['p']} -> {r['sonuc']}")
    if args.csv:
        os.makedirs(args.csv, exist_ok=True)
        for name, data, keys in (("trend.csv", rows, cols), ("onculuk.csv", onc_rows, ["test", "n_marka", "rho", "p", "sonuc"])):
            with open(os.path.join(args.csv, name), "w", encoding="utf-8-sig", newline="") as fh:
                w = csv.writer(fh, delimiter=";")
                w.writerow(keys)
                for r in data:
                    w.writerow([str(r[k]).replace(".", ",") if isinstance(r[k], float) else r[k] for k in keys])
    return 0


if __name__ == "__main__":
    sys.exit(main())
