"""
Marka kimlik karti — TEK KAYNAK yukleyicisi + iddia bekcisi (saf, additive, ucretsiz).

`data/brand_identity.json` bu projedeki tek marka kaynagidir. Reklam/kampanya
motoru (#140), kompozisyon video modulu (#141), TTS (#142) ve cssberlin ticker'i
(#145) renk/tipografi/dil/iddia kurallarini buradan okur — her modul kendi
kopyasini tutmaz, boylece marka zamanla dagilmaz.

EN KRITIK PARCA: `check_claim()`. Otomatik uretilen HICBIR kampanya metni,
kanitlanmamis bir iddiayla disari cikmamali. Bu sadece bir "iyi uygulama" degil:
- Kullanicinin kendi kurali: fiyat karsilastirmasi ICERIDE kalir, Almanya UWG
  nedeniyle "X sitede su fiyat" reklami YAPILMAZ.
- Gercek olay: canli sitede "Versandkostenfrei erste Bestellung" iddiasi vardi
  ama checkout'ta boyle bir mekanizma YOK; ayni ticker'da sabit yazilmis
  "45.2K Artikel" / "12,8t CO2" sayilari duruyor — canli /api/eco-impact
  gercekte 1 urun / 14 kg diyor. Bu bekci tam olarak bu sinifi yakalar.

Saf modul: DB/ag bilmez, sadece JSON okur ve metin denetler -> izole test edilir.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "brand_identity.json"
_CACHE: dict[str, dict] = {}


# --------------------------------------------------------------------- yukleme
def load_brand(path: Optional[Path] = None, *, reload: bool = False) -> dict:
    """Marka kartini okur (varsayilan: data/brand_identity.json). Sonuc onbellege alinir."""
    target = Path(path) if path else _DEFAULT_PATH
    key = str(target)
    if reload or key not in _CACHE:
        with open(target, encoding="utf-8") as fh:
            _CACHE[key] = json.load(fh)
    return _CACHE[key]


def identity(**kw) -> dict:
    return load_brand(**kw).get("identity", {})


def palette(**kw) -> dict:
    """Renkler — video/reklam gorselinin marka rengini uydurmasini onler."""
    return {k: v for k, v in load_brand(**kw).get("palette", {}).items()
            if not k.startswith("_")}


def voice(**kw) -> dict:
    return load_brand(**kw).get("voice", {})


def facts(**kw) -> dict:
    """Su an GERCEKTEN dogru olan seyler (iddia bekcisi bunlari okur)."""
    return {k: v for k, v in load_brand(**kw).get("facts", {}).items()
            if not k.startswith("_")}


def missing_inputs(**kw) -> list[str]:
    """Kullanicinin doldurmasi gereken yaratici alanlar (marka sesi uydurulmaz)."""
    return list(voice(**kw).get("needs_user_input", []))


def dynamic_claim(claim_id: str, **kw) -> Optional[dict]:
    """Sayisal bir iddianin CANLI kaynagini dondurur (sabit sayi yazmak yerine)."""
    for item in load_brand(**kw).get("claims", {}).get("dynamic", []):
        if item.get("id") == claim_id:
            return item
    return None


# ---------------------------------------------------------------- iddia bekcisi
@dataclass
class ClaimViolation:
    category: str
    severity: str      # "forbidden" | "warn"
    matched: str       # metinde yakalanan parca
    reason: str        # insan-okunur (TR)

    def __str__(self) -> str:
        return f"[{self.severity}] {self.category}: '{self.matched}' — {self.reason}"


# Almanca umlaut toleransi. Bu kod tabani her yerde ASCII translit yaziyor
# ("Kaeuferschutz", "fuer", "Schaetze"), ama uretilen metin gercek umlaut da
# icerebilir. Desenlerde {ue}/{oe}/{ae}/{ss} yer tutucularini kullan; her ucu de
# (u / ü / ue) kabul edilir. Bu olmadan "guenstigste" gozden kaciyordu.
_UMLAUT_CLASSES = {
    "{ue}": "(?:ü|ue|u)", "{oe}": "(?:ö|oe|o)",
    "{ae}": "(?:ä|ae|a)", "{ss}": "(?:ß|ss|s)",
}


def _expand(pattern: str) -> str:
    for placeholder, klass in _UMLAUT_CLASSES.items():
        pattern = pattern.replace(placeholder, klass)
    return pattern


# Kategori -> (severity, TR gerekce, {dil: [regex...]})
# Diller: de (birincil), en, tr. Desen listesi bos olan dil o kategoride atlanir.
_PATTERNS: dict[str, tuple[str, str, dict[str, list[str]]]] = {
    "comparative_price": (
        "forbidden",
        "Rakip fiyatiyla karsilastirma. Fiyat karsilastirmasi ICERIDE kalir; "
        "Almanya UWG nedeniyle disariya reklam olarak verilmez.",
        {
            "de": [r"\b(?:billiger|g{ue}nstiger)\s+als\b",
                   r"\b(?:bei|auf)\s+(?:vinted|ebay|kleinanzeigen|momox|sellpy|willhaben|depop|leboncoin|tradera)\b"
                   r"[^.!?]{0,40}?(?:kostet|preis|€|eur)\b"],
            "en": [r"\bcheaper\s+than\b",
                   r"\b(?:on|at)\s+(?:vinted|ebay|kleinanzeigen|depop)\b[^.!?]{0,40}?(?:costs?|price|€|eur)\b"],
            "tr": [r"\bdaha\s+ucuz\b", r"\b(?:vinted|ebay|kleinanzeigen)['’]?d[ae]\b[^.!?]{0,40}?(?:fiyat|€|eur)\b"],
        },
    ),
    "unbacked_superlative": (
        "forbidden",
        "Kanitlanmamis ustunluk iddiasi (en ucuz/en iyi/1 numara). Alman reklam "
        "hukukunda kanit yuku reklam verendedir.",
        {
            # (?<!am\s) -> "am besten" deyimi bir ustunluk iddiasi degil, elenmez.
            "de": [r"\b(?:g{ue}nstigste|billigste|gr{oe}{ss}te)(?:r|n|s|m)?\b",
                   r"(?<!am\s)\bbeste(?:r|n|s|m)?\b",
                   r"\bnummer\s*1\b", r"\bnr\.?\s*1\b"],
            # "Best regards / best wishes / all the best" selamlamadir, ustunluk
            # iddiasi degil — Almanca'daki "am besten" deyimiyle ayni durum.
            "en": [r"\b(?:cheapest|lowest\s+price)\b",
                   r"(?<!all the )\bbest\b(?!\s+(?:regards|wishes))",
                   r"\bnumber\s*one\b", r"\bno\.?\s*1\b"],
            "tr": [r"\ben\s+(?:ucuz|iyi|buyuk|b[uü]y[uü]k)\b", r"\bbir\s+numara\b"],
        },
    ),
    "free_shipping": (
        "forbidden",
        "Ucretsiz kargo vaadi. Checkout'ta boyle bir mekanizma UYGULANMIYOR "
        "(facts.free_shipping_first_order = false). Gerceklesene kadar kullanilamaz.",
        {
            "de": [r"\bversandkostenfrei\b", r"\bkostenlose[rn]?\s+versand\b", r"\bgratis\s+versand\b"],
            "en": [r"\bfree\s+shipping\b", r"\bshipping\s+is\s+free\b"],
            "tr": [r"\b(?:[uü]cretsiz|bedava)\s+kargo\b"],
        },
    ),
    "hardcoded_stat": (
        "forbidden",
        "Metne SABITLENMIS istatistik. Sayilar canli kaynaktan okunmali "
        "(claims.dynamic -> source_url); aksi halde gercekle uyusmaz.",
        {
            "de": [r"\d[\d.,]*\s*(?:k|m|mio\.?|t|kg|tonnen?)?\s*"
                   r"(?:co2|artikel|nutzer|mitglieder|verk{ae}ufe)\b"],
            "en": [r"\d[\d.,]*\s*(?:k|m|t|kg|tons?)?\s*(?:co2|items|users|members|sales)\b"],
            "tr": [r"\d[\d.,]*\s*(?:k|m|t|kg)?\s*(?:co2|[uü]r[uü]n|kullan[ıi]c[ıi]|[uü]ye)\b"],
        },
    ),
    "greenwashing": (
        "warn",
        "Cevre iddiasi kanit ister (klimaneutral/CO2-frei/100% nachhaltig). "
        "Almanya'da yesil aklama davalari yaygin — somut hesap olmadan kullanma.",
        {
            "de": [r"\bklimaneutral\b", r"\bco2[\s-]?frei\b", r"\b100\s*%\s*nachhaltig\b"],
            "en": [r"\bclimate[\s-]?neutral\b", r"\bcarbon[\s-]?free\b", r"\b100\s*%\s*sustainable\b"],
            "tr": [r"\b(?:iklim|karbon)\s+n[oö]tr\b", r"\b%\s*100\s+s[uü]rd[uü]r[uü]lebilir\b"],
        },
    ),
    "fake_urgency": (
        "warn",
        "Yapay aciliyet. Sadece GERCEK bir kampanya bitis tarihi varsa kullanilabilir.",
        {
            "de": [r"\bnur\s+heute\b", r"\bletzte\s+chance\b", r"\bnur\s+noch\s+\d+\b"],
            "en": [r"\bonly\s+today\b", r"\blast\s+chance\b", r"\bonly\s+\d+\s+left\b"],
            "tr": [r"\bsadece\s+bug[uü]n\b", r"\bson\s+[sş]ans\b", r"\bson\s+\d+\s+adet\b"],
        },
    ),
}

# Kategoriyi serbest birakan gercek/bayrak. Bayrak True ise o kategori denetlenmez.
_GATED_BY_FACT = {
    # Ucretsiz kargo iddiasi, checkout'ta GERCEKTEN uygulanan bir kural varsa
    # serbest kalir. Bugun oyle: cssberlin src/config/shipping-policy.ts
    # (50 EUR ustu her siparis, ilk sipariste 30 EUR ustu).
    "free_shipping": "free_shipping_over_threshold",
    "comparative_price": "price_comparison_public",
}


def check_claim(
    text: str,
    *,
    lang: str = "de",
    brand_facts: Optional[dict] = None,
    stats_from_live_source: bool = False,
) -> list[ClaimViolation]:
    """
    Uretilen bir kampanya/reklam/altyazi metnini marka iddia kurallarina karsi denetler.

    lang: "de" | "en" | "tr"
    brand_facts: None ise karttaki `facts` okunur. Bir bayrak True ise ilgili
                 kategori artik yasak degildir (ornek: ucretsiz kargo gercekten
                 devreye girdiginde).
    stats_from_live_source: sayilar canli uctan (claims.dynamic.source_url)
                 okunduysa True ver — o zaman sayisal iddia serbesttir.

    Donen liste BOS ise metin yayina uygundur.
    """
    if not text:
        return []
    known = brand_facts if brand_facts is not None else facts()
    found: list[ClaimViolation] = []

    for category, (severity, reason, by_lang) in _PATTERNS.items():
        gate = _GATED_BY_FACT.get(category)
        if gate and known.get(gate):
            continue
        if category == "hardcoded_stat" and stats_from_live_source:
            continue
        for pattern in by_lang.get(lang, []):
            for match in re.finditer(_expand(pattern), text, flags=re.IGNORECASE):
                found.append(ClaimViolation(
                    category=category, severity=severity,
                    matched=match.group(0).strip(), reason=reason,
                ))
    return found


def is_claim_safe(text: str, **kw) -> bool:
    """Yayina uygun mu — 'warn' seviyesi engellemez, sadece 'forbidden' engeller."""
    return not any(v.severity == "forbidden" for v in check_claim(text, **kw))
