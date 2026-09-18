"""
Capraz-platform arbitraj tablosu — product_matcher'i ILK KEZ gercek veriye baglar.

NEDEN VAR: logic/product_matcher.py "ayni urun mu?" sorusunu cevaplamak icin
yazilmis ama app.py'de HIC cagrilmiyordu. Bu betik onu 3639 urunluk havuza
uygular ve ayni urunun platformlar arasi fiyat farkini cikarir.

DEGISIKLIK YAPMAZ: veritabanini salt okunur (mode=ro) acar, hicbir sey yazmaz.
Cikti: stdout + data/arbitraj_tablosu.json

Kullanim:
    python scripts/arbitraj_tablosu.py            # ozet
    python scripts/arbitraj_tablosu.py --detay 20 # en buyuk 20 firsat
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HUB))

from logic.product_matcher import match_key  # noqa: E402

DB = HUB / "data" / "hub.db"
CIKTI = HUB / "data" / "arbitraj_tablosu.json"

# Ayni urunun iki ilani arasinda anlamli sayilacak en dusuk fark.
# Altindaki farklar kargo/pazarlik gurultusune karisir.
MIN_FARK_EUR = 15.0
MIN_FARK_ORAN = 0.35   # ucuz olanin en az %35 uzerinde olmali


def yukle() -> list[dict]:
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    rows = db.execute("""
        SELECT id, title, brand, size, category, price, currency,
               source_platform, source_url, source_status, cssberlin_id
        FROM products
        WHERE price > 0 AND title IS NOT NULL AND title != ''
    """).fetchall()
    db.close()
    return [dict(r) for r in rows]


def kovala(urunler: list[dict]) -> dict[str, list[dict]]:
    """Urunleri kanonik match_key'e gore kovalara ayirir."""
    kovalar: dict[str, list[dict]] = defaultdict(list)
    for u in urunler:
        # Yalniz EUR: kur cevrimi yapilmadan fiyat karsilastirmak sahte spread uretir
        if (u.get("currency") or "EUR").upper() != "EUR":
            continue
        k = match_key(brand=u.get("brand"), title=u.get("title"),
                      size=u.get("size"), category=u.get("category"))
        if k:
            kovalar[k].append(u)
    return kovalar


def firsatlar(kovalar: dict[str, list[dict]]) -> list[dict]:
    """Ayni match_key'de birden fazla PLATFORM varsa fiyat farkini olcer."""
    sonuc = []
    for anahtar, grup in kovalar.items():
        platformlar = {u["source_platform"] for u in grup}
        if len(platformlar) < 2:
            continue  # tek platformdaki fark arbitraj degil
        ucuz = min(grup, key=lambda x: x["price"])
        pahali = max(grup, key=lambda x: x["price"])
        if ucuz["source_platform"] == pahali["source_platform"]:
            continue
        fark = pahali["price"] - ucuz["price"]
        if fark < MIN_FARK_EUR or fark < ucuz["price"] * MIN_FARK_ORAN:
            continue
        sonuc.append({
            "anahtar": anahtar,
            "ilan_sayisi": len(grup),
            "platform_sayisi": len(platformlar),
            "al_platform": ucuz["source_platform"],
            "al_fiyat": round(ucuz["price"], 2),
            "al_url": ucuz["source_url"],
            "al_baslik": (ucuz["title"] or "")[:70],
            "al_durum": ucuz.get("source_status"),
            "sat_platform": pahali["source_platform"],
            "sat_fiyat": round(pahali["price"], 2),
            "sat_url": pahali["source_url"],
            "fark_eur": round(fark, 2),
            "fark_yuzde": round(fark / ucuz["price"] * 100, 1),
        })
    sonuc.sort(key=lambda x: x["fark_eur"], reverse=True)
    return sonuc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--detay", type=int, default=10)
    args = ap.parse_args()

    urunler = yukle()
    kovalar = kovala(urunler)
    eslesen = {k: v for k, v in kovalar.items() if len(v) > 1}
    f = firsatlar(kovalar)

    print(f"Havuz                     : {len(urunler)} urun")
    print(f"Eslestirilebilen (EUR)    : {sum(len(v) for v in kovalar.values())}")
    print(f"Kanonik urun (match_key)  : {len(kovalar)}")
    print(f"  birden fazla ilani olan : {len(eslesen)}")
    print(f"Coklu-platform firsati    : {len(f)}  (>= {MIN_FARK_EUR} EUR ve >= %{MIN_FARK_ORAN*100:.0f})")
    print()

    if f:
        print(f"--- en buyuk {min(args.detay, len(f))} fark ---")
        for x in f[:args.detay]:
            bayrak = " [KAYNAK SATILMIS]" if x["al_durum"] == "sold" else ""
            print(f"  +{x['fark_eur']:7.2f} EUR (%{x['fark_yuzde']:5.1f})  "
                  f"{x['al_platform']:12} {x['al_fiyat']:7.2f}  ->  "
                  f"{x['sat_platform']:12} {x['sat_fiyat']:7.2f}{bayrak}")
            print(f"           {x['al_baslik']}")
    else:
        print("Coklu-platform firsati bulunamadi.")

    CIKTI.write_text(json.dumps({
        "havuz": len(urunler),
        "kanonik_urun": len(kovalar),
        "coklu_ilanli": len(eslesen),
        "firsatlar": f,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nJSON: {CIKTI}")


if __name__ == "__main__":
    main()
