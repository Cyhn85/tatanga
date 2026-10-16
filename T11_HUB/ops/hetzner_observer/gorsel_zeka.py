#!/usr/bin/env python3
"""
Gorsel zeka (PC). Gorseller DISKE KAYDEDILMEZ: bellekte acilir, yalnizca sayisal iz saklanir (istatistik/gorsel.db).

    python gorsel_zeka.py iz [--limit N]        -> yeni gorsel adreslerinin parmak izi (dHash, 64 bit)
    python gorsel_zeka.py esler                 -> ayni fotografin farkli ilanlarda kullanimi (capraz / yeniden listeleme)
    python gorsel_zeka.py model-dogrula         -> CLIP model tanimanin isabeti (basliginda model YAZAN ilanlarda olculur)
    python gorsel_zeka.py model [--limit N]     -> basliginda model olmayan ilanlara gorselden model onerisi
    python gorsel_zeka.py indeks [--limit N]    -> GORSEL ARAMA DIZINI: CLIP vektoru (512) + ilan bilgisi (TATANGA arar)

3) GORSEL ARAMA DIZINI (indeks): eBay / Kleinanzeigen / Sellpy aktif ilanlari + TATANGA urunleri. Her gorsel bellekte
   CLIP ile 512 boyutlu vektore cevrilir; GORSEL SAKLANMAZ, yalniz vektor (float16, ~1 KB) ve ilan bilgisi.
   TATANGA "Benzerini bul" / "Fotografla ara" bu dizinde kosinus benzerligiyle arar (logic/gorsel_arama.py).

1) PARMAK IZI (dHash): ayni fotograf = ayni ilan/ayni urun. Kucuk fark (yeniden boyut, sikistirma) toleransli.
   Kullanim: ayni urun birden cok platformda (capraz eslesme guveni), yeniden listeleme, stok fotograf tespiti.
2) MODEL TANIMA (CLIP, sifir-ornek): gorsel, markanin model adlariyla ("a photo of a Carhartt Detroit Jacket")
   karsilastirilir. KURAL: once isabet olculur (model-dogrula); hedef isabete ulasmadan oneri kullanilmaz.
   Replikayi AYIRT ETMEZ: replika icin satici gecmisi / fiyat kurallari gecerli.
"""

from __future__ import annotations

import argparse
import io
import os
import sqlite3
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import analyze as A  # noqa: E402

ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "..", "istatistik"))
ALIS_DB = os.path.join(ROOT, "alis_arsiv.db")
OUT_DB = os.path.join(ROOT, "gorsel.db")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
GAP = 0.35            # gorsel indirmeleri arasi saniye (CDN'lere nazik)
HAMMING_SAME = 6      # 64 bitte en fazla bu kadar fark = ayni fotograf
MODEL_MIN_SIM = 0.24  # CLIP: en iyi model benzerligi en az bu
MODEL_MIN_GAP = 0.015 # CLIP: en iyi ile ikinci arasindaki fark en az bu (kararsiz eslesme kullanilmaz)


