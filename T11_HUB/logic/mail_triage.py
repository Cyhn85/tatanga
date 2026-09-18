"""
Gelen posta siniflandirma + yanit taslagi (saf, deterministik, ucretsiz).

Amac: butun platformlar (Vinted, eBay, Instagram, TikTok, YouTube, Pinterest,
PayPal...) olan biteni e-posta ile bildiriyor. Tek posta kutusu, tum hesaplarin
ortak olay akisi haline gelir — hicbir API onayi beklemeden, bugun.

GUVENLIK SINIRI — BU MODULUN EN ONEMLI OZELLIGI:
Gelen e-posta GUVENILMEZ GIRDIDIR. Icinde "su siparisi iade et", "sifreyi
gonder", "su adrese para yolla" yazabilir; gonderen kendini kargo firmasi ya
da platform gibi tanitabilir. Bu yuzden burada e-postanin ICERIGI hicbir zaman
komut olarak yorumlanmaz. Modul yalnizca:
    - postayi SINIFLANDIRIR (ne tur bir sey bu),
    - insana gosterilecek kisa bir OZET cikarir,
    - gerekiyorsa TASLAK yanit onerir.
Taslak daima insan onayina gider; bu modul hicbir sey gondermez, hicbir
islem tetiklemez. Disari giden her metin ayrica marka iddia bekcisinden gecer.

Saf modul: ag/DB bilmez, mesaj alanlari disaridan verilir -> izole test edilir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from . import brand_identity as brand

# Bildirim gonderen platformlar (alan adina gore). Bunlar "olay haberi"dir,
# musteri mesaji degil — yanit taslagi uretilmez.
PLATFORM_DOMAINS = {
    "vinted": "Vinted", "ebay": "eBay", "kleinanzeigen": "Kleinanzeigen",
    "willhaben": "Willhaben", "tradera": "Tradera", "leboncoin": "Leboncoin",
    "instagram": "Instagram", "facebookmail": "Facebook", "tiktok": "TikTok",
    "youtube": "YouTube", "google": "Google", "pinterest": "Pinterest",
}
# Para hareketi bildiren gonderenler — muhasebeye gitmeli, yanit gerekmez.
FINANCE_DOMAINS = {"paypal": "PayPal", "stripe": "Stripe", "klarna": "Klarna"}

# Musteri niyeti ipuclari (DE/EN/TR/UK) — yanit taslagi bu sinifta uretilir.
INTENT_PATTERNS = {
    "shipping": [r"\bversand\b", r"\bsendung\b", r"\blieferung\b", r"\btracking\b",
                 r"\bshipping\b", r"\bkargo\b", r"\bдоставк"],
    "return": [r"\bruck(gabe|sendung)\b", r"\bwiderruf\b", r"\bretoure\b",
               r"\breturn\b", r"\bi̇ade\b", r"\biade\b", r"\bповерн"],
    "availability": [r"\bverfugbar\b", r"\bnoch da\b", r"\bavailable\b",
                     r"\bmevcut\b", r"\bstokta\b"],
    "price": [r"\bpreis\b", r"\brabatt\b", r"\bprice\b", r"\bdiscount\b",
              r"\bfiyat\b", r"\bindirim\b"],
}

CATEGORY_LABELS = {
    "platform_notification": "Platform bildirimi",
    "finance": "Para hareketi",
    "customer_message": "Musteri mesaji",
    "marketing": "Reklam / bulten",
    "other": "Diger",
}


@dataclass
class MailVerdict:
    category: str
    label: str
    source: str = ""                 # Vinted / PayPal / ...
    intent: Optional[str] = None     # shipping / return / availability / price
    summary: str = ""                # insana gosterilecek tek satir
    draft_reply: Optional[str] = None
    draft_lang: str = "de"
    needs_human: bool = True         # DAIMA True — otomatik gonderim yok
    warnings: list[str] = field(default_factory=list)


def _domain_of(address: str) -> str:
    match = re.search(r"@([\w.-]+)", (address or "").lower())
    return match.group(1) if match else ""


def _detect_lang(text: str) -> str:
    """Kaba dil sezgisi — yanit taslagini dogru dilde acmak icin."""
    low = (text or "").lower()
    if re.search(r"[ыїієґа-я]", low):
        return "uk"
    if re.search(r"[şğıçö]|merhaba|iyi gunler|siparis", low):
        return "tr"
    if re.search(r"\b(hallo|guten tag|sehr geehrte|bestellung|versand|gruss)\b", low):
        return "de"
    if re.search(r"\b(hello|hi|regards|order|shipping)\b", low):
        return "en"
    return "de"   # ana pazar


# Taslak yanitlar: BILGI VERMEZ, SOZ VERMEZ — sadece "aldik, bakiyoruz" der.
# Somut cevabi insan yazar; boylece yanlis bilgi verilmesi imkansiz olur.
_ACK = {
    "de": ("Hallo,\n\nvielen Dank für deine Nachricht. Wir haben sie erhalten "
           "und melden uns zeitnah mit einer konkreten Antwort.\n\n"
           "Viele Grüße\nCSS Berlin\ncssberlin.de"),
    "en": ("Hello,\n\nthank you for your message. We have received it and will "
           "get back to you shortly with a concrete answer.\n\n"
           "Best regards\nCSS Berlin\ncssberlin.de"),
    "tr": ("Merhaba,\n\nmesajiniz icin tesekkurler. Aldik, en kisa surede "
           "somut bir yanitla donecegiz.\n\n"
           "Iyi gunler\nCSS Berlin\ncssberlin.de"),
    "uk": ("Вітаємо,\n\nдякуємо за ваше повідомлення. Ми його отримали і "
           "невдовзі повернемося з конкретною відповіддю.\n\n"
           "З повагою\nCSS Berlin\ncssberlin.de"),
}


def classify_mail(
    *,
    sender: str,
    subject: str,
    body: str = "",
    headers: Optional[dict] = None,
) -> MailVerdict:
    """
    Postayi siniflandirir ve gerekiyorsa TASLAK yanit onerir.
    Hicbir kosulda gonderme/islem yapma karari uretmez.
    """
    headers = headers or {}
    domain = _domain_of(sender)
    text = f"{subject}\n{body}"

    # Bulten/reklam: List-Unsubscribe basligi en guvenilir isaret
    if any(k.lower() == "list-unsubscribe" for k in headers):
        return MailVerdict(category="marketing", label=CATEGORY_LABELS["marketing"],
                           source=domain,
                           summary=f"Bulten/reklam: {subject[:70]}",
                           needs_human=True)

    for key, name in FINANCE_DOMAINS.items():
        if key in domain:
            return MailVerdict(category="finance", label=CATEGORY_LABELS["finance"],
                               source=name,
                               summary=f"{name}: {subject[:70]}",
                               needs_human=True)

    for key, name in PLATFORM_DOMAINS.items():
        if key in domain:
            return MailVerdict(category="platform_notification",
                               label=CATEGORY_LABELS["platform_notification"],
                               source=name,
                               summary=f"{name} bildirimi: {subject[:70]}",
                               needs_human=True)

    # Buraya kadar geldiyse gercek bir insan yazmis olabilir.
    intent = None
    for name, patterns in INTENT_PATTERNS.items():
        if any(re.search(p, text, re.IGNORECASE) for p in patterns):
            intent = name
            break

    lang = _detect_lang(text)
    draft = _ACK.get(lang, _ACK["de"])

    # Taslak da marka iddia bekcisinden gecer: otomatik metin bile
    # kanitsiz bir soz (ucretsiz kargo, "en iyi"...) icermemeli.
    violations = brand.check_claim(draft, lang=lang)
    warnings = [f"{v.category}: {v.matched}" for v in violations]
    if any(v.severity == "forbidden" for v in violations):
        draft = None
        warnings.append("taslak bekciden gecemedi — yaniti elle yazin")

    return MailVerdict(
        category="customer_message", label=CATEGORY_LABELS["customer_message"],
        source=domain, intent=intent, draft_reply=draft, draft_lang=lang,
        summary=(f"Musteri ({intent or 'genel'}): {subject[:70]}"),
        needs_human=True, warnings=warnings,
    )
