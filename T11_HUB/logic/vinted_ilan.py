"""
VINTED SATIS ASISTANI (2026-10-20). Satin alinan urun icin Vinted (DE) ilan taslagi: baslik, aciklama, kategori yolu,
kondisyon, beden, fiyat onerisi. GIRIS YOK / GONDERIM YOK: kullanici kopyalayip Vinted uygulamasinda kendisi yayinlar.

Kurallar:
  - UYDURMA YOK. Baslik ve aciklamada yalniz bilinen bilgi (marka, etiketten/basliktan dogrulanmis model, stil kodu,
    beden, renk, kondisyon, malzeme). Bilinmeyen (olculer, kusur) kullanicinin dolduracagi bos alan olarak kalir.
  - Fiyat gercek Vinted satislarindan (zeka_*): liste fiyati = medyan (pazarlik payi icin yukari yuvarlanir),
    alt sinir = P25 (bunun altindaki teklif tutucu karin altina iner). Satis verisi yoksa fiyat ONERILMEZ.
  - Groq (opsiyonel) yalniz dili duzeltir: ayni bilgiler, yeni iddia eklenemez (cikti dogrulanir; yeni rakam/marka
    eklerse sablon kullanilir).
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from pathlib import Path

OBS = Path(__file__).resolve().parents[1] / "ops" / "hetzner_observer"

TUR_DE = {
    "kaz_tuyu": "Daunenjacke", "kislik": "Winterjacke", "deri": "Lederjacke", "kayak": "Skijacke", "polar": "Fleecejacke",
    "parka": "Parka", "yagmurluk": "Regenjacke", "softshell": "Softshelljacke", "ruzgarlik": "Windjacke",
    "yelek": "Weste", "kaban": "Mantel", "bomber": "Bomberjacke", "esofman": "Trainingsjacke", "kot_ceket": "Jeansjacke",
    "kot_pantolon": "Jeans", "kapusonlu": "Hoodie", "sweatshirt": "Sweatshirt", "triko": "Strickpullover",
    "sneaker": "Sneaker", "bot": "Boots", "topuklu": "Pumps", "babet": "Ballerinas", "loafer": "Loafer",
    "klasik": "Schnürschuhe", "espadril": "Espadrilles", "terlik": "Pantoletten", "kosu": "Laufschuhe",
    "trekking": "Wanderschuhe", "sandalet": "Sandalen", "krampon": "Fußballschuhe",
}
KAT_DE = {"jacken": "Jacke", "schuhe": "Schuhe", "oberteile": "Pullover", "jeans": "Jeans"}
KAT_YOL = {
    "jacken": "Kleidung › Jacken & Mäntel", "oberteile": "Kleidung › Pullover & Sweatshirts",
    "jeans": "Kleidung › Jeans", "schuhe": "Schuhe",
}
KOND_DE = {"yeni_etiketli": "Neu mit Etikett", "yeni": "Neu ohne Etikett", "cok_iyi": "Sehr gut", "iyi": "Gut"}
CINSIYET_RE = (("Damen", re.compile(r"\b(damen|women|woman|ladies|femme|donna|mujer|dames|dam)\b", re.I)),
               ("Herren", re.compile(r"\b(herren|men|mens|homme|uomo|hombre|heren|herr)\b", re.I)))


def _ctx():
    sys.path.insert(0, str(OBS))
    import analyze as A
    import capraz as C
    return A, C


def _yuvarla_liste(x: float) -> int:
    """Vinted'de alisilmis fiyat sonu 5 ya da 9 (yukari yuvarlanir): 33.2 -> 35, 36 -> 39, 40.1 -> 45, 18.3 -> 19."""
    if x < 10:
        return int(math.ceil(x))
    taban = int(x // 10) * 10
    return min(v for v in (taban + 5, taban + 9, taban + 15, taban + 19) if v >= x)


def taslak(p: dict) -> dict:
    A, C = _ctx()
    title = p.get("title") or ""
    et = {}
    try:
        et = json.loads(p.get("etiket_json") or "{}") or {}
    except ValueError:
        pass
    brand = p.get("brand") or et.get("marka") or ""
    mt = A.ModelMatcher()
    model, line = mt.match(brand, title) if brand else (None, None)
    model_kaynak = "baslik"
    if not model and et.get("durum") == "ok" and et.get("model"):
        model, model_kaynak = et["model"], "etiket"
    kod = mt.code(brand, title, p.get("description")) if brand else None
    kod = kod or et.get("kod")
    typ = A.match_type(A.norm_text(title))
    cat = next(iter(C.TYPE_CAT[typ]), None) if typ in C.TYPE_CAT and len(C.TYPE_CAT[typ]) == 1 else None
    if cat is None:
        nt = A.norm_text(title)
        cat = next((k for k, rx in C.CAT_WORDS.items() if rx.search(nt)), None)
    if cat is None and (model or line):
        # baslikta tur yok ama model biliniyor (or. etiketten Gel-NYC): kategori gercek veriden (zeka_urunler yazar)
        try:
            mk = json.load(open(OBS.parents[2] / "istatistik" / "model_kategori.json", encoding="utf-8"))
            cat = mk.get(f"{brand.lower()}|{(model or line).lower()}")
        except (OSError, ValueError):
            pass
    tur = TUR_DE.get(typ) or KAT_DE.get(cat or "", "")
    # cok dilli kondisyon (Vinted UK 'Very good', FR 'Neuf avec etiquette', noktalama farki) - puanlamayla AYNI sozluk
    import zeka_urunler as Z
    kt = " ".join(re.findall(r"[^\W_]+", (p.get("condition") or "").lower()))
    tier = (A.norm_condition(p.get("condition")) or Z.KOND_EXTRA.get(A.norm_text(p.get("condition") or ""))
            or A.norm_condition(kt) or Z.KOND_EXTRA.get(kt))
    kond = KOND_DE.get(tier or "", p.get("condition") or "")
    beden = (p.get("size") or et.get("beden") or "").strip()
    renk = (p.get("color") or "").strip()
    cins = next((g for g, rx in CINSIYET_RE if rx.search(title)), None)

    # BASLIK: Marke Modell Typ Gr. X Farbe (Vinted ~ 60 karakter gorunur)
    parcalar = [brand, model or line or "", tur, f"Gr. {beden}" if beden else "", renk]
    baslik = re.sub(r"\s+", " ", " ".join(x for x in parcalar if x)).strip()
    if len(baslik) > 60:
        baslik = re.sub(r"\s+", " ", " ".join(x for x in parcalar[:4] if x)).strip()[:60]

    satirlar = [f"{brand} {model or line or ''} {tur}".replace("  ", " ").strip() + (f" – {cins}" if cins else ""), ""]
    satirlar.append(f"Zustand: {kond}" if kond else "Zustand: ")
    satirlar.append(f"Größe: {beden}" if beden else "Größe: ")
    if renk:
        satirlar.append(f"Farbe: {renk}")
    if et.get("durum") == "ok" and et.get("metin"):
        mat = re.search(r"(\d{1,3}\s?%\s?[A-Za-zÄÖÜäöüß]+(?:[ ,/]+\d{1,3}\s?%\s?[A-Za-zÄÖÜäöüß]+)*)", et["metin"])
        if mat:
            satirlar.append(f"Material (laut Etikett): {mat.group(1)}")
    if kod:
        satirlar.append(f"Artikelnummer: {kod}")
    satirlar += ["", "Maße (liegend gemessen): Länge __ cm, Achsel bis Achsel __ cm" if cat != "schuhe"
                 else "Innensohle: __ cm", "",
                 "Mängel: __ (bitte Fotos beachten)", "",
                 "Versand mit Vinted-Versand. Bei Fragen gerne melden."]
    aciklama = "\n".join(satirlar)

    # FIYAT: gercek Vinted satislari
    fiyat = None
    if p.get("zeka_satis_medyan") and p.get("zeka_satis_p25"):
        med, p25 = float(p["zeka_satis_medyan"]), float(p["zeka_satis_p25"])
        fiyat = {"liste": _yuvarla_liste(med * 1.05), "medyan": round(med, 2), "alt_sinir": round(p25, 2),
                 "satis_n": p.get("zeka_n"), "seviye": p.get("zeka_seviye"),
                 "p30": p.get("zeka_p30"),
                 "not": "Liste fiyati gercek satis medyaninin ~%5 ustu (teklif payi). Alt sinirin altindaki teklif "
                        "tutucu kari asindirir."}
        if str(p.get("zeka_seviye") or "").startswith("marka·kategori"):
            fiyat["zayif"] = True
            fiyat["not"] = ("ZAYIF DAYANAK: yalniz marka+kategori satislari (farkli urun turleri karisik). Benzer ilanlara "
                            "Vinted'de bakip kontrol et. " + fiyat["not"])
    eksik = [x for x, v in (("beden", beden), ("kondisyon", kond), ("model", model or line), ("tur", tur)) if not v]
    return {
        "baslik": baslik, "aciklama": aciklama, "kategori_yolu": " › ".join(x for x in (cins, KAT_YOL.get(cat or "")) if x),
        "kondisyon": kond, "beden": beden, "marka": brand, "model": model or line, "model_kaynak": model_kaynak if model else None,
        "kod": kod, "fiyat": fiyat, "eksik": eksik,
        "fiyat_yok_neden": None if fiyat else "gercek satis verisi yok (zeka puani yok); fiyat uydurulmaz",
    }


def groq_cila(t: dict) -> dict:
    """Dili akicilastirir; yeni bilgi EKLEYEMEZ. Dogrulama: ciktidaki rakamlar ve marka girdide olmali."""
    import requests
    key = os.getenv("GROQ_API_KEY")
    if not key or os.getenv("GROQ_MESSAGE_DRAFT_ENABLED", "").lower() != "true":
        return {**t, "cila": "kapali"}
    sistem = ("Du überarbeitest eine Vinted-Artikelbeschreibung auf Deutsch: freundlich, klar, kurz. STRENG: keine neuen "
              "Fakten, keine Zahlen, Materialien, Mängel oder Eigenschaften hinzufügen, die nicht im Text stehen. "
              "Platzhalter '__' unverändert lassen. Antworte NUR mit JSON {\"beschreibung\": \"...\"}.")
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                          json={"model": os.getenv("GROQ_TEXT_MODEL", "qwen/qwen3.8-27b"), "temperature": 0.2,
                                "max_tokens": 700, "response_format": {"type": "json_object"},
                                "messages": [{"role": "system", "content": sistem},
                                             {"role": "user", "content": t["aciklama"]}]}, timeout=40)
        if r.status_code != 200:
            return {**t, "cila": f"sablon (Groq HTTP {r.status_code})"}
        yeni = json.loads(r.json()["choices"][0]["message"]["content"]).get("beschreibung", "").strip()
    except Exception as exc:
        return {**t, "cila": f"sablon (Groq: {type(exc).__name__})"}
    eski_rakam = set(re.findall(r"\d+", t["aciklama"]))
    yeni_rakam = set(re.findall(r"\d+", yeni))
    if not yeni or not yeni_rakam <= eski_rakam or yeni.count("__") < t["aciklama"].count("__") or \
            (t["marka"] and t["marka"].lower() not in yeni.lower()):
        return {**t, "cila": "sablon (Groq ciktisi yeni bilgi ekledi ya da bosluklari sildi -> reddedildi)"}
    return {**t, "aciklama": yeni, "cila": "groq (dil duzeltmesi, dogrulandi)"}
