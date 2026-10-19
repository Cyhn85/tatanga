#!/usr/bin/env python3
"""
GERIYE DONUK SINAV: zeka GELECEGI GORMEDEN ne kadar dogru tahmin ediyor? (37 gun beklemeden olcum)

    python geritest.py [--arsiv <arsiv.db>] [--csv <klasor>]

1) FIYAT: kesim zamani T secilir. Satis referansi YALNIZ T'den once kapanan satislarla kurulur (capraz.SellRef until=T);
   T ile T+4 gun arasinda gerceklesen her satisin fiyati, kendi grubu (marka+model/seri/tur/kategori, kondisyon)
   icin tahmin edilir. Olculen: gercek fiyat tahmin bandinda mi (P25-P75; dogru kalibre bir bantta beklenen ~%50),
   medyana gore ortalama mutlak yuzde hata (MAPE), sapma yonu. Seviye bazinda (model / seri / tur / kategori).
   Fiyatlar ulke carpaniyla DE tabanina cevrilerek karsilastirilir (referans havuzu DE tabaninda).
2) SATIS HIZI: kesim T0 icin YALNIZ T0'da bilinen durumla (satildi: T0'dan once; digerleri T0'da sansurlu)
   marka x kategori 7 gunde satilma olasiligi tahmin edilir (motor.kaplan_meier + kucuk grup duzeltmesi).
   T0 ile T0+3 gun arasinda takibe giren YENI ilanlarin gerceklesen 7 gun orani (bugunku veriyle KM) ile kiyaslanir.
   7 gun: verimiz ~2 haftalik, 30 gunluk sonuc henuz gozlenemiyor.
Cikti: capraz.db -> geritest tablosu (karne.py C5 okur), geritest.csv.
"""

from __future__ import annotations

import argparse
import csv
import os
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
FMT = "%Y-%m-%d %H:%M:%S"
PRICE_WINDOW = timedelta(days=4)
COHORT_WINDOW = timedelta(days=3)
HORIZON = 7.0
MIN_GROUP_TRAIN, MIN_GROUP_TEST, SHRINK_K = 20, 10, 20


def _dt(s):
    return datetime.strptime(s, FMT) if s else None


def sold_rows(conn, matcher, rates):
    out = []
    for r in conn.execute("SELECT cell, title, size, condition, country, COALESCE(final_price, price) p, "
                          "COALESCE(currency,'EUR') cur, closed_at FROM listings WHERE state='sold' AND closed_at IS NOT NULL"):
        brand, cat, _ = (r["cell"].split("|") + ["", ""])[:3]
        cat = None if cat.startswith("model:") else C.CAT_MAP.get(cat, cat)
        tier = A.norm_condition(r["condition"])
        rate = rates.get(r["cur"]) or 0
        if not tier or not rate or not r["p"] or A.is_child_size(r["size"], cat or ""):
            continue
        price = r["p"] / rate
        if price < C.MIN_PRICE:
            continue
        model, line = matcher.match(brand, r["title"] or "")
        out.append({"brand": brand, "cat": cat, "model": model, "line": line,
                    "type": A.match_type(A.norm_text(r["title"] or "")), "tier": tier, "country": r["country"],
                    "price": price, "closed": _dt(r["closed_at"])})
    return out


def price_test(conn, matcher, rates, cond_f, market_f, sales) -> list[dict]:
    first = min(s["closed"] for s in sales)
    last = max(s["closed"] for s in sales)
    cutoffs, t = [], first + timedelta(days=4)
    while t + PRICE_WINDOW <= last + timedelta(hours=1):
        cutoffs.append(t)
        t += timedelta(days=2)
    res = []
    for T in cutoffs:
        ref = C.SellRef(conn, matcher, rates, cond_f, market_f, until=T.strftime(FMT))
        for s in sales:
            if not (T <= s["closed"] < T + PRICE_WINDOW):
                continue
            keys = C.keys_for(s["brand"], s["cat"], s["model"], s["type"], s["line"])
            est = ref.estimate(keys, s["tier"], "*", cat=s["cat"])
            if not est:
                continue
            vals, n, level, scope = est
            p25, med, p75 = C.quantile(vals, 0.25), statistics.median(vals), C.quantile(vals, 0.75)
            actual = s["price"] / ref.f(market_f, s["country"])          # DE tabani
            res.append({"kesim": T.strftime("%m-%d %H:%M"), "seviye": level, "kapsam": scope, "n_ref": n,
                        "gercek": actual, "p25": p25, "medyan": med, "p75": p75,
                        "bantta": int(p25 <= actual <= p75), "ape": abs(actual - med) / actual,
                        "sapma": (med - actual) / actual})
    return res


