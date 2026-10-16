"""
Gorsel arama: bir urunun ya da yuklenen fotografin, sistemdeki HALA YAYINDA olan ilanlar arasindaki en benzerleri.

Dizin: <tatanga>/istatistik/gorsel.db -> vektor tablosu (ops/hetzner_observer/gorsel_zeka.py indeks yazar).
Gorseller saklanmaz; yalniz CLIP vektoru (512, float16). Arama = kosinus benzerligi (vektorler normalize).

Benzerlik etiketleri (CLIP ViT-B-32, olculmus genel davranis; kesin "ayni urun" kaniti DEGIL, goz kontrolu icindir):
  >= 0.95 ya da ayni fotograf (dHash farki <= 6 bit) -> "ayni fotograf"
  >= 0.90 -> "ayni urun olabilir"     >= 0.82 -> "cok benzer"     altinda -> "benzer"
"""

from __future__ import annotations

import base64
import io
import json
import os
import sqlite3
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX_DB = ROOT / "istatistik" / "gorsel.db"
HUB_DATA = Path(__file__).resolve().parents[1] / "data"

_lock = threading.Lock()
_model = None          # (model, preprocess, torch)
_index = {"mtime": None, "ids": [], "meta": [], "mat": None, "pos": {}}


def _load_model():
    global _model
    with _lock:
        if _model is None:
            import open_clip
            import torch
            torch.set_num_threads(4)
            m, _, prep = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
            m.eval()
            _model = (m, prep, torch)
    return _model


def _load_index():
    import numpy as np
    if not INDEX_DB.exists():
        return _index
    mtime = INDEX_DB.stat().st_mtime
    if _index["mtime"] == mtime:
        return _index
    c = sqlite3.connect(f"file:{INDEX_DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    rows = c.execute("SELECT kaynak_id, platform, ulke, gorsel_url, ilan_url, baslik, marka, fiyat, para, kondisyon, "
                     "son_gorulme, dhash, emb FROM vektor WHERE aktif=1 AND emb IS NOT NULL").fetchall()
    c.close()
    ids = [r["kaynak_id"] for r in rows]
    meta = [{k: r[k] for k in r.keys() if k != "emb"} for r in rows]
    mat = np.frombuffer(b"".join(r["emb"] for r in rows), dtype=np.float16).reshape(len(rows), 512).astype(np.float32) \
        if rows else np.zeros((0, 512), np.float32)
    _index.update(mtime=mtime, ids=ids, meta=meta, mat=mat, pos={k: i for i, k in enumerate(ids)})
    return _index


def _embed_image(img):
    m, prep, torch = _load_model()
    with torch.no_grad():
        v = m.encode_image(prep(img.convert("RGB")).unsqueeze(0))
        v = (v / v.norm(dim=-1, keepdim=True)).cpu().numpy()[0]
    return v


def _dhash(img, size: int = 8) -> str:
    g = img.convert("L").resize((size + 1, size))
    px = list(g.getdata())
    bits = 0
    for row in range(size):
        for col in range(size):
            bits = (bits << 1) | (1 if px[row * (size + 1) + col] > px[row * (size + 1) + col + 1] else 0)
    return f"{bits:016x}"


def _label(sim: float, same_photo: bool) -> str:
    if same_photo or sim >= 0.95:
        return "ayni fotograf"
    if sim >= 0.90:
        return "ayni urun olabilir"
    if sim >= 0.82:
        return "cok benzer"
    return "benzer"


def _search(vec, query_hash: str | None, k: int, exclude: set) -> list[dict]:
    import numpy as np
    idx = _load_index()
    if idx["mat"] is None or not len(idx["ids"]):
        return []
    sims = idx["mat"] @ vec.astype(np.float32)
    order = np.argsort(-sims)
    out = []
    for i in order:
        kid = idx["ids"][i]
        if kid in exclude:
            continue
        meta = dict(idx["meta"][i])
        same = bool(query_hash and meta.get("dhash") and
                    bin(int(query_hash, 16) ^ int(meta["dhash"], 16)).count("1") <= 6)
        meta.update(benzerlik=round(float(sims[i]), 4), etiket=_label(float(sims[i]), same), ayni_fotograf=same)
        g = meta.get("gorsel_url") or ""
        if g and not g.startswith("http"):
            # TATANGA'nin yerel ham gorseli -> hub'in /data adresi (tarayici yerel yolu acamaz)
            try:
                meta["gorsel_url"] = "/data/" + Path(g).resolve().relative_to(HUB_DATA.resolve()).as_posix()
            except ValueError:
                meta["gorsel_url"] = ""
        meta.pop("dhash", None)
        out.append(meta)
        if len(out) >= k:
            break
    return out


def _product_image(product: dict):
    """TATANGA urununun gorseli: once yerel ham dosya, sonra islenmis, sonra internet adresi (404 ise siradakine)."""
    from PIL import Image
    import urllib.request
    for field in ("raw_images_json", "processed_images_json", "images_json"):
        try:
            items = json.loads(product.get(field) or "[]")
        except ValueError:
            continue
        for p in items:
            if not isinstance(p, str):
                continue
            if p.startswith("http"):
                try:
                    req = urllib.request.Request(p, headers={"User-Agent": "Mozilla/5.0"})
                    return Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=20).read()))
                except Exception:
                    continue          # Vinted CDN adresleri zamanla 404 oluyor
            # "/data/images/..." hub'in sundugu goreli yol (Windows'ta "/" ile baslayan yol mutlak sanilir)
            local = str(HUB_DATA.parent / p.lstrip("/\\")) if p.startswith(("/data", "\data")) else p
            if os.path.exists(local):
                return Image.open(local)
    return None


def similar_to_product(product: dict, k: int = 24) -> dict:
    idx = _load_index()
    kid = "TT-" + product["id"]
    exclude = {kid}
    if kid in idx["pos"]:
        vec = idx["mat"][idx["pos"][kid]]
        qhash = idx["meta"][idx["pos"][kid]].get("dhash")
    else:
        img = _product_image(product)
        if img is None:
            return {"status": "error", "error": "Urunun gorseli artik erisilemiyor (yerel dosya yok, kaynak adresi 404)"}
        vec, qhash = _embed_image(img), _dhash(img)
    # ayni kaynak ilanin baska Vinted alan adlarindaki kopyalari (ayni URL) disarida
    res = [r for r in _search(vec, qhash, k + 10, exclude) if r.get("ilan_url") != product.get("source_url")][:k]
    return {"status": "ok", "sorgu": {"id": product["id"], "baslik": product.get("title")},
            "dizin_aktif": len(idx["ids"]), "sonuclar": res}


def similar_to_upload(b64: str, k: int = 24) -> dict:
    from PIL import Image
    raw = base64.b64decode(b64.split(",", 1)[-1])
    if len(raw) > 12 * 1024 * 1024:
        return {"status": "error", "error": "Gorsel 12 MB'tan buyuk"}
    img = Image.open(io.BytesIO(raw))          # yalniz bellekte; diske yazilmaz
    vec, qhash = _embed_image(img), _dhash(img)
    return {"status": "ok", "sorgu": {"id": None, "baslik": "yuklenen fotograf"},
            "dizin_aktif": len(_load_index()["ids"]), "sonuclar": _search(vec, qhash, k, set())}


def status() -> dict:
    idx = _load_index()
    return {"dizin_var": INDEX_DB.exists(), "aktif_vektor": len(idx["ids"]), "model_yuklu": _model is not None}
