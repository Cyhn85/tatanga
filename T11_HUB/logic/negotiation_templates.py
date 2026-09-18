"""
Pazarlik mesaj sablonlari (saf, additive).

ONEMLI GUVENLIK NOTU: Bu modul yalnizca TASLAK metin uretir. Hicbir mesaji
otomatik gondermez. Uretilen her mesaj kullaniciya (Telegram onay akisi uzerinden)
sunulur ve GONDERIM her zaman insan onayiyla yapilir. Otomatik satici-mesajlasma
kural geregi yasak — bu modul sadece metni hazirlar.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

# Almanca sablonlar. {..} alanlari render sirasinda doldurulur.
TEMPLATES: dict[str, str] = {
    "availability_check":
        "Hallo, ist der Artikel \"{title}\" noch verfugbar? "
        "Wann konnten Sie versenden?",
    "initial_offer":
        "Hallo, ich interessiere mich fur \"{title}\". "
        "Waren Sie mit {offer_price} EUR statt {list_price} EUR einverstanden?",
    "counter_offer":
        "Danke fur Ihr Angebot. Wurden Sie {counter_price} EUR akzeptieren? "
        "Ich kann zeitnah bezahlen.",
    "bundle_offer":
        "Hallo, ich interessiere mich fur mehrere Ihrer Artikel. "
        "Ware ein Paketpreis von {bundle_price} EUR moglich?",
    "accept":
        "Perfekt, ich nehme es fur {agreed_price} EUR. "
        "Konnten Sie mir bitte die Zahlungsdaten senden?",
    "decline":
        "Danke fur die Ruckmeldung, das passt preislich leider nicht. "
        "Viel Erfolg beim Verkauf!",
}

# Platform bazli ton: Kleinanzeigen daha samimi/kisa, Vinted daha net/resmi.
PLATFORM_TONE: dict[str, dict] = {
    "kleinanzeigen": {"greeting": "Hallo", "closing": "VG", "max_len": 220},
    "vinted":        {"greeting": "Hallo", "closing": "Danke", "max_len": 200},
    "ebay":          {"greeting": "Guten Tag", "closing": "Mit freundlichen Grussen", "max_len": 260},
    "willhaben":     {"greeting": "Hallo", "closing": "LG", "max_len": 220},
}
_DEFAULT_TONE = {"greeting": "Hallo", "closing": "VG", "max_len": 220}

# Platform bazli pazarlik davranisi (mesaj vs. yerlesik teklif butonu)
# NOT: Vinted'de saticidan kargo adresi belirlenemez; teklif "Make an offer"
# butonuyla, mesajla degil. Kleinanzeigen'de pazarlik mesajla yapilir.
PLATFORM_NEGOTIATION_MODE: dict[str, str] = {
    "kleinanzeigen": "message",   # mesajla pazarlik, adres/kargo anlasmali
    "vinted":        "offer_button",  # yerlesik teklif; adres Vinted'e bagli
    "ebay":          "best_offer",
    "willhaben":     "message",
}


class DraftMessage(BaseModel):
    platform: str
    template_key: str
    text: str
    within_length: bool
    negotiation_mode: str
    requires_human_approval: bool = True  # her zaman True


def render(
    template_key: str,
    platform: str,
    *,
    with_greeting: bool = True,
    **fields,
) -> DraftMessage:
    """
    Sablonu doldurur ve platform tonuna gore selam/kapanis ekler.
    GONDERMEZ — sadece taslak dondurur (requires_human_approval=True).
    """
    if template_key not in TEMPLATES:
        raise KeyError(f"bilinmeyen sablon: {template_key}")
    tone = PLATFORM_TONE.get(platform.lower(), _DEFAULT_TONE)

    body = TEMPLATES[template_key].format(**fields)
    parts = []
    if with_greeting and not body.lower().startswith(tone["greeting"].lower()):
        parts.append(tone["greeting"] + ",")
    parts.append(body)
    parts.append(tone["closing"])
    text = " ".join(parts).strip()

    return DraftMessage(
        platform=platform,
        template_key=template_key,
        text=text,
        within_length=len(text) <= tone["max_len"],
        negotiation_mode=PLATFORM_NEGOTIATION_MODE.get(platform.lower(), "message"),
        requires_human_approval=True,
    )