def items_at(conn, matcher, T: datetime, until_seen: datetime | None = None, since_seen: datetime | None = None,
             known_at: datetime | None = None) -> list[dict]:
    """Takipli (yeni kohort) ilanlar -> KM kaydi. known_at verilirse durum O ANDA bilinen haliyle (sansur)."""
    out = []
    for r in conn.execute("SELECT cell, title, state, first_seen, last_active_at, last_check, closed_at, days_to_close "
                          "FROM listings WHERE cohort IS NOT 'baseline' AND state IN ('active','sold','gone','expired')"):
        fs = _dt(r["first_seen"])
        if fs is None or (until_seen and fs >= until_seen) or (since_seen and fs < since_seen):
            continue
        brand, cat, _ = (r["cell"].split("|") + ["", ""])[:3]
        cat = "model" if cat.startswith("model:") else C.CAT_MAP.get(cat, cat)
        closed = _dt(r["closed_at"])
        seen = _dt(r["last_active_at"] or r["last_check"]) or fs
        if known_at:
            if r["state"] == "sold" and closed and closed < known_at:
                t, ev = r["days_to_close"], 1
            elif r["state"] == "gone" and closed and closed < known_at:
                t, ev = r["days_to_close"], 0
            else:
                t, ev = (min(seen, known_at) - fs).total_seconds() / 86400, 0
        else:
            if r["state"] == "sold":
                t, ev = r["days_to_close"], 1
            elif r["state"] == "gone":
                t, ev = r["days_to_close"], 0
            elif r["state"] == "expired":
                t, ev = 90.0, 0
            else:
                t, ev = (seen - fs).total_seconds() / 86400, 0
        if t is None or t < 0:
            continue
        out.append({"g": (brand.lower(), cat), "cat": cat, "t": max(t, 0.01), "event": ev})
    return out


def p7(items) -> tuple[float, bool]:
    if not items:
        return 0.0, False
    km = M.kaplan_meier([{"t": d["t"], "event": d["event"]} for d in items])
    # motor.HORIZONS icinde 7 var
    return km[7]["p"], km[7]["ok"]


