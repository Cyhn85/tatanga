"""
ETIKET / STIL KODU OKUMA (2026-10-19). Fotograftaki etiket, askilik karti, kutu etiketi -> marka, model, stil kodu.
Sonuc capraz eslesmeye "etiket kaniti" olarak girer (baslikta model yazmayan ilan dogru modelle fiyatlanir).

Akis:
  1) Aday secimi (YEREL, ucretsiz): ilanin fotograflari CLIP ile "etiket / care tag / kutu etiketi" olasiligina gore
     siralanir; yalniz en olasi 1-2 fotograf disari gider.
  2) Okuma: Groq gorme modeli (qwen/qwen3.8-27b). OLCULDU: dakikada 7.000 girdi token siniri; 1280 px fotograf
     ~5.400 token -> fotograf 1024 px'e kucultulur ve istekler dakikalik butceyle siraya girer, 429'da beklenir.
  3) Cozumleme (YEREL, kanita dayali):
       stil kodu -> models.json kod desenleri ile dogrulanir -> o kodun gectigi GERCEK Vinted ilanlarinin
       basliklarindaki model cogunlugu (en az 2 ilan, %60) = model ("kod kaniti");
       yoksa okunan model metni ModelMatcher ile eslesirse = model ("etiket metni");
       yoksa Groq'un model tahmini yalniz "oneri" olarak saklanir, fiyatlamaya GIRMEZ.
Veri siniri: Groq'a yalniz urun fotografi gider (kisisel veri yok).
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import sqlite3
import sys
import threading
import time
from collections import Counter, deque
from pathlib import Path

from PIL import Image

MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
TPM_BUTCE = 6500               # dakikalik girdi token butcesi (Groq siniri 7000, pay birakilir)
TOKEN_TAHMIN = 2600            # 1024 px fotograf + istem (olculen ~5.400 / 1280 px'ten olceklenmis, tutucu)
MAX_SIDE = 1024
ADAY_ESIK = 0.35               # CLIP etiket olasiligi; alti "etiket yok" sayilir

_lock = threading.Lock()
_gecmis: deque = deque()       # (zaman, token)
_TXT = None

ISTEM = ("Lies alle sichtbaren Texte auf Etiketten, Hangtags, Schuhkartons, Innenzungen oder Aufnähern in diesem "
         "Produktfoto. Antworte NUR mit JSON: {\"marke\": str|null, \"modell\": str|null, \"stilcode\": str|null, "
         "\"groesse\": str|null, \"material\": str|null, \"text\": \"alle gelesenen Zeilen, mit | getrennt\", "
         "\"sicher\": 0..1}. Erfinde nichts: was nicht lesbar ist, ist null. stilcode = Artikel-/Style-Nummer "
         "(z.B. CW2288-111, 1201A256-020, L41678400).")

ROOT = Path(__file__).resolve().parents[2] / "istatistik"
OBS = Path(__file__).resolve().parents[1] / "ops" / "hetzner_observer"


def _clip_etiket(images: list[Image.Image]) -> list[float]:
    """Her fotograf icin 'etiket/kutu etiketi' olasiligi (yerel CLIP, sifir-atis)."""
    global _TXT
    try:
        from logic import gorsel_arama as G
        import open_clip
        m, prep, torch = G._load_model()
        if _TXT is None:
            tok = open_clip.get_tokenizer("ViT-B-32")
            texts = ["a close-up photo of a clothing label with text", "a photo of a care tag with washing symbols",
                     "a photo of a shoe box label", "a photo of a hang tag with price and barcode",
                     "a photo of the label inside a shoe tongue",
                     "a photo of a whole jacket", "a photo of a pair of shoes", "a photo of a garment on a hanger",
                     "a flat lay photo of clothing", "a photo of a person wearing clothes"]
            with torch.no_grad():
                tf = m.encode_text(tok(texts))
                tf /= tf.norm(dim=-1, keepdim=True)
            _TXT = tf
        out = []
        with torch.no_grad():
            for im in images:
                v = m.encode_image(prep(im).unsqueeze(0))
                v /= v.norm(dim=-1, keepdim=True)
                p = (100 * v @ _TXT.T).softmax(-1)[0]
                out.append(float(p[:5].sum()))
        return out
    except Exception:
        return [0.5] * len(images)          # CLIP yoksa hepsi aday (siralama yok)


def _butce_bekle(token: int) -> None:
    while True:
        with _lock:
            now = time.time()
            while _gecmis and now - _gecmis[0][0] > 60:
                _gecmis.popleft()
            kullanilan = sum(t for _, t in _gecmis)
            if kullanilan + token <= TPM_BUTCE:
                _gecmis.append((now, token))
                return
            bekle = 60 - (now - _gecmis[0][0]) + 0.5
        time.sleep(max(1.0, bekle))


def groq_oku(img: Image.Image) -> dict:
    """Tek fotograf -> okuma sozlugu. Hata durumunda {'hata': ...}."""
    import requests
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return {"hata": "GROQ_API_KEY yok"}
    im = img.convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    b64 = base64.b64encode(buf.getvalue()).decode()
    for deneme in range(4):
        _butce_bekle(TOKEN_TAHMIN)
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": MODEL, "temperature": 0, "max_tokens": 400, "response_format": {"type": "json_object"},
                      "messages": [{"role": "user", "content": [
                          {"type": "text", "text": ISTEM},
                          {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}]}]},
                timeout=60)
        except Exception as exc:
            return {"hata": f"ag: {type(exc).__name__}"}
        if r.status_code == 429:
            m = re.search(r"try again in ([\d.]+)s", r.text)
            time.sleep(float(m.group(1)) + 1 if m else 20)
            continue
        if r.status_code != 200:
            return {"hata": f"HTTP {r.status_code}"}
        try:
            js = json.loads(r.json()["choices"][0]["message"]["content"])
        except Exception:
            return {"hata": "gecersiz JSON"}
        return {k: js.get(k) for k in ("marke", "modell", "stilcode", "groesse", "material", "text", "sicher")}
    return {"hata": "hiz siniri (4 deneme)"}


_MATCHER = None


def _matcher():
    global _MATCHER
    if _MATCHER is None:
        sys.path.insert(0, str(OBS))
        import analyze as A
        _MATCHER = (A, A.ModelMatcher())
    return _MATCHER


def kod_modeli(marka: str, kod: str) -> tuple[str | None, int, int]:
    """Stil kodunun gectigi GERCEK Vinted ilanlarindaki model cogunlugu: (model, destek, toplam)."""
    A, mt = _matcher()
    db = ROOT / "arsiv.db"
    if not db.exists() or not kod:
        return None, 0, 0
    variants = {kod, kod.replace("-", " "), kod.replace("-", "")}
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    say = Counter()
    toplam = 0
    try:
        for v in variants:
            for (t,) in c.execute("SELECT title FROM catalog_samples WHERE lower(brand)=lower(?) AND upper(title) LIKE ? "
                                  "UNION ALL SELECT title FROM listings WHERE lower(brand)=lower(?) AND "
                                  "(upper(title) LIKE ? OR upper(COALESCE(description,'')) LIKE ?)",
                                  (marka, f"%{v}%", marka, f"%{v}%", f"%{v}%")):
                toplam += 1
                model, _ = mt.match(marka, t or "")
                if model:
                    say[model] += 1
    finally:
        c.close()
    # eBay / Kleinanzeigen basliklari stil kodunu cok daha sik yazar ("Nike Dunk Low DD1391-100")
    alis = ROOT / "alis_arsiv.db"
    if alis.exists():
        a = sqlite3.connect(f"file:{alis}?mode=ro", uri=True)
        try:
            for v in variants:
                for (t,) in a.execute("SELECT title FROM eb_items WHERE lower(brand)=lower(?) AND upper(title) LIKE ? "
                                      "UNION ALL SELECT title FROM ka_ads WHERE lower(brand)=lower(?) AND "
                                      "(upper(title) LIKE ? OR upper(COALESCE(descr,'')) LIKE ?)",
                                      (marka, f"%{v}%", marka, f"%{v}%", f"%{v}%")):
                    toplam += 1
                    model, _ = mt.match(marka, t or "")
                    if model:
                        say[model] += 1
        finally:
            a.close()
    if not say:
        return None, 0, toplam
    model, n = say.most_common(1)[0]
    return (model if n >= 2 and n / max(1, sum(say.values())) >= 0.6 else None), n, toplam


def cozumle(okumalar: list[dict], marka_ipucu: str | None) -> dict:
    """Okumalari birlestirip kanita dayali sonuca cevirir."""
    A, mt = _matcher()
    markalar = {b.lower(): b for b in mt.raw if not b.startswith("_")}
    marka = None
    for o in okumalar:
        m = (o.get("marke") or "").strip().lower()
        if m in markalar:
            marka = markalar[m]
            break
    if not marka and marka_ipucu and marka_ipucu.lower() in markalar:
        marka = markalar[marka_ipucu.lower()]
    sonuc = {"marka": marka, "model": None, "kod": None, "kaynak": None, "oneri_model": None,
             "beden": next((o.get("groesse") for o in okumalar if o.get("groesse")), None),
             "metin": " | ".join(filter(None, (o.get("text") for o in okumalar)))[:500]}
    if not marka:
        sonuc["kaynak"] = "marka belirlenemedi"
        return sonuc
    metinler = [o.get("stilcode") for o in okumalar] + [o.get("text") for o in okumalar]
    kod = mt.code(marka, *metinler)
    sonuc["kod"] = kod
    if kod:
        model, n, tot = kod_modeli(marka, kod)
        sonuc["kod_destek"] = f"{n}/{tot} ilan"
        if model:
            sonuc.update(model=model, kaynak=f"stil kodu {kod} ({n} gercek ilanda bu model)")
            return sonuc
    for o in okumalar:
        model, _ = mt.match(marka, f"{o.get('modell') or ''} {o.get('text') or ''}")
        if model:
            sonuc.update(model=model, kaynak="etiket metni (model sozlugunde birebir)")
            return sonuc
    oneri = next((o.get("modell") for o in okumalar if o.get("modell")), None)
    sonuc["oneri_model"] = oneri
    sonuc["kaynak"] = "model dogrulanamadi" + (f" (Groq onerisi: {oneri}; fiyatlamaya girmez)" if oneri else "")
    return sonuc


def urun_etiketi(gorseller: list[Image.Image], marka_ipucu: str | None, en_fazla: int = 2) -> dict:
    """Bir urunun fotograflarindan etiket sonucu. Disari en fazla `en_fazla` fotograf gider."""
    if not gorseller:
        return {"durum": "gorsel yok"}
    puan = _clip_etiket(gorseller)
    sira = sorted(range(len(gorseller)), key=lambda i: -puan[i])
    secilen = [i for i in sira if puan[i] >= ADAY_ESIK][:en_fazla]
    if not secilen:
        return {"durum": "etiket fotografi yok", "clip": [round(x, 2) for x in puan]}
    okumalar = []
    for i in secilen:
        o = groq_oku(gorseller[i])
        o["foto"] = i
        o["clip"] = round(puan[i], 2)
        okumalar.append(o)
    gecerli = [o for o in okumalar if not o.get("hata")]
    if not gecerli:
        return {"durum": "okunamadi", "okumalar": okumalar}
    return {"durum": "ok", **cozumle(gecerli, marka_ipucu), "okumalar": okumalar}