def out_db() -> sqlite3.Connection:
    c = sqlite3.connect(OUT_DB)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS iz (kaynak_id TEXT PRIMARY KEY, platform TEXT, url TEXT, dhash TEXT, ts TEXT,
        hata TEXT);
    CREATE TABLE IF NOT EXISTS model_oneri (kaynak_id TEXT PRIMARY KEY, marka TEXT, model TEXT, benzerlik REAL,
        fark REAL, ikinci TEXT, ts TEXT);
    CREATE TABLE IF NOT EXISTS dogrulama (ts TEXT, n INTEGER, isabet REAL, kapsam REAL, esik_sim REAL, esik_fark REAL);
    CREATE TABLE IF NOT EXISTS vektor (kaynak_id TEXT PRIMARY KEY, platform TEXT, ulke TEXT, gorsel_url TEXT,
        ilan_url TEXT, baslik TEXT, marka TEXT, fiyat REAL, para TEXT, kondisyon TEXT, son_gorulme TEXT,
        aktif INTEGER, emb BLOB, dhash TEXT, ts TEXT, hata TEXT);
    CREATE INDEX IF NOT EXISTS ix_vektor_aktif ON vektor (aktif);
    """)
    return c


def sources(limit: int | None = None) -> list[tuple[str, str, str, str, str]]:
    """(kaynak_id, platform, gorsel_url, marka, baslik). Alis arsivinde gorsel adresi olan ilanlar."""
    a = sqlite3.connect(ALIS_DB)
    rows = []
    for sql, plat in (
            ("SELECT 'EB-'||replace(item_id,'|','-'), image_url, brand, title FROM eb_items WHERE image_url IS NOT NULL", "eBay"),
            ("SELECT 'KA-'||adid, image_url, brand, title FROM ka_ads WHERE image_url IS NOT NULL", "Kleinanzeigen"),
            ("SELECT 'SP-'||object_id, image_url, brand_q, brand||' '||COALESCE(type,'') FROM sp_items WHERE image_url IS NOT NULL", "Sellpy")):
        try:
            rows += [(r[0], plat, r[1], r[2], r[3]) for r in a.execute(sql)]
        except sqlite3.OperationalError:
            pass      # arsivde sutun henuz yok
    if not limit:
        return rows
    # ornek: platformlar arasi esit dagilim (capraz eslesme olculebilsin)
    by = defaultdict(list)
    for r in rows:
        by[r[1]].append(r)
    per = max(1, limit // len(by)) if by else 0
    return [r for group in by.values() for r in group[:per]]


def fetch_image(url: str):
    from PIL import Image
    if url and not url.startswith("http") and os.path.exists(url):
        return Image.open(url).convert("RGB")             # TATANGA'nin kendi yerel ham gorseli
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    data = urllib.request.urlopen(req, timeout=20).read()
    return Image.open(io.BytesIO(data)).convert("RGB")     # yalnizca bellekte


def dhash(img, size: int = 8) -> str:
    """Fark hash'i: 9x8 gri olcek, komsu piksel karsilastirmasi -> 64 bit (16 hex)."""
    g = img.convert("L").resize((size + 1, size))
    px = list(g.getdata())
    bits = 0
    for row in range(size):
        for col in range(size):
            left, right = px[row * (size + 1) + col], px[row * (size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def cmd_iz(limit: int | None) -> None:
    c = out_db()
    done = {r[0] for r in c.execute("SELECT kaynak_id FROM iz")}
    todo = [s for s in sources(limit) if s[0] not in done]
    ok = err = 0
    t0 = time.time()
    for sid, plat, url, _, _ in todo:
        try:
            h, e = dhash(fetch_image(url)), None
            ok += 1
        except Exception as exc:
            h, e = None, f"{type(exc).__name__}: {exc}"[:120]
            err += 1
        c.execute("INSERT OR REPLACE INTO iz VALUES (?,?,?,?,?,?)", (sid, plat, url, h, datetime.now().isoformat(), e))
        if (ok + err) % 50 == 0:
            c.commit()
        time.sleep(GAP)
    c.commit()
    print(f"IZ: {ok} yeni parmak izi, {err} hata, {time.time() - t0:.0f} sn | toplam: "
          f"{c.execute('SELECT COUNT(*) FROM iz WHERE dhash IS NOT NULL').fetchone()[0]}")


def cmd_esler() -> None:
    """Ayni fotograf birden cok ilanda: kova (ilk 16 bit) + tam hamming kontrolu."""
    c = out_db()
    rows = c.execute("SELECT kaynak_id, platform, dhash FROM iz WHERE dhash IS NOT NULL").fetchall()
    buckets = defaultdict(list)
    for r in rows:
        buckets[r[2][:4]].append(r)
    pairs = []
    for group in buckets.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                d = hamming(group[i][2], group[j][2])
                if d <= HAMMING_SAME:
                    pairs.append((group[i], group[j], d))
    cross = [p for p in pairs if p[0][1] != p[1][1]]
    print(f"ESLER: {len(rows)} iz | ayni fotograf cifti {len(pairs)} (farkli platform: {len(cross)})")
    for a, b, d in cross[:10]:
        print(f"  {a[1]:13} {a[0]:28} == {b[1]:13} {b[0]:28} (fark {d} bit)")


def clip_model():
    import open_clip
    import torch
    model, _, prep = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
    tok = open_clip.get_tokenizer("ViT-B-32")
    model.eval()
    return model, prep, tok, torch


def model_names() -> dict[str, list[str]]:
    """models.json: {"Marka": {"models": {"Model Adi": [yazimlar]}, "lines": {...}}, "_aciklama": ...}"""
    import json
    m = json.load(open(os.path.join(BASE_DIR, "models.json"), encoding="utf-8"))
    out = {}
    for brand, info in m.items():
        if brand.startswith("_") or not isinstance(info, dict):
            continue
        names = list((info.get("models") or {}).keys())
        if names:
            out[brand.lower()] = names
    return out


def _embed_texts(model, tok, torch, brand: str, names: list[str]):
    with torch.no_grad():
        t = model.encode_text(tok([f"a photo of a {brand} {n}" for n in names]))
        return t / t.norm(dim=-1, keepdim=True)


def cmd_model(validate: bool, limit: int | None) -> None:
    model, prep, tok, torch = clip_model()
    names = model_names()
    matcher = A.ModelMatcher()
    c = out_db()
    cache = {}
    hits = total = covered = 0
    for sid, plat, url, brand, title in sources():
        b = (brand or "").lower()
        if b not in names or len(names[b]) < 2:
            continue
        title_model, _ = matcher.match(brand, title or "")
        if validate != bool(title_model):
            continue     # dogrulama: basliginda model YAZANLAR (dogru cevap belli); oneri: YAZMAYANLAR
        try:
            img = prep(fetch_image(url)).unsqueeze(0)
        except Exception:
            continue
        if b not in cache:
            cache[b] = _embed_texts(model, tok, torch, brand, names[b])
        with torch.no_grad():
            v = model.encode_image(img)
            v = v / v.norm(dim=-1, keepdim=True)
            sims = (v @ cache[b].T).squeeze(0).tolist()
        order = sorted(range(len(sims)), key=lambda i: -sims[i])
        best, second = order[0], order[1]
        sim, gap = sims[best], sims[best] - sims[second]
        confident = sim >= MODEL_MIN_SIM and gap >= MODEL_MIN_GAP
        total += 1
        if validate:
            if confident:
                covered += 1
                hits += int(names[b][best].lower() == title_model.lower())
        elif confident:
            c.execute("INSERT OR REPLACE INTO model_oneri VALUES (?,?,?,?,?,?,?)",
                      (sid, brand, names[b][best], round(sim, 4), round(gap, 4), names[b][second],
                       datetime.now().isoformat()))
            covered += 1
        time.sleep(GAP)
        if limit and total >= limit:
            break
    c.commit()
    if validate:
        prec = hits / covered if covered else 0
        cov = covered / total if total else 0
        c.execute("INSERT INTO dogrulama VALUES (?,?,?,?,?,?)",
                  (datetime.now().isoformat(), total, prec, cov, MODEL_MIN_SIM, MODEL_MIN_GAP))
        c.commit()
        print(f"MODEL DOGRULAMA: {total} ilan (dogru cevap basliktan) | emin olunan {covered} (%{cov*100:.0f}) | "
              f"isabet %{prec*100:.0f}")
    else:
        print(f"MODEL ONERI: {total} ilan incelendi | emin olunan oneri {covered}")


HUB_DB = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "data", "hub.db"))
ACTIVE_DAYS = 3          # ilan en son bu kadar gun icinde goruldu = hala yayinda kabul


