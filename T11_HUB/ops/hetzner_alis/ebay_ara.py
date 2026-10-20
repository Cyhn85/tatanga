#!/usr/bin/env python3
"""
ANLIK eBay ARAMASI (Chrome eklentisi / en ucuzu bul, 2026-10-20). Resmi Browse API, toplayicinin (ebay.py) kimligi,
kondisyon filtresi (1000/1500/2990) ve gunluk kota sayaci (health) ile. Arsive YAZMAZ; yalniz JSON doner.

    venv/bin/python ebay_ara.py "Dr. Martens 1460" [--pazarlar DE,AT,FR,IT,NL,BE,ES] [--limit 50]

Cikti (stdout, tek satir JSON): {"ok": true, "sonuclar": [{platform, ulke, url, baslik, fiyat, para, kondisyon,
kondisyon_id, kargo, gorsel, pazar}], "cagri": n}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ebay as E  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("q")
    ap.add_argument("--pazarlar", default="DE,AT,FR,IT,NL,BE,ES")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--kategori", help="jacken|oberteile|jeans|schuhe -> eBay kategori filtresi (aksesuar/bagcik elenir)")
    ap.add_argument("--min-fiyat", type=float, default=0)
    args = ap.parse_args()
    conn = E.connect()
    if E.calls_today(conn) >= E.CALLS_PER_DAY:
        print(json.dumps({"ok": False, "hata": "gunluk eBay API kotasi doldu"}))
        return 0
    api = E.Api(conn)
    out, cagri = [], 0
    pazarlar = [x.strip().upper() for x in args.pazarlar.split(",") if x.strip().upper() in E.MARKETS]
    # Browse API aramada TEK kategori kabul eder (virgulle iki kategori HTTP hatasi verdi, olculdu 2026-10-20):
    # kategori verildiyse erkek + kadin icin ayri istek.
    kategoriler = [c for _, c in E.EB_CATS[args.kategori]] if args.kategori in E.EB_CATS else [None]
    gorulen = set()
    for m in pazarlar:
        for kat in kategoriler:
            filt = f"conditionIds:{{{E.CONDITIONS}}},itemLocationCountry:{m},buyingOptions:{{FIXED_PRICE}}"
            params = {"q": args.q[:100], "limit": min(args.limit, 200), "sort": "price", "filter": filt}
            if kat:
                params["category_ids"] = str(kat)
            status, data = api.call("/buy/browse/v1/item_summary/search", params, m, "eb_anlik")
            cagri += 1
            if status != 200 or not data:
                continue
            for it in data.get("itemSummaries", []) or []:
                if it.get("conditionId") not in E.CONDITIONS.split("|") or it.get("itemId") in gorulen:
                    continue
                price = it.get("price") or {}
                fiyat = float(price["value"]) if price.get("value") else None
                if fiyat is None or fiyat < args.min_fiyat:
                    continue                      # alt sinir burada (eBay price filtresi beklendigi gibi calismadi)
                gorulen.add(it.get("itemId"))
                ship = ((it.get("shippingOptions") or [{}])[0].get("shippingCost") or {}).get("value")
                img = (it.get("image") or {}).get("imageUrl") or ((it.get("thumbnailImages") or [{}])[0]).get("imageUrl")
                out.append({"platform": "eBay", "ulke": (it.get("itemLocation") or {}).get("country") or m,
                            "url": it.get("itemWebUrl"), "baslik": it.get("title"), "fiyat": fiyat,
                            "para": price.get("currency"), "kondisyon": it.get("condition"),
                            "kondisyon_id": it.get("conditionId"), "kargo": float(ship) if ship is not None else None,
                            "gorsel": img, "pazar": m})
            time.sleep(0.4)
    conn.commit()
    print(json.dumps({"ok": True, "sonuclar": out, "cagri": cagri}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
