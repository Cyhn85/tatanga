"""
Platform basina gonderi bicimlendirici (saf, ucretsiz, deterministik).

AMAC: Ayni kampanya her platformda ayni sekilde iyi durmaz. Instagram baslik
istemez, YouTube ister. TikTok etiketi metnin icine gomer, Pinterest etikete
neredeyse hic bakmaz. Bu modul tek bir kampanya taslagini her platformun kendi
adetine gore yeniden yazar.

NEDEN "ATTENDED" (yari otomatik): Instagram ve TikTok'ta otomatik yayin icin
2-4 haftalik uygulama incelemesi bekleniyor. O sure boyunca islerin durmamasi
icin sistem HER SEYI hazirlar — video, baslik, aciklama, etiketler — ve
Telegram'a duser; insan tek dokunusla yayinlar. Ne kural ihlali, ne ban riski.

SINIRLAR BILINCLI OLARAK MUHAFAZAKAR: platformlarin ust sinirlarina dayanmak
yerine guvenli araliklarda kaliyoruz. Kirpilan bir aciklama, reddedilen bir
gonderiden iyidir.

Uretilen HER metin marka iddia bekcisinden gecer; kanitsiz iddia disari cikmaz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from . import brand_identity as brand

# Guvenli sinirlar (platform tavanlarinin altinda tutuldu)
PLATFORM_LIMITS = {
    "instagram": {"title": 0, "caption": 2000, "hashtags": 20, "aspect": "9:16", "seconds": (5, 90)},
    "tiktok":    {"title": 0, "caption": 1800, "hashtags": 8,  "aspect": "9:16", "seconds": (5, 180)},
    "youtube":   {"title": 90, "caption": 4500, "hashtags": 10, "aspect": "9:16", "seconds": (5, 180)},
    "pinterest": {"title": 95, "caption": 480,  "hashtags": 5,  "aspect": "2:3",  "seconds": (5, 60)},
}

# Etiketler: marka + kategori + dil. Uydurma trend etiketi KULLANILMAZ —
# alakasiz etiket kisa vadede erisim getirse de hesabi spam'e dogru iter.
BASE_HASHTAGS = {
    "de": ["secondhand", "berlin", "nachhaltigemode", "vintage", "gebraucht",
           "kreislaufwirtschaft", "slowfashion"],
    "en": ["secondhand", "berlin", "sustainablefashion", "vintage", "preloved",
           "circularfashion", "slowfashion"],
    "tr": ["ikincielmoda", "berlin", "surdurulebilirmoda", "vintage", "ikinciel"],
    "uk": ["секондхенд", "берлін", "екомода", "вінтаж"],
}

PLATFORM_UPLOAD_URLS = {
    "instagram": "https://www.instagram.com/",
    "tiktok": "https://www.tiktok.com/upload",
    "youtube": "https://studio.youtube.com/channel/UC/videos/upload",
    "pinterest": "https://www.pinterest.com/pin-builder/",
}


@dataclass
class PostPackage:
    platform: str
    lang: str
    title: str = ""
    caption: str = ""
    hashtags: list[str] = field(default_factory=list)
    upload_url: str = ""
    video_requirements: str = ""
    warnings: list[str] = field(default_factory=list)
    blocked: Optional[str] = None      # bekci reddettiyse gerekce

    @property
    def full_caption(self) -> str:
        etiketler = " ".join(f"#{h}" for h in self.hashtags)
        return f"{self.caption}\n\n{etiketler}".strip() if etiketler else self.caption


def _clip(text: str, limit: int) -> str:
    """Kelime ortasindan kesmez; sinira sigmiyorsa son tam cumleden keser."""
    if limit <= 0 or len(text) <= limit:
        return text
    kirpik = text[:limit]
    for ayrac in (". ", "! ", "? ", "\n", " "):
        yer = kirpik.rfind(ayrac)
        if yer > limit * 0.6:
            return kirpik[:yer + 1].strip()
    return kirpik.strip()


def build_hashtags(lang: str, platform: str, category: str = "") -> list[str]:
    limit = PLATFORM_LIMITS.get(platform, {}).get("hashtags", 10)
    etiketler = list(BASE_HASHTAGS.get(lang, BASE_HASHTAGS["de"]))
    if category:
        temiz = re.sub(r"[^0-9a-zA-ZäöüßÄÖÜğışçöüĞİŞÇÖÜа-яА-Я]+", "", category).lower()
        if temiz and temiz not in etiketler:
            etiketler.insert(1, temiz)
    return etiketler[:limit]


def format_for_platform(
    *,
    platform: str,
    lang: str,
    headline: str,
    body: str,
    cta: str,
    site_url: str = "https://cssberlin.de",
    category: str = "",
) -> PostPackage:
    """
    Kampanya metnini bir platformun adetine gore paketler.
    Bekci reddederse `blocked` doldurulur ve paket YAYINLANMAMALIDIR.
    """
    limits = PLATFORM_LIMITS.get(platform)
    package = PostPackage(platform=platform, lang=lang,
                          upload_url=PLATFORM_UPLOAD_URLS.get(platform, ""))
    if not limits:
        package.blocked = f"bilinmeyen platform: {platform}"
        return package

    alt, ust = limits["seconds"]
    package.video_requirements = (f"{limits['aspect']} dikey, {alt}-{ust} saniye")

    # YouTube tek platformda baslik alani ister; digerlerinde baslik metnin basidir.
    if limits["title"]:
        package.title = _clip(headline, limits["title"])
        govde = f"{body}\n\n{cta}\n{site_url}"
    else:
        govde = f"{headline}\n\n{body}\n\n{cta}\n{site_url}"

    package.caption = _clip(govde, limits["caption"])
    package.hashtags = build_hashtags(lang, platform, category)

    # Bekci: baslik + aciklama + etiketler birlikte denetlenir.
    denetlenecek = f"{package.title} {package.full_caption}"
    ihlaller = brand.check_claim(denetlenecek, lang=lang)
    yasak = [v for v in ihlaller if v.severity == "forbidden"]
    if yasak:
        package.blocked = "; ".join(f"{v.category}('{v.matched}')" for v in yasak)
    package.warnings = [f"{v.category}: {v.matched}" for v in ihlaller if v.severity == "warn"]
    return package


def format_all_platforms(**kwargs) -> dict[str, PostPackage]:
    """Ayni kampanyayi dort platform icin birden paketler."""
    return {p: format_for_platform(platform=p, **kwargs) for p in PLATFORM_LIMITS}