def _big_ebay(url: str) -> str:
    # eBay ozet gorseli s-l140 (140 px); arama kalitesi icin 400 px surumu (ayni gorsel, daha buyuk)
    import re as _re
    return _re.sub(r"/s-l\d+\.", "/s-l400.", url or "")


def index_sources() -> list[dict]:
    """Dizine girecek ilanlar: alis arsivi (eBay/KA/Sellpy) + TATANGA urunleri. aktif = hala yayinda."""
    import json as _json
    out = []
    a = sqlite3.connect(ALIS_DB)
    a.row_factory = sqlite3.Row
    act = f"datetime('now','-{ACTIVE_DAYS} day')"
    q = {
        "eBay": f"SELECT 'EB-'||replace(item_id,'|','-') id, country ulke, image_url img, url, title, brand, price, "
                f"currency para, condition kond, last_seen son, (last_seen >= {act}) aktif FROM eb_items WHERE image_url IS NOT NULL",
        "Kleinanzeigen": f"SELECT 'KA-'||adid id, 'DE' ulke, image_url img, url, title, brand, COALESCE(detail_price, price) price, "
                         f"'EUR' para, zustand kond, last_seen son, (last_seen >= {act}) aktif FROM ka_ads WHERE image_url IS NOT NULL",
        "Sellpy": f"SELECT 'SP-'||object_id id, 'DE' ulke, image_url img, url, brand||' '||COALESCE(type,'') title, brand_q brand, "
                  f"price, 'EUR' para, condition kond, last_seen son, (for_sale=1 AND reserved=0 AND last_seen >= {act}) aktif "
                  f"FROM sp_items WHERE image_url IS NOT NULL",
    }
    for plat, sql in q.items():
        try:
            for r in a.execute(sql):
                out.append({**dict(r), "platform": plat,
                            "img": _big_ebay(r["img"]) if plat == "eBay" else r["img"]})
        except sqlite3.OperationalError:
            pass
    if os.path.exists(HUB_DB):
        h = sqlite3.connect(f"file:{HUB_DB}?mode=ro", uri=True)
        h.row_factory = sqlite3.Row
        for r in h.execute("SELECT id, source_platform, source_url, title, brand, price, currency, condition, "
                           "images_json, raw_images_json, source_status, last_source_check FROM products"):
            try:
                imgs = _json.loads(r["images_json"] or "[]")
                raws = _json.loads(r["raw_images_json"] or "[]")
            except ValueError:
                imgs, raws = [], []
            # once yerel ham gorsel (Vinted CDN adresleri zamanla 404 oluyor), yoksa internet adresi
            img = next((i for i in raws if isinstance(i, str) and os.path.exists(i)), None) or                 next((i for i in imgs if isinstance(i, str) and i.startswith("http")), None)
            if not img:
                continue
            out.append({"id": "TT-" + r["id"], "platform": "TATANGA:" + (r["source_platform"] or "?"), "ulke": None,
                        "img": _big_ebay(img) if "ebayimg" in img and img.startswith("http") else img,
                        "url": r["source_url"], "title": r["title"],
                        "brand": r["brand"], "price": r["price"], "para": r["currency"], "kond": r["condition"],
                        "son": r["last_source_check"], "aktif": 1 if (r["source_status"] or "") == "active" else 0})
    return out


