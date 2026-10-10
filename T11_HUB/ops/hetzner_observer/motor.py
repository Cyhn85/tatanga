#!/usr/bin/env python3
"""
Istatistik motoru (Faz 2.1-2.3). PC'de arsiv uzerinde calisir; hicbir seye karar vermez, olcer.

    python motor.py --db <arsiv.db>                 -> ozet
    python motor.py --db <arsiv.db> --csv <klasor>  -> satis_olasiligi.csv

2.1 SATILMA OLASILIGI (Kaplan-Meier): 7/14/30 gunde satilma olasiligi. Hala satistaki ilanlar
    "o gune kadar satilmadi" bilgisiyle hesaba girer (sansur). Silinen ilan satis sayilmaz, silindigi
    an sansurlenir. Biz baslamadan once yayindaki ilanlar (baseline) disarida: yaslari bilinmiyor.
2.2 BELIRSIZLIK PAYI: Greenwood varyansiyla %95 araligi. Yari genislik > 10 puan -> "on sonuc".
2.3 KUCUK GRUP DUZELTMESI: grubun 30 gun olasiligi, bagli oldugu ust grubun (kategori) oranina
    dogru cekilir: p* = (n*p + K*p_ust) / (n + K). Az veride ust grup, cok veride kendi verisi agir basar.
    Boylece 8 ilanlik grubun %40'i 200 ilanlik grubun %20'sini yalanci bir sekilde gecmez.

Satis gunu bilinmeyen eski satislar (close_uncertain) olasiliga girer ama zamanlari kaba oldugu icin
"hiz" yorumu yapilmaz; tabloda kac tane oldugu ayrica yazilir.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A  # noqa: E402

HORIZONS = (7, 14, 30)
MIN_GROUP = 20          # olasilik icin grupta en az bu kadar (yeni kohort) takipli ilan
SHRINK_K = 20           # kucuk grup duzeltmesinin gucu (ust grup "bu kadar ilan degerinde" sayilir)
MAX_HALF_WIDTH = 0.10   # %95 araligin yari genisligi bundan buyukse "on sonuc"
FMT = "%Y-%m-%d %H:%M:%S"


def _days(a: str | None, b: str | None) -> float | None:
    if not a or not b:
        return None
    return (datetime.strptime(b, FMT) - datetime.strptime(a, FMT)).total_seconds() / 86400


def load(conn, matcher: A.ModelMatcher, rates: dict) -> list[dict]:
    """Takipli ilanlar -> (sure, olay) kayitlari. Olay = satildi; digerleri sansurlu."""
    out = []
    for r in conn.execute(
            "SELECT cell, title, state, first_seen, last_check, last_active_at, closed_at, days_to_close, "
            "COALESCE(close_uncertain,0) unc, price, final_price, COALESCE(currency,'EUR') cur, cohort, "
            "condition, country FROM listings WHERE state IN ('active','sold','gone','expired')"):
        if r["cohort"] == "baseline":
            continue
        brand, category, _ = (r["cell"].split("|") + ["", ""])[:3]
        if category.startswith("model:"):
            category = "model"
        if r["state"] == "sold":
            t, event = r["days_to_close"], 1
        elif r["state"] == "gone":
            t, event = r["days_to_close"], 0
        elif r["state"] == "expired":
            t, event = 90.0, 0
        else:
            t, event = _days(r["first_seen"], r["last_active_at"] or r["last_check"]), 0
        if t is None or t < 0:
            continue
        model, line = matcher.match(brand, r["title"] or "")
        rate = rates.get(r["cur"]) or 0
        price = (r["final_price"] if r["state"] == "sold" and r["final_price"] else r["price"]) or 0
        out.append({
            "brand": brand, "category": category, "model": model, "line": line,
            "type": A.match_type(A.norm_text(r["title"] or "")), "market": r["country"],
            "cond": A.norm_condition(r["condition"]), "t": max(t, 0.01), "event": event,
            "uncertain": bool(r["unc"]) and event == 1,
            "price_eur": price / rate if rate else None,
        })
    return out


def kaplan_meier(items: list[dict]) -> dict:
    """S(t) ve Greenwood varyansi; HORIZONS gunlerinde satilma olasiligi 1-S(t) ve %95 araligi."""
    times = sorted({d["t"] for d in items if d["event"]})
    n_at_risk = len(items)
    s, var_sum = 1.0, 0.0
    by_t_event = defaultdict(int)
    by_t_all = defaultdict(int)
    for d in items:
        by_t_all[d["t"]] += 1
        if d["event"]:
            by_t_event[d["t"]] += 1
    out = {}
    curve = []
    for t in sorted(by_t_all):
        d_t = by_t_event.get(t, 0)
        if d_t and n_at_risk > d_t:
            s *= 1 - d_t / n_at_risk
            var_sum += d_t / (n_at_risk * (n_at_risk - d_t))
        elif d_t and n_at_risk == d_t:
            s = 0.0
        curve.append((t, s, var_sum, n_at_risk))
        n_at_risk -= by_t_all[t]
    for h in HORIZONS:
        s_h, v_h, risk_h = 1.0, 0.0, len(items)
        for t, s_t, v_t, n_t in curve:
            if t > h:
                break
            s_h, v_h, risk_h = s_t, v_t, n_t
        p = 1 - s_h
        se = s_h * math.sqrt(v_h) if v_h else 0.0
        # ufukta hic risk altinda ilan kalmadiysa (takip o kadar uzun degil) tahmin yapilmaz
        followed = sum(1 for d in items if d["t"] >= h or d["event"])
        out[h] = {"p": p, "half": 1.96 * se, "ok": followed >= 10}
    return out


def build(items: list[dict]) -> list[dict]:
    levels = [
        ("kategori", lambda d: (d["category"],), None),
        ("marka", lambda d: (d["brand"],), None),
        ("marka·kategori", lambda d: (d["brand"], d["category"]), lambda d: (d["category"],)),
        ("marka·kategori·tip", lambda d: (d["brand"], d["category"], d["type"]) if d["type"] and not d["model"] else None,
         lambda d: (d["category"],)),
        ("marka·model", lambda d: (d["brand"], d["model"]) if d["model"] else None, lambda d: (d["category"],)),
        ("pazar", lambda d: (d["market"],), None),
        ("kondisyon", lambda d: (d["cond"],) if d["cond"] else None, None),
    ]
    # ust grup (kategori) 30 gun oranlari: kucuk grup duzeltmesinin hedefi
    parent_p = {}
    by_cat = defaultdict(list)
    for d in items:
        by_cat[(d["category"],)].append(d)
    for k, g in by_cat.items():
        if len(g) >= MIN_GROUP:
            parent_p[k] = kaplan_meier(g)[30]["p"]
    overall = kaplan_meier(items)[30]["p"] if items else 0

    rows = []
    for level, key, parent in levels:
        groups = defaultdict(list)
        for d in items:
            k = key(d)
            if k:
                groups[k].append(d)
        for k, g in groups.items():
            if len(g) < MIN_GROUP:
                continue
            km = kaplan_meier(g)
            sold = [d for d in g if d["event"]]
            p30 = km[30]["p"]
            p_parent = parent_p.get(parent(g[0]), overall) if parent else None
            p30_adj = (len(g) * p30 + SHRINK_K * p_parent) / (len(g) + SHRINK_K) if p_parent is not None else p30
            prices = [d["price_eur"] for d in sold if d["price_eur"]]
            reliable = km[30]["ok"] and km[30]["half"] <= MAX_HALF_WIDTH
            rows.append({
                "seviye": level, "grup": " · ".join(str(x) for x in k), "takip": len(g), "satis": len(sold),
                "zamani_belirsiz_satis": sum(1 for d in sold if d["uncertain"]),
                **{f"p{h}": km[h]["p"] for h in HORIZONS},
                **{f"p{h}_pay": km[h]["half"] for h in HORIZONS},
                "p30_duzeltilmis": p30_adj,
                "medyan_satis_eur": statistics.median(prices) if prices else None,
                "durum": "guvenilir" if reliable else "on sonuc",
            })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--csv", metavar="KLASOR")
    args = ap.parse_args()

    conn = A.connect(args.db)
    from saglama import FAIL, run_checks
    late = [text for lvl, code, text in run_checks(conn) if code == "T14" and lvl == FAIL]
    matcher = A.ModelMatcher()
    rates = A.fx_rates(conn)
    items = load(conn, matcher, rates)
    rows = build(items)
    if late:
        # kontroller gecikmeliyken satislar eksik sayilir: hicbir sonuc "guvenilir" isaretlenmez
        for r in rows:
            r["durum"] = "on sonuc (kontrol gecikmesi)"

    n_sold = sum(d["event"] for d in items)
    print(f"MOTOR: {len(items)} yeni kohort ilani, {n_sold} satis | grup: {len(rows)} | "
          f"guvenilir: {sum(1 for r in rows if r['durum'] == 'guvenilir')}"
          + (f" | UYARI: {late[0]}" if late else ""))
    for level in ("kategori", "marka·kategori"):
        sel = sorted((r for r in rows if r["seviye"] == level), key=lambda r: -r["p30_duzeltilmis"])[:8]
        print(f"\n{level.upper()} (30 gunde satilma, duzeltilmis)")
        print(f"{'grup':34}{'takip':>6}{'satis':>6}{'7g':>6}{'14g':>6}{'30g':>10}{'duz.':>6}{'fiyat':>7}  durum")
        for r in sel:
            fiyat = f"{r['medyan_satis_eur']:.0f}€" if r["medyan_satis_eur"] else "-"
            print(f"{r['grup'][:34]:34}{r['takip']:>6}{r['satis']:>6}{r['p7']*100:>5.0f}%{r['p14']*100:>5.0f}%"
                  f"{r['p30']*100:>5.0f}±{r['p30_pay']*100:<3.0f}{r['p30_duzeltilmis']*100:>5.0f}%{fiyat:>7}  {r['durum']}")

    if args.csv:
        os.makedirs(args.csv, exist_ok=True)
        cols = ["seviye", "grup", "takip", "satis", "zamani_belirsiz_satis", "p7", "p7_pay", "p14", "p14_pay",
                "p30", "p30_pay", "p30_duzeltilmis", "medyan_satis_eur", "durum"]
        with open(os.path.join(args.csv, "satis_olasiligi.csv"), "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(cols)
            for r in sorted(rows, key=lambda r: (r["seviye"], -r["p30_duzeltilmis"])):
                vals = []
                for c in cols:
                    v = r[c]
                    if isinstance(v, float):
                        v = round(v * 100, 1) if c.startswith("p") else round(v, 2)
                        v = str(v).replace(".", ",")
                    vals.append(v)
                w.writerow(vals)
    return 0


if __name__ == "__main__":
    sys.exit(main())