def speed_test(conn, matcher) -> list[dict]:
    allc = items_at(conn, matcher, None)
    if not allc:
        return []
    starts = sorted(_dt(r[0]) for r in conn.execute(
        "SELECT first_seen FROM listings WHERE cohort IS NOT 'baseline' AND first_seen IS NOT NULL"))
    first, last = starts[0], starts[-1]
    now = datetime.utcnow()
    # Egitimde satis olabilmesi icin kesim, ilk tespit edilen satistan EN AZ 4 gun sonra olmali
    # (satis tespiti 2026-10-05'te basladi; daha erken kesim "tahmin %0" uretir - sinavin hatasi olurdu).
    first_sale = _dt(conn.execute("SELECT MIN(closed_at) FROM listings WHERE state='sold'").fetchone()[0])
    res, T0 = [], max(first + timedelta(days=5), first_sale + timedelta(days=4))
    while T0 + COHORT_WINDOW <= last and T0 + COHORT_WINDOW + timedelta(days=HORIZON) <= now:
        train = items_at(conn, matcher, None, until_seen=T0, known_at=T0)
        test = items_at(conn, matcher, None, since_seen=T0, until_seen=T0 + COHORT_WINDOW)
        by_tr, by_te, by_cat = defaultdict(list), defaultdict(list), defaultdict(list)
        for d in train:
            by_tr[d["g"]].append(d)
            by_cat[d["cat"]].append(d)
        for d in test:
            by_te[d["g"]].append(d)
        for g, te in by_te.items():
            tr = by_tr.get(g, [])
            if len(tr) < MIN_GROUP_TRAIN or len(te) < MIN_GROUP_TEST:
                continue
            p_tr, _ = p7(tr)
            p_cat, _ = p7(by_cat.get(g[1], []))
            pred = (len(tr) * p_tr + SHRINK_K * p_cat) / (len(tr) + SHRINK_K)
            real, ok = p7(te)
            if not ok:
                continue
            res.append({"kesim": T0.strftime("%m-%d"), "grup": f"{g[0]} · {g[1]}", "n_egitim": len(tr), "n_test": len(te),
                        "tahmin_p7": pred, "gercek_p7": real, "fark": pred - real})
        T0 += timedelta(days=2)
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arsiv", default=os.path.join(ROOT, "arsiv.db"))
    ap.add_argument("--csv", metavar="KLASOR")
    args = ap.parse_args()
    conn = A.connect(args.arsiv)
    matcher, rates = A.ModelMatcher(), A.fx_rates(conn)
    samples, _ = A.samples(conn, matcher, rates)
    cond_f, market_f, _ = A.factors(samples)
    sales = sold_rows(conn, matcher, rates)
    pr = price_test(conn, matcher, rates, cond_f, market_f, sales)
    sp = speed_test(conn, matcher)

    print(f"GERITEST FIYAT: {len(pr)} tahmin (gelecegi gormeden) | {len(sales)} gercek satis")
    summary = []
    for level in ("marka·model", "marka·seri", "marka·tur", "marka·kategori", "HEPSI"):
        sel = [r for r in pr if level == "HEPSI" or r["seviye"] == level]
        if not sel:
            continue
        row = {"olcum": "fiyat", "seviye": level, "n": len(sel),
               "bantta_oran": sum(r["bantta"] for r in sel) / len(sel),
               "mape": statistics.median(r["ape"] for r in sel),
               "sapma": statistics.median(r["sapma"] for r in sel)}
        summary.append(row)
        print(f"  {level:16} n={row['n']:>4} | P25-P75 bandinda %{row['bantta_oran'] * 100:4.0f} (beklenen ~50) | "
              f"medyan mutlak hata %{row['mape'] * 100:4.0f} | sapma %{row['sapma'] * 100:+4.0f}")
    print(f"GERITEST HIZ (7 gun): {len(sp)} grup karsilastirmasi")
    if not sp:
        print("  OLCULEMEDI: gecerli kesim yok. Kosul: kesimden once satis verisi (tespit 05.10'da basladi) VE kesimden "
              "sonra takibe giren ilanlarin 7 gunluk sonucu. 09.10 sonrasi yeni takip girisi yok (sunucu engeli); "
              "PC gozlemcisi yeni ilan aldikca ~10 gun icinde olculur.")
        summary.append({"olcum": "hiz_p7", "seviye": "marka·kategori", "n": 0, "bantta_oran": None, "mape": None,
                        "sapma": None})
    if sp:
        mae = statistics.mean(abs(r["fark"]) for r in sp)
        bias = statistics.mean(r["fark"] for r in sp)
        summary.append({"olcum": "hiz_p7", "seviye": "marka·kategori", "n": len(sp), "bantta_oran": None,
                        "mape": mae, "sapma": bias})
        print(f"  ortalama mutlak fark {mae * 100:.1f} puan | sapma {bias * 100:+.1f} puan "
              f"(+ = olasiligi fazla tahmin)")
        for r in sorted(sp, key=lambda x: -abs(x["fark"]))[:5]:
            print(f"   {r['kesim']} {r['grup'][:28]:28} tahmin %{r['tahmin_p7'] * 100:.0f} gercek %{r['gercek_p7'] * 100:.0f} "
                  f"(egitim {r['n_egitim']}, test {r['n_test']})")
    db = sqlite3.connect(os.path.join(ROOT, "capraz.db"))
    db.execute("DROP TABLE IF EXISTS geritest")
    db.execute("CREATE TABLE geritest (olcum TEXT, seviye TEXT, n INTEGER, bantta_oran REAL, hata REAL, sapma REAL, ts TEXT)")
    ts = datetime.utcnow().strftime(FMT)
    db.executemany("INSERT INTO geritest VALUES (?,?,?,?,?,?,?)",
                   [(r["olcum"], r["seviye"], r["n"], r["bantta_oran"], r["mape"], r["sapma"], ts) for r in summary])
    db.commit()
    if args.csv:
        os.makedirs(args.csv, exist_ok=True)
        with open(os.path.join(args.csv, "geritest_fiyat.csv"), "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            if pr:
                w.writerow(pr[0].keys())
                for r in pr:
                    w.writerow([str(round(v, 4)).replace(".", ",") if isinstance(v, float) else v for v in r.values()])
    return 0


if __name__ == "__main__":
    sys.exit(main())
