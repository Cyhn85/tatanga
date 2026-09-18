"""
Tam boy gorsel kaynaklama (saf, additive, ucretsiz).

SORUN: Kazima, ilan listesi sayfasindaki <img src> degerini kaydediyor. Bu
degerler cogu platformda KUCUK-RESIM (thumbnail): gercek olculen ornekler
140x105 ve 105x140 piksel. Video 1080 kisa kenar istiyor; 140 pikseli 1080'e
cikarmak 8x buyutme demek ve bulanik cikiyor. Urun kartinda da kalitesiz duruyor.

COZUM: Platformlarin gorsel CDN'lerinde boyut, URL icinde kodlu. Ayni gorselin
buyuk surumu genelde tek bir parca degistirilerek elde ediliyor. Ama bu desenler
zamanla degisir — bu yuzden burada TAHMINE GUVENILMEZ:
  1. Bilinen desenlerden aday URL'ler uretilir (buyukten kucuge),
  2. Adaylar sirayla indirilip GERCEKTEN OLCULUR,
  3. Esigi gecen ilk gorsel kullanilir; hicbiri gecmezse en buyuk bulunan alinir
     ve durum acikca raporlanir.
Yanlis bir desen tahmini bu yuzden zarar vermez: sadece o aday elenir.

Saf modul: ag cagrisi disaridan `fetch` ile enjekte edilir -> izole test edilir.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Callable, Optional

# Video kisa kenari 1080. Bunun altindaki gorseller kabul edilebilir ama
# 600'un altina inersek buyutme artefakti gozle gorulur hale geliyor.
MIN_IMAGE_SIDE = 600


@dataclass
class SourcedImage:
    data: bytes
    url: str
    width: int
    height: int
    upgraded: bool          # kucuk-resim yerine buyuk surum mu bulundu
    meets_minimum: bool     # MIN_IMAGE_SIDE esigini geciyor mu

    @property
    def short_side(self) -> int:
        return min(self.width, self.height)


def image_url_candidates(url: str, platform: str = "") -> list[str]:
    """
    Ayni gorselin daha buyuk surumleri icin aday URL'ler (buyukten kucuge,
    orijinal daima listede kalir). Desen tutmazsa aday sessizce elenir.
    """
    if not url:
        return []
    candidates: list[str] = []

    # eBay CDN: .../s-l64.jpg | s-l225.jpg | s-l500.jpg -> s-l1600.jpg
    # (Kleinanzeigen de ayni altyapiyi kullaniyor.)
    if re.search(r"/s-l\d+\.(jpe?g|png|webp)", url, re.I):
        for size in (1600, 960, 500):
            candidates.append(re.sub(r"/s-l\d+\.", f"/s-l{size}.", url, flags=re.I))

    # eBay/Kleinanzeigen resim API'si: ?rule=$_59.JPG -> daha buyuk kurallar
    if "rule=$_" in url:
        for rule in ("$_57.JPG", "$_27.JPG"):
            candidates.append(re.sub(r"rule=\$_\d+\.[A-Za-z]+", f"rule={rule}", url))

    # Vinted CDN: .../thumb/... veya f800/f320 gibi boyut segmentleri
    if re.search(r"/f\d{3}/", url):
        candidates.append(re.sub(r"/f\d{3}/", "/f800/", url))
    if "/thumb/" in url:
        candidates.append(url.replace("/thumb/", "/f800/"))

    # Genel: URL sonundaki boyut sorgusu (?w=200&h=200 gibi) atilirsa cogu
    # CDN orijinali dondurur.
    if re.search(r"[?&](w|width|h|height|size)=\d+", url, re.I):
        candidates.append(re.split(r"[?&](?:w|width|h|height|size)=", url)[0].rstrip("?&"))

    candidates.append(url)  # orijinal daima son care

    seen: set[str] = set()
    ordered: list[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


def _measure(data: bytes) -> Optional[tuple[int, int]]:
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as img:
            return img.size
    except Exception:
        return None


def source_best_image(
    url: str,
    *,
    platform: str = "",
    fetch: Callable[[str], Optional[bytes]],
    min_side: int = MIN_IMAGE_SIDE,
) -> Optional[SourcedImage]:
    """
    Aday URL'leri sirayla indirir, GERCEK boyutu olcer ve esigi gecen ilkini
    dondurur. Hicbiri gecmezse en buyugunu dondurur (meets_minimum=False).
    Hicbir aday indirilemezse None.

    fetch(url) -> bytes | None  (ag cagrisi disaridan verilir)
    """
    best: Optional[SourcedImage] = None
    candidates = image_url_candidates(url, platform)

    for index, candidate in enumerate(candidates):
        data = None
        try:
            data = fetch(candidate)
        except Exception:
            data = None
        if not data:
            continue
        size = _measure(data)
        if not size:
            continue

        width, height = size
        found = SourcedImage(
            data=data, url=candidate, width=width, height=height,
            upgraded=(candidate != url),
            meets_minimum=(min(width, height) >= min_side),
        )
        if best is None or found.short_side > best.short_side:
            best = found
        if found.meets_minimum:
            return found   # yeterince buyuk -> daha fazla istek atma

        del index
    return best
