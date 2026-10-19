#!/usr/bin/env python3
"""
TATANGA urunlerini (Urunler sayfasi) gercek satis zekasiyla puanlar. Nokta Atis ile AYNI motor (capraz.Engine).

    python zeka_urunler.py [--hub <hub.db>] [--arsiv <arsiv.db>]

Neden: eski kar alani satis fiyatini alis fiyatinin ~1,4 kati varsayiyordu; "en karli" siralamasi aslinda
"en pahali" demekti (2026-10-16: 2.650 EUR'luk mont "1.110 EUR kar" ile en ustteydi). Bu betik her urune gercek
satislardan tutucu (P25) net kar, satis fiyati, 30 gun satilma olasiligi ve dayandigi satis sayisini yazar.

Yazdigi sutunlar (yalnizca bunlar; mevcut alanlara DOKUNMAZ):
  zeka_net_kar, zeka_net_medyan, zeka_satis_p25, zeka_satis_medyan, zeka_p30, zeka_beklenen, zeka_n,
  zeka_seviye, zeka_alis_toplam, zeka_isaret, zeka_tarih
Tahmin yapilamayan urunde zeka_net_kar NULL kalir (siralamada en alta), zeka_isaret nedenini yazar.
"""

from __future__ import annotations

import argparse
import re
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import analyze as A  # noqa: E402
import capraz as C  # noqa: E402

HUB_DB = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "data", "hub.db"))
COLS = {"zeka_net_kar": "REAL", "zeka_net_medyan": "REAL", "zeka_satis_p25": "REAL", "zeka_satis_medyan": "REAL",
        "zeka_p30": "REAL", "zeka_beklenen": "REAL", "zeka_n": "INTEGER", "zeka_seviye": "TEXT",
        "zeka_alis_toplam": "REAL", "zeka_isaret": "TEXT", "zeka_tarih": "TEXT", "zeka_sirala": "INTEGER"}
EU = {"DE", "AT", "FR", "BE", "NL", "IT", "PL", "ES", "PT", "LU", "DK", "SE", "FI", "IE", "CZ", "SK", "SI", "HU",
      "RO", "BG", "HR", "GR", "CY", "MT", "EE", "LV", "LT"}
# TATANGA kategori agaci -> ortak kategori
CAT_FROM_TATANGA = {"jacken": "jacken", "mantel": "jacken", "fleece": "jacken", "pullover": "oberteile",
                    "schuhe": "schuhe"}
# Vinted UK / PL / NL ve diger kaynaklarin ilk 3 kondisyon adlari (Good / Gut / Dobry / Bon etat = 4. kademe, ALINMAZ).
# "Zo goed als nieuw" ve "Etat neuf" (= yeni gibi) tutucu olarak cok_iyi sayilir.
KOND_EXTRA = {"neu mit etikett": "yeni_etiketli", "new_with_tags": "yeni_etiketli", "neu ohne etikett": "yeni",
              "neu": "yeni", "sehr gut": "cok_iyi", "very_good": "cok_iyi", "neuwertig": "cok_iyi",
              "new with tags": "yeni_etiketli", "new without tags": "yeni", "very good": "cok_iyi",
              "nowy z metka": "yeni_etiketli", "nowy bez metki": "yeni", "bardzo dobry": "cok_iyi",
              "nieuw": "yeni", "zo goed als nieuw": "cok_iyi", "etat neuf": "cok_iyi",
              # Vinted ES / IT / NL / SE (2026-10-16 yeni ulkeler)
              "muy bueno": "cok_iyi", "nuevo con etiquetas": "yeni_etiketli", "nuevo sin etiquetas": "yeni",
              "nuovo senza cartellino": "yeni", "ottimo": "cok_iyi", "nieuw zonder prijskaartje": "yeni",
              "ny med prislapp": "yeni_etiketli", "ny utan prislapp": "yeni", "mycket bra": "cok_iyi"}


def brand_table() -> list[tuple[str, list[str]]]:
    cfg = json.load(open(os.path.join(BASE_DIR, "config.json"), encoding="utf-8"))
    out = []
    for tier in cfg["brands"].values():
        for b in tier:
            out.append((b, [A.norm_text(a) for a in cfg.get("brand_match", {}).get(b, [b])]))
    return out