def cmd_indeks(limit: int | None, workers: int = 8) -> None:
    """Yeni gorselleri vektorlestirir; var olanlarin aktiflik/fiyat bilgisini gunceller. Gorsel saklanmaz."""
    import numpy as np
    from concurrent.futures import ThreadPoolExecutor
    c = out_db()
    srcs = index_sources()
    have = {r[0] for r in c.execute("SELECT kaynak_id FROM vektor WHERE emb IS NOT NULL OR hata IS NOT NULL")}
    # mevcut kayitlarin durumu her calismada guncellenir (satilan/kalkan ilan aramada cikmasin)
    c.executemany("UPDATE vektor SET aktif=?, fiyat=?, son_gorulme=? WHERE kaynak_id=?",
                  [(int(bool(x["aktif"])), x["price"], x["son"], x["id"]) for x in srcs if x["id"] in have])
    c.commit()
    todo = [x for x in srcs if x["id"] not in have and x["aktif"]]
    todo.sort(key=lambda x: 0 if x["platform"].startswith("TATANGA") else 1)   # TATANGA urunleri once
    if limit:
        todo = todo[:limit]
    print(f"INDEKS: kaynak {len(srcs)} | zaten dizinde {len(have)} | yeni (aktif) {len(todo)}", flush=True)
    if not todo:
        return
    model, prep, tok, torch = clip_model()
    torch.set_num_threads(4)

    def load(x):
        try:
            img = fetch_image(x["img"])
            return x, prep(img), dhash(img), None
        except Exception as exc:
            return x, None, None, f"{type(exc).__name__}: {exc}"[:120]

    done = err = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for start in range(0, len(todo), 64):
            batch = list(pool.map(load, todo[start:start + 64]))
            good = [(x, t, h) for x, t, h, e in batch if t is not None]
            if good:
                with torch.no_grad():
                    v = model.encode_image(torch.stack([t for _, t, _ in good]))
                    v = (v / v.norm(dim=-1, keepdim=True)).cpu().numpy().astype(np.float16)
            now = datetime.now().isoformat(timespec="seconds")
            for i, (x, t, h) in enumerate(good):
                c.execute("INSERT OR REPLACE INTO vektor VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (x["id"], x["platform"], x["ulke"], x["img"], x["url"], (x["title"] or "")[:150], x["brand"],
                           x["price"], x["para"], x["kond"], x["son"], int(bool(x["aktif"])), v[i].tobytes(), h, now, None))
            for x, t, h, e in batch:
                if t is None:
                    c.execute("INSERT OR REPLACE INTO vektor (kaynak_id, platform, gorsel_url, ilan_url, aktif, ts, hata) "
                              "VALUES (?,?,?,?,0,?,?)", (x["id"], x["platform"], x["img"], x["url"], now, e))
            c.commit()
            done += len(good)
            err += len(batch) - len(good)
            if (start // 64) % 10 == 0:
                rate = done / max(1, time.time() - t0)
                print(f"  {done + err}/{len(todo)} | vektor {done}, hata {err} | {rate:.1f}/sn", flush=True)
            time.sleep(GAP)
    print(f"INDEKS BITTI: {done} yeni vektor, {err} hata, {time.time() - t0:.0f} sn | dizinde aktif: "
          f"{c.execute('SELECT COUNT(*) FROM vektor WHERE aktif=1 AND emb IS NOT NULL').fetchone()[0]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("komut", choices=["iz", "esler", "model-dogrula", "model", "indeks"])
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    if args.komut == "iz":
        cmd_iz(args.limit)
    elif args.komut == "esler":
        cmd_esler()
    elif args.komut == "indeks":
        cmd_indeks(args.limit)
    else:
        cmd_model(args.komut == "model-dogrula", args.limit)
