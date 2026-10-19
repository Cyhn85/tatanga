#!/usr/bin/env python3
"""
ODAK TARAMA PLANI (2026-10-19). Gozlemcinin keşif + takip butcesini, GERCEKTEN alim yapilabilecek ve verisi eksik
marka+model gruplarina yogunlastirir. Neden: model duzeyinde guvenilir fiyat icin >= 5 gercek satis gerekir; 2.000
hucreyi esit taramak bu esige ancak haftalar sonra ulasir (2026-10-19: yalniz 9 grup esikteydi).

    python odak.py [--arsiv ..] [--alis ..] [--n 25]

Puan (her marka+model icin, models.json sozlugunden):
  alis     = KA aktif (detayli) + eBay DE aktif (ikinci el)                                     -> alinabilecek mal
  vinted   = Vinted son 7 gun yeni ilan                     -> takibe girecek ilan = satis verisinin HIZI
  ihtiyac  = 1.0 (satis < 5) | 0.7 (< 15) | 0.4 (< 30) | 0.15 (>= 30)                          -> veri eksigi
  fiyat    = satis medyani (>= 3 satis) yoksa alis ilanlarinin medyani; < 25 EUR elenir           -> kar potansiyeli
  katman   = config 'luxury' markalari 0.4 (replika riski, sermaye, satis yok; istenen fiyat sisirir)
  puan     = log(1 + alis) x log(1 + vinted) x ihtiyac x min(fiyat, 150) / 50 x katman
  (ilk surum yalniz arz topluyordu: Balenciaga/LV/Dior gibi Vinted'de satisi olmayan luks modeller one cikti)
Cikti: odak_cells.json (gozlemci her turda okur; analyze.py'nin model_cells.json'una DOKUNMAZ),
       capraz.db -> odak tablosu (zaman serisi: secildigi andaki satis sayisi -> etki olculur).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import analyze as A  # noqa: E402
import capraz as C  # noqa: E402

MIN_FIYAT = 25.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arsiv", default=os.path.join(C.ROOT, "arsiv.db"))
    ap.add_argument("--alis", default=os.path.join(C.ROOT, "alis_arsiv.db"))
    ap.add_argument("--n", type=int, default=25)
    args = ap.parse_args()
    mt = A.ModelMatcher()
    markalar = {b.lower(): b for b in mt.raw if not b.startswith("_")}
    conn = A.connect(args.arsiv)
    rates = A.fx_rates(conn)

    g = defaultdict(lambda: {"ka": 0, "eb": 0, "vt": 0, "satis": [], "alis_fiyat": []})

    def key(brand, title):
        b = markalar.get((brand or "").strip().lower())
        if not b:
            return None
        model, _ = mt.match(b, title or "")
        return (b, model) if model else None

    # gercek Vinted satislari (EUR)
    for r in conn.execute("SELECT brand, title, COALESCE(final_price, price) p, COALESCE(currency,'EUR') cur "
                          "FROM listings WHERE state='sold'"):
        k = key(r["brand"], r["title"])
        rate = rates.get(r["cur"]) or 0
        if k and rate and r["p"]:
            g[k]["satis"].append(r["p"] / rate)
    # Vinted son 7 gun yeni ilan (arz sinyali; Vinted de alis kanali)
    for r in conn.execute("SELECT brand, title FROM catalog_samples WHERE ts >= datetime('now','-7 day')"):
        k = key(r["brand"], r["title"])
        if k:
            g[k]["vt"] += 1
    if os.path.exists(args.alis):
        a = sqlite3.connect(f"file:{args.alis}?mode=ro", uri=True)
        a.row_factory = sqlite3.Row
        for r in a.execute("SELECT COALESCE(marke, brand) b, title, COALESCE(detail_price, price) p FROM ka_ads "
                           "WHERE detail_status='ok' AND last_seen >= datetime('now','-3 day')"):
            k = key(r["b"], r["title"])
            if k:
                g[k]["ka"] += 1
                if r["p"] and r["p"] >= C.BAIT_PRICE:
                    g[k]["alis_fiyat"].append(float(r["p"]))
        for r in a.execute("SELECT e.brand, e.title, e.price, COALESCE(e.currency,'EUR') cur FROM eb_items e "
                           "LEFT JOIN eb_track t USING(item_id) WHERE e.market='DE' AND e.country='DE' "
                           "AND e.last_seen >= datetime('now','-3 day') AND COALESCE(t.sinif,'ikinci_el')<>'sifir_talep' "
                           "AND e.condition_id IN ('1000','1500','2990')"):
            k = key(r["brand"], r["title"])
            rate = rates.get(r["cur"]) or 0
            if k:
                g[k]["eb"] += 1
                if rate and r["price"]:
                    g[k]["alis_fiyat"].append(r["price"] / rate)
        a.close()

    cfg = json.load(open(os.path.join(BASE_DIR, "config.json"), encoding="utf-8"))
    luks = {x.lower() for x in cfg.get("brands", {}).get("luxury", [])}
    rows = []
    for (b, m), v in g.items():
        n = len(v["satis"])
        fiyat = statistics.median(v["satis"]) if n >= 3 else (statistics.median(v["alis_fiyat"]) if v["alis_fiyat"] else 0)
        if fiyat < MIN_FIYAT:
            continue
        alis = v["ka"] + v["eb"]
        if alis < 2 or v["vt"] < 5:
            continue                      # alinacak mal yok ya da Vinted'de veri birikmez
        ihtiyac = 1.0 if n < 5 else 0.7 if n < 15 else 0.4 if n < 30 else 0.15
        katman = 0.4 if b.lower() in luks else 1.0
        puan = math.log1p(alis) * math.log1p(v["vt"]) * ihtiyac * min(fiyat, 150) / 50 * katman
        rows.append({"brand": b, "model": m, "query": f"{b} {m}", "puan": round(puan, 3), "satis_n": n,
                     "fiyat": round(fiyat, 1), "arz_ka": v["ka"], "arz_eb": v["eb"], "arz_vinted7": v["vt"]})
    rows.sort(key=lambda r: -r["puan"])
    odak = rows[:args.n]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    json.dump({"olusturma": ts, "aciklama": "odak.py: gozlemci bu modelleri her turda once tarar (8 saat, hucre basina gunde 2 takip)",
               "hucreler": odak}, open(os.path.join(BASE_DIR, "odak_cells.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    db = sqlite3.connect(os.path.join(C.ROOT, "capraz.db"))
    db.execute("CREATE TABLE IF NOT EXISTS odak (ts TEXT, marka TEXT, model TEXT, puan REAL, satis_n INTEGER, fiyat REAL, "
               "arz_ka INTEGER, arz_eb INTEGER, arz_vinted7 INTEGER)")
    db.executemany("INSERT INTO odak VALUES (?,?,?,?,?,?,?,?,?)",
                   [(ts, r["brand"], r["model"], r["puan"], r["satis_n"], r["fiyat"], r["arz_ka"], r["arz_eb"],
                     r["arz_vinted7"]) for r in odak])
    db.commit()
    print(f"ODAK: {len(rows)} aday model (fiyat >= {MIN_FIYAT:.0f}, alis arzi >= 2, Vinted 7g >= 5) -> ilk {len(odak)}")
    for r in odak:
        print(f"  {r['puan']:5.2f}  {r['brand'][:14]:14} {r['model'][:24]:24} satis {r['satis_n']:>3} | fiyat {r['fiyat']:>6} "
              f"| KA {r['arz_ka']:>3} eBay {r['arz_eb']:>4} Vinted7g {r['arz_vinted7']:>4}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