def canonical_brand(raw: str, title: str, table) -> str | None:
    """Urun markasini listemizdeki adla eslestirir (once marka alani, sonra baslik). Kisa takma adlar tam eslesmeli."""
    for text in (raw or "", title or ""):
        t = " " + A.norm_text(text) + " "
        for name, aliases in table:
            for a in aliases:
                if (len(a) <= 3 and f" {a} " in t) or (len(a) > 3 and f" {a}" in t):
                    return name
    return None


def platform_of(src: str) -> tuple[str, str]:
    s = (src or "").lower()
    if s.startswith("vinted"):
        cc = s.split("_", 1)[1].upper() if "_" in s else "DE"
        return "Vinted", {"UK": "GB"}.get(cc, cc)
    return {"ebay": ("eBay", "DE"), "kleinanzeigen": ("Kleinanzeigen", "DE"), "sellpy": ("Sellpy", "DE"),
            "willhaben": ("Willhaben", "AT"), "leboncoin": ("Leboncoin", "FR"), "tradera": ("Tradera", "SE")
            }.get(s, (src or "?", "DE"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hub", default=HUB_DB)
    ap.add_argument("--arsiv", default=os.path.join(C.ROOT, "arsiv.db"))
    args = ap.parse_args()

    eng = C.Engine(A.connect(args.arsiv))
    c, rates, matcher = eng.c, eng.rates, eng.matcher
    table = brand_table()
    model_cat = eng.ref.model_cat
    hub = sqlite3.connect(args.hub, timeout=60)
    hub.row_factory = sqlite3.Row
    have = {r[1] for r in hub.execute("PRAGMA table_info(products)")}
    for name, decl in COLS.items():
        if name not in have:
            hub.execute(f"ALTER TABLE products ADD COLUMN {name} {decl}")
    if "etiket_json" not in have:
        hub.execute("ALTER TABLE products ADD COLUMN etiket_json TEXT")
    hub.commit()

    stats = defaultdict(lambda: defaultdict(int))
    reasons = defaultdict(int)
    now = datetime.now().isoformat(timespec="seconds")
    updates = []
    for p in hub.execute("SELECT id, source_platform, source_url, title, price, currency, brand, size, condition, "
                         "category, shipping_cost, description, etiket_json FROM products"):
        title = p["title"] or ""
        why = None
        platform, cc = platform_of(p["source_platform"])
        brand = canonical_brand(p["brand"], title, table)
        # noktalama farki ("Neu, ohne Etikett" - Vinted DE/AT) kondisyonu taninmaz yapiyordu: 213 urun disarida kaliyordu
        kond_txt = " ".join(re.findall(r"[^\W_]+", (p["condition"] or "").lower()))
        tier = (A.norm_condition(p["condition"]) or KOND_EXTRA.get(A.norm_text(p["condition"] or ""))
                or A.norm_condition(kond_txt) or KOND_EXTRA.get(kond_txt))
        rate = rates.get((p["currency"] or "EUR").upper()) or 0
        # ETIKET KANITI (logic/etiket.py): stil kodu -> gercek ilanlarda model cogunlugu, ya da etiket metni birebir
        et_model, et_kaynak = None, None
        if p["etiket_json"] and brand:
            try:
                et = json.loads(p["etiket_json"])
                if et.get("durum") == "ok" and et.get("model") and (et.get("marka") or "").lower() == brand.lower():
                    et_model, et_kaynak = et["model"], et.get("kaynak")
            except ValueError:
                pass
        typ = A.match_type(A.norm_text(title))
        cat = next(iter(C.TYPE_CAT[typ]), None) if typ in C.TYPE_CAT and len(C.TYPE_CAT[typ]) == 1 else None
        cat = cat or CAT_FROM_TATANGA.get((p["category"] or "").lower())
        if cat is None and typ in C.TYPE_CAT:
            cat = sorted(C.TYPE_CAT[typ])[0]
        if cat is None:
            # tur yoksa basliktaki genel kategori kelimesi (Veste / Jacke / Schuhe / Pullover / Jeans ...)
            nt = A.norm_text(title)
            cat = next((k for k, rx in C.CAT_WORDS.items() if rx.search(nt)), None)
        if cat is None and brand and not C.OTHER_GARMENT_RE.search(title):
            # basliktaki model adi kategorisini gercek veriden bilir (XT-6 -> schuhe, 501 -> jeans).
            # Baslikta hedef disi bir giysi kelimesi varsa (pantolon/sort/etek...) ATANMAZ: "Firebird pants" ceket degil.
            m0, _l0 = matcher.match(brand, title)
            m0 = m0 or et_model
            cat = model_cat.get((brand.lower(), m0.lower())) if m0 else None
        if not brand:
            why = "marka listemizde degil"
        elif not tier:
            why = f"kondisyon ilk 3 disi/bilinmiyor ({p['condition']})"
        elif not rate or not p["price"]:
            why = "fiyat/para birimi yok"
        elif not cat:
            why = "kategori belirlenemedi (mont/ayakkabi/kazak/kot disi olabilir)"
        elif C.CHILD_TITLE_RE.search(title) or A.is_child_size(p["size"], cat):
            why = "cocuk urunu"
        elif C.OTHER_GARMENT_RE.search(title):
            # "Levi's 501 denim shorts" kot satisiyla, "Firebird pants" ceket satisiyla degerlenmesin
            why = "hedef disi giysi (sort/pantolon/etek/elbise/canta...)"
        if why:
            reasons[why] += 1
            updates.append((None, None, None, None, None, None, None, None, None, why, now, 0, p["id"]))
            continue
        price = p["price"] / rate
        flags = []
        if platform == "Vinted":
            cost = price + c["alici_koruma_sabit"] + c["alici_koruma_oran"] * price + c["gelen_kargo"]
        elif platform == "Sellpy":
            cost = price + c["sellpy_kargo"]
        elif platform == "eBay" and p["shipping_cost"]:
            cost = price + p["shipping_cost"]
        elif platform == "Kleinanzeigen":
            cost = price + c["ka_koruma_sabit"] + c["ka_koruma_oran"] * price + c["gelen_kargo"]
            flags.append("kargo varsayim (ilan kargosu bilinmiyor)")
        else:
            cost = price + c["gelen_kargo"]
            flags.append("kargo varsayim")
        if cc not in EU:
            flags.append(f"AB disi ({cc}): gumruk/ithalat KDV'si hesapta yok")
        model, line = matcher.match(brand, title)
        if not model and et_model:
            model = et_model
            flags.append(f"model etiketten: {et_model} ({et_kaynak})")
        b = {"platform": platform, "sid": p["id"], "img": None, "line": line, "country": cc, "url": p["source_url"],
             "brand": brand, "cat": cat, "gender": None, "title": title, "model": model, "type": typ, "tier": tier,
             "size": p["size"], "price": price, "cost": cost, "flags": flags, "structured": False,
             "descr": p["description"]}
        r = eng.evaluate(b, stats)
        if not r:
            reasons["gercek satis verisi yetersiz / kategori uyusmaz"] += 1
            updates.append((None, None, None, None, None, None, None, None, round(cost, 2),
                            "gercek satis verisi yetersiz", now, 0, p["id"]))
            continue
        updates.append((round(r["net_kar_tutucu"], 2), round(r["net_kar_medyan"], 2), round(r["satis_p25"], 2),
                        round(r["satis_medyan"], 2), r["p30"], r["beklenen_kar_30g"], r["satis_n"],
                        f"{r['tahmin_seviye']} ({r['tahmin_kapsam']})", round(cost, 2), r["isaretler"] or None,
                        now, 0 if r["siralama_disi"] else 1, p["id"]))
    hub.executemany("UPDATE products SET zeka_net_kar=?, zeka_net_medyan=?, zeka_satis_p25=?, zeka_satis_medyan=?, "
                    "zeka_p30=?, zeka_beklenen=?, zeka_n=?, zeka_seviye=?, zeka_alis_toplam=?, zeka_isaret=?, "
                    "zeka_tarih=?, zeka_sirala=? WHERE id=?", updates)
    hub.commit()
    scored = sum(1 for u in updates if u[0] is not None)
    profit = sum(1 for u in updates if u[0] is not None and u[0] > 0 and u[11] == 1)
    weak = sum(1 for u in updates if u[0] is not None and u[11] == 0)
    print(f"ZEKA URUNLER: {len(updates)} urun | gercek satisla puanlanan {scored} | siralama disi (yem fiyat/"
          f"zayif karsilastirma/farkli amac) {weak} | siralamaya giren ve tutucu kar > 0: {profit}")
    for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  puanlanamadi: {v:>5}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
