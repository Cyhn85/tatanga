#!/usr/bin/env python3
"""
SIFIR URUN TALEBI (eBay magaza ilanlari, coklu adet). Ikinci el satis fiyatinda KULLANILMAZ; ayri talep sinyalidir.

    python sifir_talep.py [--alis <alis_arsiv.db>] [--csv <klasor>]

Kaynak: eb_track.sinif='sifir_talep' (ebay.py: satistan sonra stok kalan ya da toplam adedi > 1 olan ilan).
Hiz: ilanin TOPLAM satilan adedi / ilanin yayinda oldugu gun (eBay ilan olusturma tarihinden). Tek ilanin hizi
gurultulu oldugundan grup hizi = gruptaki ilanlarin hiz toplami (talep), ilan sayisi ve fiyat bandiyla birlikte.
Grup: marka x (model | seri | tur) x kondisyon (1000 etiketli yeni / 1500 yeni). Marka+model/tur eslesmesi sart:
yalniz marka+kategori olan ilanlar gruba girmez (kullanici karari: marka, model, cins, durum cok onemli).
Cikti: capraz.db -> sifir_talep tablosu (TATANGA ve capraz.py okur), sifir_talep.csv.
"""

from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import analyze as A  # noqa: E402

ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "..", "istatistik"))
COND = {"1000": "yeni_etiketli", "1500": "yeni"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alis", default=os.path.join(ROOT, "alis_arsiv.db"))
    ap.add_argument("--csv", metavar="KLASOR")
    args = ap.parse_args()
    alis = sqlite3.connect(args.alis)
    alis.row_factory = sqlite3.Row
    matcher = A.ModelMatcher()
    try:
        rows = alis.execute(
            "SELECT t.item_id, t.sold_qty, t.avail_qty, t.state, e.brand, e.title, e.condition_id, e.price, "
            "e.currency, e.created, e.country FROM eb_track t JOIN eb_items e USING(item_id) "
            "WHERE t.sinif='sifir_talep' AND COALESCE(t.sold_qty,0) > 0").fetchall()
    except sqlite3.OperationalError as exc:
        print(f"SIFIR TALEP: arsivde sinif sutunu henuz yok ({exc}); bir sonraki cekimden sonra calisir")
        return 0
    now = datetime.utcnow()
    groups = defaultdict(list)
    skipped = 0
    for r in rows:
        cond = COND.get(r["condition_id"])
        model, line = matcher.match(r["brand"], r["title"] or "")
        typ = A.match_type(A.norm_text(r["title"] or ""))
        key_level, key = ("model", model) if model else ("seri", line) if line else ("tur", typ) if typ else (None, None)
        if not cond or not key:
            skipped += 1
            continue
        try:
            age = max(1.0, (now - datetime.strptime(r["created"], "%Y-%m-%d %H:%M:%S")).total_seconds() / 86400)
        except (TypeError, ValueError):
            skipped += 1
            continue
        groups[(r["brand"].lower(), key_level, key.lower() if key_level != "tur" else key, cond)].append(
            {"hiz": r["sold_qty"] / age, "adet": r["sold_qty"], "fiyat": r["price"], "stok": r["avail_qty"],
             "aktif": r["state"] == "active"})
    out = []
    for (brand, level, key, cond), g in groups.items():
        prices = [x["fiyat"] for x in g if x["fiyat"]]
        out.append({"marka": brand, "seviye": level, "grup": key, "kondisyon": cond, "ilan": len(g),
                    "aktif_ilan": sum(1 for x in g if x["aktif"]), "toplam_satilan": sum(x["adet"] for x in g),
                    "haftalik_talep": round(sum(x["hiz"] for x in g) * 7, 2),
                    "fiyat_medyan": round(statistics.median(prices), 2) if prices else None,
                    "guven": "zayif (tek ilan)" if len(g) == 1 else "orta" if len(g) < 5 else "guclu"})
    out.sort(key=lambda r: -r["haftalik_talep"])
    db = sqlite3.connect(os.path.join(ROOT, "capraz.db"))
    db.execute("DROP TABLE IF EXISTS sifir_talep")
    db.execute("CREATE TABLE sifir_talep (marka TEXT, seviye TEXT, grup TEXT, kondisyon TEXT, ilan INTEGER, "
               "aktif_ilan INTEGER, toplam_satilan INTEGER, haftalik_talep REAL, fiyat_medyan REAL, guven TEXT, ts TEXT)")
    ts = now.strftime("%Y-%m-%d %H:%M:%S")
    db.executemany("INSERT INTO sifir_talep VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   [(r["marka"], r["seviye"], r["grup"], r["kondisyon"], r["ilan"], r["aktif_ilan"],
                     r["toplam_satilan"], r["haftalik_talep"], r["fiyat_medyan"], r["guven"], ts) for r in out])
    db.commit()
    print(f"SIFIR TALEP: {len(rows)} magaza ilani -> {len(out)} grup (marka+model/seri/tur+kondisyon) | "
          f"grubu belirlenemeyen {skipped}")
    for r in out[:10]:
        print(f"  {r['marka'][:14]:14} {r['seviye']:5} {str(r['grup'])[:22]:22} {r['kondisyon']:13} ilan {r['ilan']:>2} "
              f"satilan {r['toplam_satilan']:>3} | haftalik {r['haftalik_talep']:>5} | medyan {r['fiyat_medyan']} | {r['guven']}")
    if args.csv:
        os.makedirs(args.csv, exist_ok=True)
        with open(os.path.join(args.csv, "sifir_talep.csv"), "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            if out:
                w.writerow(out[0].keys())
                for r in out:
                    w.writerow([str(v).replace(".", ",") if isinstance(v, float) else v for v in r.values()])
    return 0


if __name__ == "__main__":
    sys.exit(main())
