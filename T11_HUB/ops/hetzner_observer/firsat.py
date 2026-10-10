#!/usr/bin/env python3
"""
Firsat puani (Faz 2.6). PC'de arsiv uzerinde calisir; hicbir seye karar vermez, olcer.

    python firsat.py --db <arsiv.db> [--csv <klasor>]

GRUP: marka x kategori x tip (model adi yoksa) ya da marka x model.

SATIS FIYATI : grupta gercekten SATILMIS ilanlarin fiyat medyani.
ALIS FIYATI  : grupta satistaki ilan orneklerinin en ucuz ceyregi (P25).
AYNI TABAN   : iki fiyat da kondisyon / pazar / beden carpanlariyla "cok iyi, DE, M" tabanina cevrilir;
               yoksa etiketli-yeni satis fiyati ile yipranmis urunun alis fiyati kiyaslanirdi.
UC DEGER     : 5 EUR alti fiyatlar atilir; kalanlarin alt ve ust %5'i atilir.
MALIYET      : maliyet.json (her degerin kaynagi yazili; varsayimlar acikca isaretli).
NET KAR      : satis - alis - alici koruma - kargo - paketleme - iade payi - komisyon
PUAN         : 30 gunde satilma olasiligi (motor.py, duzeltilmis) x net kar = 30 gunde beklenen kazanc.
               Olasilik en dar guvenilir seviyeden alinir; hangi seviye oldugu yazilir.
ESIK         : en az 5 satis + en az 30 ornek. Altinda puan verilmez.
KONTROLLER   : fiyat <= 0, alis >= satis, net kar > 3 x alis (veri hatasi supheli) -> "supheli".
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import analyze as A  # noqa: E402
import motor as M  # noqa: E402

MIN_SOLD = 5
MIN_SAMPLES = 30
MIN_PRICE = 5.0       # bunun altindaki fiyatlar (1 EUR "satis", takas ilani) fiyat verisi sayilmaz


def trimmed(vals: list[float], frac: float = 0.05) -> list[float]:
    vals = sorted(v for v in vals if v and v >= MIN_PRICE)
    k = int(len(vals) * frac)
    return vals[k:len(vals) - k] if len(vals) > 2 * k + 2 else vals


def quantile(vals: list[float], q: float) -> float:
    vals = sorted(vals)
    pos = (len(vals) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


def costs() -> dict:
    raw = json.load(open(os.path.join(BASE_DIR, "maliyet.json"), encoding="utf-8"))
    return {k: v["deger"] for k, v in raw.items() if not k.startswith("_")}


def net_profit(sell: float, buy: float, c: dict) -> tuple[float, float]:
    cost = (c["alici_koruma_sabit"] + c["alici_koruma_oran"] * buy + c["gelen_kargo"] + c["paketleme"]
            + c["iade_payi_oran"] * sell + c["satis_komisyonu_oran"] * sell + c["giden_kargo"])
    return sell - buy - cost, cost


def group_keys(brand: str, category: str, model: str | None, typ: str | None) -> list[tuple[str, str]]:
    out = []
    if model:
        out.append(("marka·model", f"{brand} · {model}"))
    elif typ:
        out.append(("marka·kategori·tip", f"{brand} · {category} · {typ}"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--csv", metavar="KLASOR")
    args = ap.parse_args()

    conn = A.connect(args.db)
    matcher = A.ModelMatcher()
    rates = A.fx_rates(conn)
    c = costs()

    # carpanlar: ornek havuzundan (analyze ile ayni yontem)
    samples, _ = A.samples(conn, matcher, rates)
    cond_f, market_f, size_f = A.factors(samples)

    def norm_price(price: float, cond, market, size) -> float | None:
        div = (cond_f.get(cond, (1.0, 0))[0] * market_f.get(market, (1.0, 0))[0]
               * size_f.get(size, (1.0, 0))[0])
        return price / div if price and div > 0 else None

    # alis tarafi: satistaki ilan ornekleri
    asks: dict[tuple, list[float]] = defaultdict(list)
    for d in samples:
        p = norm_price(d["price"], d["cond"], d["market"], d["size"])
        for key in group_keys(d["brand"], d["category"], d["model"], d["type"]):
            if p:
                asks[key].append(p)

    # satis tarafi: gercekten satilmis ilanlar (yasi bilinmeyenler dahil: FIYAT icin gecerli)
    sold: dict[tuple, list[float]] = defaultdict(list)
    for r in conn.execute(
            "SELECT cell, title, size, condition, country, COALESCE(final_price, price) p, "
            "COALESCE(currency,'EUR') cur FROM listings WHERE state='sold'"):
        brand, category, _ = (r["cell"].split("|") + ["", ""])[:3]
        if category.startswith("model:"):
            category = "model"
        title_n = A.norm_text(r["title"] or "")
        # ornek tarafiyla birebir ayni filtreler: cocuk bedeni, ayakkabi aramasina karisanlar, kondisyonu bilinmeyen
        if A.is_child_size(r["size"], category):
            continue
        if category == "schuhe" and (A._NON_SHOE_RE.search(title_n) or A._CHILD_WORD_RE.search(title_n)):
            continue
        cond = A.norm_condition(r["condition"])
        if not cond:
            continue
        rate = rates.get(r["cur"]) or 0
        if not rate or not r["p"]:
            continue
        model, _line = matcher.match(brand, r["title"] or "")
        typ = A.match_type(title_n)
        p = norm_price(r["p"] / rate, cond, r["country"], A.size_group(r["size"]))
        for key in group_keys(brand.lower(), category, model, typ):
            if p:
                sold[key].append(p)

    # satilma olasiligi: motor (en dar seviyeden ust seviyeye)
    items = M.load(conn, matcher, rates)
    prob_rows = {(r["seviye"], r["grup"].lower()): r for r in M.build(items)}

    def probability(level: str, grp: str) -> tuple[float, str, str] | None:
        parts = grp.split(" · ")
        brand = parts[0]
        candidates = [(level, grp)]
        if level == "marka·kategori·tip":
            candidates += [("marka·kategori", f"{brand} · {parts[1]}"), ("kategori", parts[1])]
        else:
            candidates += [("marka", brand)]
        for lv, g in candidates:
            r = prob_rows.get((lv, g.lower()))
            if r:
                return r["p30_duzeltilmis"], lv, r["durum"]
        return None

    from saglama import FAIL, run_checks
    late = any(code == "T14" and lvl == FAIL for lvl, code, _ in run_checks(conn))
    rows, skipped = [], {"satis_az": 0, "ornek_az": 0, "olasilik_yok": 0}
    for key in set(sold) | set(asks):
        level, grp = key
        s_vals, a_vals = trimmed(sold.get(key, [])), trimmed(asks.get(key, []))
        if len(s_vals) < MIN_SOLD:
            skipped["satis_az"] += 1
            continue
        if len(a_vals) < MIN_SAMPLES:
            skipped["ornek_az"] += 1
            continue
        prob = probability(level, grp)
        if prob is None:
            skipped["olasilik_yok"] += 1
            continue
        p30, p_level, p_status = prob
        sell = statistics.median(s_vals)
        buy = quantile(a_vals, 0.25)
        net, cost = net_profit(sell, buy, c)
        flags = []
        if sell <= 0 or buy <= 0:
            flags.append("fiyat<=0")
        if buy >= sell:
            flags.append("alis>=satis")
        if net > 3 * buy:
            flags.append("kar>3xalis")
        status = "supheli: " + ",".join(flags) if flags else (
            "on sonuc (kontrol gecikmesi)" if late else p_status)
        rows.append({
            "grup": grp, "seviye": level, "satis_medyan": sell, "alis_p25": buy, "maliyet": cost,
            "net_kar": net, "p30": p30, "p30_seviye": p_level, "beklenen_kar_30g": p30 * net,
            "n_satis": len(s_vals), "n_ornek": len(a_vals), "durum": status,
        })

    rows.sort(key=lambda r: -r["beklenen_kar_30g"])
    print(f"FIRSAT PUANI: {len(rows)} grup puanlandi | atlanan: satis<{MIN_SOLD} {skipped['satis_az']}, "
          f"ornek<{MIN_SAMPLES} {skipped['ornek_az']}, olasilik yok {skipped['olasilik_yok']}")
    print("Fiyatlar 'cok iyi kondisyon, DE, M beden' tabanina cevrilmistir. Maliyet varsayimlari: maliyet.json")
    print(f"{'grup':36}{'alis':>7}{'satis':>7}{'maliyet':>8}{'net':>7}{'p30':>6}{'beklenen':>9}{'n':>8}  durum")
    for r in rows[:15]:
        print(f"{r['grup'][:36]:36}{r['alis_p25']:>6.0f}€{r['satis_medyan']:>6.0f}€{r['maliyet']:>7.1f}€"
              f"{r['net_kar']:>6.1f}€{r['p30']*100:>5.0f}%{r['beklenen_kar_30g']:>8.1f}€"
              f"{r['n_satis']:>4}/{r['n_ornek']:<4} {r['durum']}")

    if args.csv:
        os.makedirs(args.csv, exist_ok=True)
        cols = ["grup", "seviye", "alis_p25", "satis_medyan", "maliyet", "net_kar", "p30", "p30_seviye",
                "beklenen_kar_30g", "n_satis", "n_ornek", "durum"]
        with open(os.path.join(args.csv, "firsatlar.csv"), "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(cols)
            for r in rows:
                vals = []
                for col in cols:
                    v = r[col]
                    if isinstance(v, float):
                        v = str(round(v * 100, 1) if col == "p30" else round(v, 2)).replace(".", ",")
                    vals.append(v)
                w.writerow(vals)
    return 0


if __name__ == "__main__":
    sys.exit(main())
