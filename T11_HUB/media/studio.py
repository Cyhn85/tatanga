"""
STUDYO HATTI (2026-10-19) — KULLANICININ KENDI urun fotograflari icin Sellpy kalitesinde katalog gorseli.

    final, qc = studio(bytes)          # PIL RGB 1200x1500 + kalite raporu

Neden ayri modul: media/image_processor.py kazinan kaynak gorseller icin yazildi (gradient + imza).
Bu hat yalniz kullanicinin aldigi urunun KENDI fotografini isler; kopya-ilan tespitini atlatma amaci YOKTUR
(dondurme / eslesme bozma yapilmaz).

Adimlar:
  1) EXIF yonu duzeltilir, uzun kenar en fazla 2048 px.
  2) On kalite: kisa kenar >= 700 px, bulaniklik (Laplace varyansi) olculur.
  3) Maske: BiRefNet-general (rembg, ~970 MB, yerel CPU). Yoksa isnet-general-use (rapor 'model' alaninda yazar).
  4) Ic delik onarimi + kalite kapisi: yuz yok, kaplama %3-92, ic delik <= %15, urun kadraj kenarina tasmiyor,
     kesim kenari yumusak (yari saydam piksel orani makul).
  5) 4:5 tuval (1200x1500), notr acik gri studyo zemin, urun uzun kenari tuvalin %80'i, yatay ortali,
     zemine oturan yumusak temas golgesi. Tum urunler ayni kadrajda (Sellpy tutarliligi).
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

CANVAS_W, CANVAS_H = 1200, 1500
BG = (242, 242, 240)                 # notr acik gri (Sellpy benzeri studyo)
FILL_W, FILL_H = 0.80, 0.80          # urunun kaplayabilecegi en buyuk alan (tuval oraninda)
FLOOR_Y = 0.90                       # urunun alt kenarinin oturdugu cizgi (tuval yuksekligi orani)
MAX_SIDE = 2048
MIN_SHORT_SIDE = 700
BLUR_REJECT, BLUR_WARN = 25.0, 60.0  # Laplace varyansi (512 px olcekte)
EDGE_TOUCH_MAX = 0.03                # bir kenarin %3'unden fazlasi urun -> urun kadraja sigmamis
MODELS = ("birefnet-general", "isnet-general-use")

_SESS: dict = {}


def _session():
    from rembg import new_session
    for name in MODELS:
        if name in _SESS:
            return _SESS[name], name
        try:
            _SESS[name] = new_session(name)
            return _SESS[name], name
        except Exception:
            continue
    raise RuntimeError("hicbir arka plan modeli yuklenemedi")


def _blur_score(img: Image.Image) -> float:
    import numpy as np
    g = img.convert("L").copy()
    g.thumbnail((512, 512))
    a = np.asarray(g, dtype=np.float32)
    lap = (-4 * a[1:-1, 1:-1] + a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:])
    return float(lap.var())


def _edge_touch(alpha) -> dict:
    """Her kenarda urun pikseli orani (urun kadrajin disina tasiyorsa kesik gorunur)."""
    import numpy as np
    a = np.asarray(alpha, dtype=np.uint8) > 128
    return {"ust": float(a[0].mean()), "alt": float(a[-1].mean()), "sol": float(a[:, 0].mean()),
            "sag": float(a[:, -1].mean())}


def _soft_edge_ratio(alpha) -> float:
    """Yari saydam (10-245) piksellerin urun alanina orani: cok yuksekse maske 'bulanik/sisli' kesilmis."""
    import numpy as np
    a = np.asarray(alpha, dtype=np.uint8)
    fg = (a > 128).sum() or 1
    return float(((a > 10) & (a < 245)).sum()) / fg


_KISI = None


def _kisi_olasiligi(img: Image.Image) -> float | None:
    """CLIP sifir-atis: 'kiyafeti giyen kisi' olasiligi (askida/serili/manken/ayakkabi/etikete karsi).
    Tek basina yetmez (serili mont / hayalet mankende 0,92'ye cikti); ten orani ile BIRLIKTE kullanilir."""
    global _KISI
    try:
        from logic import gorsel_arama as G
        import open_clip
        m, prep, torch = G._load_model()
        if _KISI is None:
            tok = open_clip.get_tokenizer("ViT-B-32")
            texts = ["a photo of a person wearing the clothes", "a selfie of a person wearing a jacket",
                     "a photo of a person standing outdoors",
                     "a product photo of clothing on a hanger", "a flat lay photo of clothing on the floor",
                     "a photo of clothing on a mannequin", "a product photo of shoes", "a photo of a clothing label"]
            with torch.no_grad():
                tf = m.encode_text(tok(texts))
                tf /= tf.norm(dim=-1, keepdim=True)
            _KISI = tf
        with torch.no_grad():
            v = m.encode_image(prep(img).unsqueeze(0))
            v /= v.norm(dim=-1, keepdim=True)
            p = (100 * v @ _KISI.T).softmax(-1)[0]
        return float(p[:3].sum())
    except Exception:
        return None


def _compose(cutout: Image.Image) -> Image.Image:
    alpha = cutout.split()[3]
    bbox = alpha.getbbox()
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), BG)
    if not bbox:
        return canvas
    prod = cutout.crop(bbox)
    pw, ph = prod.size
    scale = min(CANVAS_W * FILL_W / pw, CANVAS_H * FILL_H / ph)
    nw, nh = max(1, int(pw * scale)), max(1, int(ph * scale))
    prod = prod.resize((nw, nh), Image.LANCZOS)
    x = (CANVAS_W - nw) // 2
    floor = int(CANVAS_H * FLOOR_Y)
    y = floor - nh
    top_min = int(CANVAS_H * (1 - FILL_H) / 2)
    if y < top_min:                          # cok uzun urun: dikeyde ortala
        y = (CANVAS_H - nh) // 2
    # temas golgesi: urunun alt kenarinda yumusak elips (yerde duruyor hissi)
    sh = Image.new("L", (CANVAS_W, CANVAS_H), 0)
    d = ImageDraw.Draw(sh)
    sw = int(nw * 0.72)
    sy = y + nh
    d.ellipse((CANVAS_W // 2 - sw // 2, sy - int(CANVAS_H * 0.012), CANVAS_W // 2 + sw // 2, sy + int(CANVAS_H * 0.018)),
              fill=70)
    sh = sh.filter(ImageFilter.GaussianBlur(28))
    shadow = Image.new("RGB", (CANVAS_W, CANVAS_H), (60, 60, 58))
    canvas = Image.composite(shadow, canvas, sh)
    canvas.paste(prod, (x, y), prod)
    return canvas


def studio(source: bytes | str | Path) -> tuple[Image.Image | None, dict]:
    """(RGB 1200x1500 ya da None, kalite raporu). Rapor 'ok' False ise gorsel yayina uygun DEGIL."""
    from rembg import remove
    from media.image_processor import _fill_alpha_holes, assess_cutout, detect_face

    data = Path(source).read_bytes() if isinstance(source, (str, Path)) else source
    src = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    src.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    rep: dict = {"ok": True, "hatalar": [], "uyarilar": [], "boyut": list(src.size)}

    if min(src.size) < MIN_SHORT_SIDE:
        rep["hatalar"].append(f"cozunurluk dusuk ({src.width}x{src.height}; kisa kenar >= {MIN_SHORT_SIDE} olmali)")
    blur = _blur_score(src)
    rep["netlik"] = round(blur, 1)
    if blur < BLUR_REJECT:
        rep["hatalar"].append(f"fotograf bulanik (netlik {blur:.0f} < {BLUR_REJECT:.0f})")
    elif blur < BLUR_WARN:
        rep["uyarilar"].append(f"netlik dusuk ({blur:.0f})")
    try:
        if detect_face(src):
            rep["hatalar"].append("insan yuzu var (katalog gorselinde yuz olmaz)")
    except Exception:
        pass

    sess, model = _session()
    rep["model"] = model
    buf = io.BytesIO()
    src.save(buf, format="PNG")
    cut = Image.open(io.BytesIO(remove(buf.getvalue(), session=sess))).convert("RGBA")
    alpha = _fill_alpha_holes(cut.split()[3])
    cut.putalpha(alpha)

    # ten: urunu tutan el/kol kesimde kaldiysa (BiRefNet cogu zaman eli atar; kalan ten orani olculur)
    skin_p = 0.0
    try:
        import numpy as np
        from media.image_processor import _skin_mask
        sk = _skin_mask(src)
        fg = np.asarray(alpha, dtype=np.uint8) > 128
        skin_p = float((sk & fg).sum()) / float(fg.sum() or 1)
    except Exception:
        pass
    rep["ten"] = round(skin_p, 3)
    q = assess_cutout(cut, skin_in_product=skin_p)
    # kiyafeti giyen kisi (yuzu kapali/bulanik olsa bile): CLIP >= 0.90 VE urunde ten >= %5
    # (2026-10-19 olcum: gercek kisiler CLIP 1.00 / ten %9.6-25.8; serili mont ve hayalet manken CLIP 0.92 / ten %0-2.8)
    kisi = _kisi_olasiligi(src)
    rep["kisi"] = round(kisi, 3) if kisi is not None else None
    if kisi is not None and kisi >= 0.90 and skin_p >= 0.05:
        rep["hatalar"].append("urun bir kisinin uzerinde (katalog gorseli: askida / serili / manken olmali)")
    if 0.10 < skin_p <= 0.25:
        rep["uyarilar"].append(f"urunde ten rengi %{skin_p * 100:.0f} (el/kol olabilir; bej/kahverengi urunde normal)")
    rep["kaplama"] = q.coverage_pct
    rep["ic_delik"] = q.hole_ratio
    if not q.likely_ok:
        rep["hatalar"].append(q.reason)
    edges = _edge_touch(alpha)
    rep["kenar"] = {k: round(v, 3) for k, v in edges.items()}
    tasan = [k for k, v in edges.items() if v > EDGE_TOUCH_MAX]
    if tasan:
        rep["hatalar"].append(f"urun kadraja sigmamis ({', '.join(tasan)} kenardan tasiyor) - daha uzaktan cek")
    soft = _soft_edge_ratio(alpha)
    rep["yumusak_kenar"] = round(soft, 3)
    if soft > 0.25:
        rep["uyarilar"].append(f"kesim kenari sisli (%{soft * 100:.0f}) - zemin/urun kontrasti dusuk olabilir")

    rep["ok"] = not rep["hatalar"]
    if not alpha.getbbox():
        return None, rep
    return _compose(cut), rep
