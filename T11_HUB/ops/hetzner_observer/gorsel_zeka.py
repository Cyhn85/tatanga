#!/usr/bin/env python3
"""
Gorsel zeka (PC). Gorseller DISKE KAYDEDILMEZ: bellekte acilir, yalnizca sayisal iz saklanir (istatistik/gorsel.db).

    python gorsel_zeka.py iz [--limit N]        -> yeni gorsel adreslerinin parmak izi (dHash, 64 bit)
    python gorsel_zeka.py esler                 -> ayni fotografin farkli ilanlarda kullanimi (capraz / yeniden listeleme)
    python gorsel_zeka.py model-dogrula         -> CLIP model tanimanin isabeti (basliginda model YAZAN ilanlarda olculur)
    python gorsel_zeka.py model [--limit N]     -> basliginda model olmayan ilanlara gorselden model onerisi

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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("komut", choices=["iz", "esler", "model-dogrula", "model"])
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    if args.komut == "iz":
        cmd_iz(args.limit)
    elif args.komut == "esler":
        cmd_esler()
    else:
        cmd_model(args.komut == "model-dogrula", args.limit)
