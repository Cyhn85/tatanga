"""
Durum zekasi + GPSR uygunlugu — ikinci el arbitrajinin iki gercek riskini olcer.

Bu modul iki ayri problemi birlikte cozer, cunku ikisi de AYNI metinden okunur:

RISK 1 — YANLIS BEYAN (para kaybettiren)
  Satici etikette "Sehr gut" yazar, aciklamada "Riss am Aermel" der. Mevcut
  quality_filter yalnizca defekt kelimesi gecen ilani ELER; celiskiyi gormez.
  Oysa asil pahali hata budur: "sehr gut" diye alip hasarli mal gelmesi.
  Burada etiket ile aciklama KARSILASTIRILIR ve celiski ayri bir sinyal olur.

RISK 2 — GPSR UYUMSUZLUGU (ceza yazdiran)
  AB Urun Guvenligi Tuzugu (GPSR) 13.12.2024'ten beri yururlukte; Almanya'da
  uyarlanmis ProdSG ile 19.02.2026 itibariyle tam etkili. TICARI saticinin
  yeniden piyasaya surdugu KULLANILMIS urunleri de kapsiyor. Ilanda uretici
  adi/adresi/elektronik iletisimi ALIM ONCESI gorunur olmali. Bazi hallerde
  100.000 EUR'ya varan idari para cezasi ongoruluyor.

  Istisnalar (tuzugun kendi metninden):
    - acikca "defekt / tamir gerektirir / calismiyor" olarak satilanlar
    - 100 yastan eski antikalar, sanat eserleri, koleksiyon parcalari
  Uretici belirlenemiyorsa hukuken net bir cozum YOK; sektor uygulamasi
  ilanda "Gebrauchtware - Hersteller nicht ermittelbar" notu dusmek.
  Bu modul o notu URETIR ama hukuki garanti VERMEZ — belirsizligi isaretler.

Saf modul: DB/ag bilmez -> izole test edilir. Karar vermez, OLCER ve isaretler;
elemeyi/yayini cagiran taraf yapar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# --- Durum etiketleri: platform/dil bagimsiz 1-5 olcegi -------------------
# 5 = etiketsiz yeni, 1 = belirgin kusurlu. Skor, ARBITRAJ icin kullanilir:
# dusuk skor -> dusuk satis fiyati -> marj daralir.
CONDITION_TERMS: dict[int, list[str]] = {
    5: ["neu mit etikett", "neu mit karton", "nagelneu", "new with tags", "nwt",
        "brand new", "etiketli yeni", "sifir"],
    4: ["neu ohne etikett", "neuwertig", "sehr guter zustand", "sehr gut",
        "wie neu", "new without tags", "nwot", "excellent", "like new",
        "cok iyi", "az kullanilmis"],
    3: ["guter zustand", "gut", "good", "very good", "iyi", "kullanilmis"],
    2: ["akzeptabel", "befriedigend", "gebraucht", "used", "fair",
        "idare eder", "yipranmis"],
    1: ["defekt", "beschaedigt", "bastler", "ersatzteil", "damaged",
        "for parts", "not working", "arizali", "parcalik"],
}

# --- Celiski sinyalleri: aciklamada gecerse etiketle catisir --------------
DEFECT_SIGNALS = {
    "de": ["riss", "loch", "fleck", "defekt", "kaputt", "beschaedigt", "bruch",
           "kratzer", "abgenutzt", "vergilbt", "fehlt", "reparatur", "naht offen",
           "verfaerbt", "pilling", "knoetchen"],
    "en": ["tear", "hole", "stain", "defect", "broken", "damaged", "crack",
           "scratch", "worn", "yellowed", "missing", "repair", "pilling"],
    "tr": ["yirtik", "delik", "leke", "defolu", "kirik", "hasarli", "cizik",
           "yipranmis", "sararmis", "eksik", "tamir", "dikis acik"],
}
POSITIVE_SIGNALS = {
    "de": ["ungetragen", "originalverpackt", "einmal getragen", "keine maengel",
           "makellos", "top zustand"],
    "en": ["unworn", "unused", "worn once", "no flaws", "flawless", "mint"],
    "tr": ["hic giyilmedi", "kullanilmadi", "bir kez giyildi", "kusursuz"],
}

# --- GPSR istisnalari ------------------------------------------------------
GPSR_DEFECT_EXEMPT = ["defekt", "bastler", "ersatzteil", "zur reparatur",
                      "nicht funktionsfaehig", "for parts", "not working",
                      "arizali", "parcalik"]
GPSR_ANTIQUE_EXEMPT = ["antik", "antique", "sammlerstueck", "sammlerstück",
                       "kunstwerk", "gemaelde", "gemälde", "antika"]

# Etiketi olmayan/marka belirsiz urun -> GPSR'de uretici bilgisi verilemez.
UNKNOWN_BRAND_MARKERS = ["no brand", "ohne marka", "markenlos", "unbekannt",
                         "marka yok", "no name", "noname"]

GPSR_UNKNOWN_MANUFACTURER_NOTE_DE = (
    "Gebrauchtware - Hersteller nicht ermittelbar. Angeboten von "
    "CSS Berlin, Am Omnibushof 12, 13593 Berlin, info@cssberlin.de"
)


@dataclass
class ConditionVerdict:
    score: Optional[int] = None            # 1-5, cozulemezse None
    label_source: str = ""                 # skoru veren ham etiket
    confidence: float = 0.0                # 0-1
    conflicting: bool = False              # etiket ile aciklama catisiyor mu
    conflict_terms: list[str] = field(default_factory=list)
    return_risk: str = "unknown"           # low | medium | high | unknown

    # GPSR
    gpsr_required: bool = True             # tuzuk bu urune uygulanir mi
    gpsr_exempt_reason: str = ""
    gpsr_ready: bool = False               # ilanda gerekli bilgi verilebilir mi
    gpsr_missing: list[str] = field(default_factory=list)
    gpsr_note: str = ""                    # ilana konulacak metin (gerekiyorsa)
    brand_resolved: str = ""               # nihai uretici (alandan veya basliktan)
    brand_source: str = ""                 # "alan" | "baslik" | ""

    notes: list[str] = field(default_factory=list)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().strip())


def detect_language(text: str) -> str:
    low = _norm(text)
    if re.search(r"[şğıçö]|kullanilmis|yirtik|beden", low):
        return "tr"
    if re.search(r"\b(zustand|getragen|gebraucht|neuwertig|gr[oö]sse)\b", low):
        return "de"
    if re.search(r"\b(condition|worn|used|size)\b", low):
        return "en"
    return "de"


def score_condition(raw_condition: str, title: str = "") -> tuple[Optional[int], str, float]:
    """
    Ham durum etiketini 1-5'e cevirir. Etiket bossa BASLIKTAN cikarmayi dener
    (TATANGA'da products.condition cogu zaman bos geliyor).
    Doner: (skor, kaynak_etiket, guven)
    """
    for kaynak, guven in ((raw_condition, 0.9), (title, 0.6)):
        low = _norm(kaynak)
        if not low:
            continue
        # Uzun ifadeler once denenir ("neu ohne etikett" -> 4, "neu" -> 5 degil)
        for skor in (5, 4, 3, 2, 1):
            for terim in sorted(CONDITION_TERMS[skor], key=len, reverse=True):
                if terim in low:
                    return skor, terim, guven
    return None, "", 0.0


def resolve_brand(brand: str, title: str, known_brands: Optional[list[str]] = None) -> tuple[str, str]:
    """
    Ureticiyi belirler. brand alani bos olabilir (eBay kaziyicisi doldurmuyor)
    ama uretici BASLIKTA apacik durabilir: "The North Face Herren Regenjacke".
    O durumda ilana "Hersteller nicht ermittelbar" yazmak hem gereksiz hem yanlis.

    known_brands DISARIDAN verilir (DB'deki gercek markalar) -> modul saf kalir.
    Doner: (marka, kaynak) — kaynak: "alan" | "baslik" | ""
    """
    marka = (brand or "").strip()
    if marka and not any(m in marka.lower() for m in UNKNOWN_BRAND_MARKERS):
        return marka, "alan"

    low = _norm(title)
    if not low:
        return "", ""
    adaylar = sorted((a.strip() for a in (known_brands or []) if a and len(a.strip()) >= 3),
                     key=len, reverse=True)   # uzun once: "the north face" > "north face"

    # 1) Tam kelime eslesmesi — en guvenli.
    for aday in adaylar:
        if re.search(r"(?<![a-z0-9])" + re.escape(aday.lower()) + r"(?![a-z0-9])", low):
            return aday, "baslik"

    # 2) Yazim varyantlari. GERCEK ilan basliklarinda gorulen iki desen:
    #      "The Northface" (bitisik yazim), "North Face" (bastaki 'the' dusmus).
    # Bosluk/tire kaldirilmis bicimde karsilastirilir. Yanlis eslesmeyi onlemek
    # icin en az 7 karakter sarti var — kisa markalarda ("nike") bitisik arama
    # "nikeschuhbank" gibi kelimelerin icine dusebilirdi.
    sikis = re.sub(r"[^a-z0-9]", "", low)
    for aday in adaylar:
        for varyant in (aday.lower(), re.sub(r"^the\s+", "", aday.lower())):
            v = re.sub(r"[^a-z0-9]", "", varyant)
            if len(v) >= 7 and v in sikis:
                return aday, "baslik"
    return "", ""


def analyze(
    *,
    title: str = "",
    description: str = "",
    raw_condition: str = "",
    brand: str = "",
    category: str = "",
    known_brands: Optional[list[str]] = None,
) -> ConditionVerdict:
    """
    Bir ilani hem YANLIS BEYAN hem GPSR acisindan degerlendirir.
    Hicbir seyi elemez — sinyal uretir; kararı cagiran taraf verir.
    """
    verdict = ConditionVerdict()
    metin = f"{title} {description}"
    dil = detect_language(metin)

    # --- 1) Durum skoru ---
    skor, kaynak, guven = score_condition(raw_condition, title)
    verdict.score, verdict.label_source, verdict.confidence = skor, kaynak, guven

    # --- 2) Celiski: etiket iyi diyor ama aciklama kusur sayiyor ---
    aciklama = _norm(description)
    kusurlar = [k for k in DEFECT_SIGNALS.get(dil, DEFECT_SIGNALS["de"]) if k in aciklama]
    olumlular = [k for k in POSITIVE_SIGNALS.get(dil, POSITIVE_SIGNALS["de"]) if k in aciklama]

    if kusurlar and skor is not None and skor >= 4:
        # "Sehr gut" etiketi + aciklamada "Riss" -> guvenilmez beyan
        verdict.conflicting = True
        verdict.conflict_terms = kusurlar
        verdict.confidence = min(verdict.confidence, 0.5)
        verdict.notes.append(
            f"etiket '{kaynak}' iyi durum diyor ama aciklamada kusur gecıyor: "
            f"{', '.join(kusurlar[:3])}")
    elif olumlular:
        verdict.confidence = min(verdict.confidence + 0.1, 1.0)

    # --- 3) Iade riski: arbitrajda asil maliyet kalemi ---
    if verdict.conflicting:
        verdict.return_risk = "high"
    elif skor is None:
        verdict.return_risk = "unknown"
        verdict.notes.append("durum belirlenemedi — korumali fiyatlama onerilir")
    elif skor <= 2 or kusurlar:
        verdict.return_risk = "medium"
    else:
        verdict.return_risk = "low"

    # --- 4) GPSR ---
    low_all = _norm(metin + " " + raw_condition)
    if any(t in low_all for t in GPSR_DEFECT_EXEMPT):
        verdict.gpsr_required = False
        verdict.gpsr_exempt_reason = ("acikca defekt/tamirlik olarak satiliyor — "
                                      "GPSR kapsami disinda")
    elif any(t in low_all for t in GPSR_ANTIQUE_EXEMPT):
        verdict.gpsr_required = False
        verdict.gpsr_exempt_reason = "antika/sanat eseri/koleksiyon — GPSR kapsami disinda"

    if verdict.gpsr_required:
        cozulen_marka, marka_kaynagi = resolve_brand(brand, title, known_brands)
        verdict.brand_resolved = cozulen_marka
        verdict.brand_source = marka_kaynagi
        if not cozulen_marka:
            verdict.gpsr_missing.append("uretici (marka) belirlenemedi")
            verdict.gpsr_note = GPSR_UNKNOWN_MANUFACTURER_NOTE_DE
            verdict.notes.append(
                "GPSR: uretici belirlenemedi. Ilana 'Hersteller nicht ermittelbar' "
                "notu konulmali; bu uygulamanin net hukuki dayanagi YOK, "
                "belirsizlik bilinerek ustlenilir.")
        else:
            verdict.gpsr_ready = True
            verdict.gpsr_note = (
                f"Hersteller: {cozulen_marka}. Inverkehrbringer: CSS Berlin, "
                f"Am Omnibushof 12, 13593 Berlin, info@cssberlin.de")
            if marka_kaynagi == "baslik":
                verdict.notes.append(
                    f"uretici marka alaninda yoktu, basliktan cozuldu: {cozulen_marka}")
    else:
        verdict.gpsr_ready = True   # istisna kapsaminda, engel yok

    return verdict


def should_avoid(verdict: ConditionVerdict) -> tuple[bool, str]:
    """
    Alinmamasi gereken ilan mi? Sadece EN NET durum icin True doner —
    asiri eleyici olmak, karli firsatlari da eler.
    """
    if verdict.conflicting:
        return True, ("beyan celiskisi: etiket iyi durum diyor, aciklama kusur sayiyor "
                      "(iade/hasar riski yuksek)")
    if verdict.score is not None and verdict.score <= 1:
        return True, "urun defekt/parcalik olarak satiliyor"
    return False, ""
