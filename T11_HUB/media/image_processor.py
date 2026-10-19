"""
TATANGA gorsel isleme boru hattı — 3. surum.

Yeni kurallar (kullanicinin bu turdaki karari):
  1) INSAN YUZU olan gorseller KABUL EDILMEZ — yuz tespit edilirse gorsel
     yayina alinmaz (likely_ok=False, reason='insan_yuzu').
  2) YUZ YOK ama insan uzuvlari (el, kol) urunle beraber goruluyor —
     bu bolgeler urunun maskesinden CIKARILIR (rembg u2net_human_seg).
     Boylece elin cikip urun ortada nefes alan bir goruntu kalir.
  3) Arka plan artik beyaz DEGIL — CSS Berlin markasi turuncu -> yesil
     yumusak gradient (orange-100 #FFE0C2 -> primary-100 #B7E4C7, 135deg).
  4) Kare 1200x1200 tuval + %8 kenar boslugu + alt kenarda kucuk
     'cssberlin.de' imzasi (urune dokunmaz).
  5) DONDURME YOK, ZOOM-CROP YOK — urunun kenarlari kesilmez.

Iç delikler (kapusonun ici, cep ici) morfolojik olarak kapatilir.

Google Lens koruma: (a) arka plan tamamen degisti (gradient), (b) kare
kompozisyon, (c) marka imzasi. Bu ucu kaynak fotografla eslesmeyi ciddi
bicimde bozar; 2 derece dondurmeye ihtiyac yok.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pydantic import BaseModel

DEFAULT_MODEL = "isnet-general-use"
FALLBACK_CHAIN = ["isnet-general-use", "u2net"]

# CSS Berlin marka gradient'i (variables.css'ten)
GRAD_START = (255, 224, 194)   # #FFE0C2 orange-100
GRAD_END   = (183, 228, 199)   # #B7E4C7 primary-100
GRAD_ANGLE_DEG = 135           # sol-ust -> sag-alt

MAX_SIDE = 1500
SQUARE_SIZE = 1200
BOTTOM_SIG_MARGIN = 0.05

# ALTIN ORAN OLCEKLEME:
# Urunun uzun kenari her zaman kanvasin 0.618'i (altin oran) olacak.
# Bu Sellpy tarzi kart tutarliligi verir: yakin/uzak cekim fark etmez,
# tum urunler ayni algisal boyutta gorunur.
GOLDEN_RATIO = 0.618
PRODUCT_LONG_SIDE = int(SQUARE_SIZE * GOLDEN_RATIO)   # 742 px

# Ten rengi tabanli insan tespiti (YCrCb) - ELLER SILINMEZ, REDDEDILIR.
# Neden red? Ceketin bej/kahverengi bolgeleri YCrCb aralığında "ten" sanilir.
# Silmek ceketi delik yapar. Onun yerine "el/kol görünen fotoğrafi hic
# kabul etme" kurali: temiz mankensiz gorseller kartta tutarlı kalir.
SKIN_CR_MIN, SKIN_CR_MAX = 135, 180
SKIN_CB_MIN, SKIN_CB_MAX = 85, 135
SKIN_Y_MIN = 60
SKIN_REJECT_RATIO = 0.25   # urunun %25'inden fazlasi ten -> insan modeli, red
# NOT: dusuk esik (%3-10) bej/kahverengi CEKETLERI insan sanip reddederdi
# (YCrCb'de bej ~ ten). %25 esik: gercek bir insanin ceketi tutmasi/giymesi
# durumunda ten kaplama %30-70 arasi; bej ceket alone yaklasik %20-25 max.

_SESSION_CACHE: dict = {}
_FACE_CASCADE = None


def _has_pymatting() -> bool:
    try:
        import pymatting  # noqa: F401
        return True
    except Exception:
        return False


def _get_session(model_name: str):
    from rembg import new_session
    tried = [model_name] + [m for m in FALLBACK_CHAIN if m != model_name]
    for name in tried:
        if name in _SESSION_CACHE:
            return _SESSION_CACHE[name]
        try:
            sess = new_session(name)
            _SESSION_CACHE[name] = sess
            return sess
        except Exception:
            continue
    raise RuntimeError("hicbir matting modeli yuklenemedi")


def _face_cascade(name: str = "haarcascade_frontalface_default.xml"):
    global _FACE_CASCADE
    if _FACE_CASCADE is None:
        _FACE_CASCADE = {}
    if name not in _FACE_CASCADE:
        import cv2
        _FACE_CASCADE[name] = cv2.CascadeClassifier(cv2.data.haarcascades + name)
    return _FACE_CASCADE[name]


def _iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter / float(aw * ah + bw * bh - inter or 1)


def detect_face(rgb_image: Image.Image) -> bool:
    """
    Insan yuzu var mi (True -> katalog gorseli olmaz).
    2026-10-19 OLCULDU: tek Haar kaskadi (minNeighbors=5) 88 urun fotografinin 29'unda "yuz" buldu ve 29'u da
    YANLISTI (kumas, fermuar, dikis) -> gorsellerin ~1/3'u haksiz reddediliyordu. Simdi uc kosul birden:
      (1) varsayilan kaskad, minNeighbors=8, yuz en az kisa kenarin %6'si;
      (2) bagimsiz alt2 kaskadi ayni bolgeyi dogrular (IoU > 0.3);
      (3) kutunun >= %30'u ten rengi.
    600 fotografta: 6 pozitif (5 gercek yuz, 1 yuzu kapatan emoji), kumas kaynakli yanlis alarm 0.
    """
    import cv2, numpy as np
    if rgb_image.mode != "RGB":
        rgb_image = rgb_image.convert("RGB")
    img = rgb_image
    if max(img.size) > 1600:
        img = img.copy()
        img.thumbnail((1600, 1600))
    gray = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY)
    m = max(40, int(min(gray.shape) * 0.06))
    c1 = _face_cascade().detectMultiScale(gray, scaleFactor=1.1, minNeighbors=8, minSize=(m, m))
    if not len(c1):
        return False
    c2 = _face_cascade("haarcascade_frontalface_alt2.xml").detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=4, minSize=(m, m))
    skin = _skin_mask(img)
    for f in c1:
        if not any(_iou(f, o) > 0.3 for o in c2):
            continue
        x, y, w, h = (int(v) for v in f)
        if skin[y:y + h, x:x + w].mean() >= 0.30:
            return True
    return False


def _skin_mask(rgb: Image.Image) -> "np.ndarray":
    """YCrCb aralikli ten pikseli maskesi (bool ndarray)."""
    import numpy as np, cv2
    arr = np.asarray(rgb.convert("RGB"))
    ycrcb = cv2.cvtColor(arr, cv2.COLOR_RGB2YCrCb)
    y, cr, cb = ycrcb[..., 0], ycrcb[..., 1], ycrcb[..., 2]
    mask = ((cr >= SKIN_CR_MIN) & (cr <= SKIN_CR_MAX) &
            (cb >= SKIN_CB_MIN) & (cb <= SKIN_CB_MAX) &
            (y  >= SKIN_Y_MIN))
    # kucuk gurultuyu at (3x3 opening)
    try:
        from scipy.ndimage import binary_opening
        mask = binary_opening(mask, iterations=1)
    except Exception:
        pass
    return mask


class CutoutQuality(BaseModel):
    coverage_pct: float
    hole_ratio: float
    has_face: bool = False
    skin_in_product_pct: float = 0.0
    likely_ok: bool
    reason: str


def _gradient_canvas(size: int, start=GRAD_START, end=GRAD_END,
                     angle_deg: float = GRAD_ANGLE_DEG) -> Image.Image:
    """Verilen aci ile duz iki-renkli gradient (RGBA opak)."""
    import numpy as np
    theta = np.deg2rad(angle_deg)
    xs = np.linspace(0, 1, size, dtype=np.float32)
    ys = np.linspace(0, 1, size, dtype=np.float32)
    x, y = np.meshgrid(xs, ys)
    # 0..1 proje: kose acisi 0deg=sag, 90deg=alt; 135=sag-alt
    t = np.cos(theta) * x + np.sin(theta) * y
    t = (t - t.min()) / (t.max() - t.min() + 1e-9)
    r = start[0] + (end[0] - start[0]) * t
    g = start[1] + (end[1] - start[1]) * t
    b = start[2] + (end[2] - start[2]) * t
    a = np.full_like(t, 255, dtype=np.float32)
    arr = np.stack([r, g, b, a], axis=-1).clip(0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="RGBA")


def _fill_alpha_holes(alpha: Image.Image) -> Image.Image:
    try:
        import numpy as np
        from scipy.ndimage import binary_fill_holes, binary_closing
        arr = np.asarray(alpha, dtype=np.uint8)
        binary = arr > 128
        closed = binary_closing(binary, iterations=1)
        filled = binary_fill_holes(closed)
        out = np.where(filled, np.maximum(arr, 200), arr).astype(np.uint8)
        return Image.fromarray(out, mode="L")
    except Exception:
        return alpha.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.SMOOTH)


def _dilate_mask(mask_l: Image.Image, radius: int) -> Image.Image:
    """Insan maskesi kenarini biraz genislet -> el/kol tam cikartilir."""
    try:
        import numpy as np
        from scipy.ndimage import binary_dilation
        arr = np.asarray(mask_l, dtype=np.uint8) > 128
        dil = binary_dilation(arr, iterations=max(1, radius))
        return Image.fromarray((dil * 255).astype(np.uint8), mode="L")
    except Exception:
        return mask_l.filter(ImageFilter.MaxFilter(2 * radius + 1))


def assess_cutout(rgba: Image.Image, *, has_face: bool = False,
                  skin_in_product: float = 0.0) -> CutoutQuality:
    """QC: kaplama % + topolojik ic delikler + yuz/ten bilgisi."""
    if rgba.mode != "RGBA":
        rgba = rgba.convert("RGBA")
    alpha = rgba.split()[3]
    hist = alpha.histogram()
    total = rgba.width * rgba.height
    fg = sum(hist[128:])
    coverage = (fg / total) * 100 if total else 0.0

    hole_ratio = 0.0
    try:
        import numpy as np
        from scipy.ndimage import binary_fill_holes
        arr = np.asarray(alpha, dtype=np.uint8) > 128
        filled = binary_fill_holes(arr)
        inner_holes = filled & (~arr)
        if filled.sum():
            hole_ratio = float(inner_holes.sum()) / float(filled.sum())
    except Exception:
        pass

    likely_ok, reason = True, "ok"
    if has_face:
        likely_ok, reason = False, "insan_yuzu tespit edildi"
    elif skin_in_product > SKIN_REJECT_RATIO:
        likely_ok, reason = False, f"urun icinde cok ten (%{skin_in_product*100:.0f}) - insan modeli"
    elif coverage < 3:
        likely_ok, reason = False, "urun neredeyse yok (kaplama <%3)"
    elif coverage > 92:
        likely_ok, reason = False, "arka plan silinmemis olabilir (kaplama >%92)"
    elif hole_ratio > 0.15:
        likely_ok, reason = False, f"urun icinde topolojik delik (%{hole_ratio*100:.1f})"

    return CutoutQuality(coverage_pct=round(coverage, 1),
                         hole_ratio=round(hole_ratio, 3),
                         has_face=has_face,
                         skin_in_product_pct=round(skin_in_product * 100, 1),
                         likely_ok=likely_ok, reason=reason)


def _fit_to_square(rgba: Image.Image, size: int = SQUARE_SIZE,
                   long_side: int = PRODUCT_LONG_SIDE) -> Image.Image:
    """ALTIN ORAN OLCEKLEMESI:
    urunun uzun kenari her zaman `long_side` (0.618*size = 742px) olur.
    Yakin cekim buyutulur, uzak cekim kucultulur; sonuc HEP AYNI oranda.
    Sellpy'de mankenin sabit boyu gibi — kart tutarliligi saglar.
    """
    if rgba.mode != "RGBA":
        rgba = rgba.convert("RGBA")
    alpha = rgba.split()[3]
    bbox = alpha.getbbox()
    canvas = _gradient_canvas(size)
    if not bbox:
        return canvas.convert("RGB")

    cropped = rgba.crop(bbox)
    cw, ch = cropped.size
    # uzun kenar = long_side; kisa kenar oran korunarak
    scale = long_side / max(cw, ch)
    new_w, new_h = max(1, int(cw * scale)), max(1, int(ch * scale))
    cropped = cropped.resize((new_w, new_h), Image.LANCZOS)

    px = (size - new_w) // 2
    py = (size - new_h) // 2
    canvas.paste(cropped, (px, py), cropped)
    return canvas.convert("RGB")


def apply_margin_signature(image: Image.Image, text: str = "cssberlin.de",
                           font_ratio: float = 0.022) -> Image.Image:
    if image.mode != "RGB":
        image = image.convert("RGB")
    w, h = image.size
    font_size = max(12, int(min(w, h) * font_ratio))
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

    draw = ImageDraw.Draw(image)
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]; th = bbox[3] - bbox[1]
    except Exception:
        tw, th = len(text) * font_size // 2, font_size

    x = (w - tw) // 2
    y = h - th - int(h * BOTTOM_SIG_MARGIN)
    # koyu-gri; gradient uzerinde okunur kalir
    draw.text((x, y), text, fill=(90, 90, 90), font=font)
    return image


def matte_to_studio(
    source: bytes | str | Path,
    *,
    model: str = DEFAULT_MODEL,
    alpha_matting: bool = True,
    remove_humans: bool = True,
    reject_faces: bool = True,
    add_signature: bool = True,
) -> tuple[Image.Image, CutoutQuality, str]:
    """
    Kenar-guvenli matting -> insan cikari -> gradient kare studyo tuvale otur.
    Donen: (RGB PIL image, QC, model_adi).

    - reject_faces=True + yuz tespit edilirse: QC.likely_ok=False,
      reason='insan_yuzu' + boş gradient tuval (yine de dondurulur;
      cagiran taraf QC'ye bakip yayına almaz).
    - remove_humans=True: urun maskesinden insan bolgeleri (el/kol) cikarılır.
    - Cikti her zaman 1200x1200, gradient bg, alt kenarda imzali.
    """
    from rembg import remove

    if isinstance(source, (str, Path)):
        data = Path(source).read_bytes()
    else:
        data = source

    src = Image.open(io.BytesIO(data)).convert("RGB")
    src.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    buf = io.BytesIO(); src.save(buf, format="PNG"); data = buf.getvalue()

    # 1) YUZ REDDI
    has_face = False
    if reject_faces:
        try:
            has_face = detect_face(src)
        except Exception:
            has_face = False
    if has_face:
        qc = assess_cutout(Image.new("RGBA", (SQUARE_SIZE, SQUARE_SIZE),
                                     (0, 0, 0, 0)), has_face=True)
        empty = _gradient_canvas(SQUARE_SIZE).convert("RGB")
        if add_signature:
            empty = apply_margin_signature(empty)
        return empty, qc, "face_rejected"

    # 2) URUN MATTING
    session = _get_session(model)
    model_used = next((k for k, v in _SESSION_CACHE.items() if v is session), model)
    kwargs = {"session": session}
    if alpha_matting and _has_pymatting():
        kwargs.update(alpha_matting=True,
                      alpha_matting_foreground_threshold=240,
                      alpha_matting_background_threshold=10,
                      alpha_matting_erode_size=0)
    cutout = Image.open(io.BytesIO(remove(data, **kwargs))).convert("RGBA")

    # 3) IC DELIK ONARIMI
    fixed_alpha = _fill_alpha_holes(cutout.split()[3])
    cutout.putalpha(fixed_alpha)

    # 4) TEN TESPITI - REDDETME (silme YOK: ceket bej/kahverengi ten rengi
    # sanilir, silmek uruni delik yapar; onun yerine "elli fotoğrafi at").
    skin_in_product = 0.0
    if remove_humans:
        try:
            import numpy as np
            skin = _skin_mask(src)
            if skin.shape[:2] != (cutout.height, cutout.width):
                sk_img = Image.fromarray((skin * 255).astype(np.uint8), mode="L")
                sk_img = sk_img.resize(cutout.size, Image.NEAREST)
                skin = np.asarray(sk_img, dtype=np.uint8) > 128
            aarr = np.asarray(cutout.split()[3], dtype=np.uint8) > 128
            skin_in_p = skin & aarr
            prod_area = int(aarr.sum()) or 1
            skin_in_product = float(skin_in_p.sum()) / prod_area
        except Exception:
            pass

    qc = assess_cutout(cutout, has_face=False, skin_in_product=skin_in_product)

    # 5) KARE GRADIENT TUVAL + IMZA
    final = _fit_to_square(cutout)
    if add_signature:
        final = apply_margin_signature(final)

    return final, qc, model_used


def process_image(source, output_path=None, **kwargs):
    jpeg_quality = kwargs.pop("jpeg_quality", 92)
    final, quality, model_used = matte_to_studio(source, **kwargs)
    result = {"quality": quality, "model_used": model_used,
              "size": final.size, "output_path": None}
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        final.save(output_path, format="JPEG", quality=jpeg_quality)
        result["output_path"] = str(output_path)
    return result
