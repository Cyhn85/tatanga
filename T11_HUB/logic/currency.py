"""
Para birimi cevirisi — TEK kaynak, GERCEK kur.

BUGUNKU SORUN: app.py icinde kur sabitleri dagınık ve elle yazilmis
(GBP 1.17 uc ayri yerde, PLN 0.23). Kur degisince biri guncellenip digeri
unutulursa karlilik hesabi sessizce yanlis olur — arbitrajda bu dogrudan
para kaybi demektir.

COZUM: Avrupa Merkez Bankasi'nin (ECB) gunluk referans kuru. Ucretsiz,
anahtarsiz, kayit istemez, kamuya acik XML. Gunde bir cekilir ve diske
yazilir; ag yoksa once disk onbellegi, o da yoksa statik yedek kullanilir —
ama hangisinin kullanildigi HER ZAMAN raporlanir, sessizce tahmin yapilmaz.

Saf modul: HTTP istemcisi disaridan verilebilir -> izole test edilir.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Optional

ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"

# ECB ulasilamazsa kullanilacak son care. Bu degerler TAHMINDIR — kullanildiginda
# sonuc "static" kaynagiyla isaretlenir ki karlilik raporunda gorulebilsin.
STATIC_FALLBACK: dict[str, float] = {
    "EUR": 1.0, "GBP": 0.85, "SEK": 11.30, "PLN": 4.30,
    "DKK": 7.46, "NOK": 11.60, "CHF": 0.94, "CZK": 25.20,
}

# Platform -> o platformun ilan fiyatlarini yayinladigi para birimi.
PLATFORM_CURRENCY: dict[str, str] = {
    "vinted": "EUR", "vinted_fr": "EUR", "vinted_be": "EUR",
    "vinted_pl": "PLN", "vinted_uk": "GBP",
    "kleinanzeigen": "EUR", "ebay": "EUR", "markt": "EUR",
    "willhaben": "EUR", "leboncoin": "EUR", "percentil": "EUR",
    "tradera": "SEK", "sellpy": "SEK", "depop": "GBP",
}


@dataclass
class Rates:
    """1 EUR = rates[XXX] birim XXX. source: 'ecb' | 'cache' | 'static'."""
    rates: dict[str, float]
    source: str
    fetched_on: str = ""

    @property
    def reliable(self) -> bool:
        return self.source in ("ecb", "cache")


def parse_ecb_xml(xml_text: str) -> dict[str, float]:
    """ECB XML'inden currency/rate ciftlerini cikarir (bagimlilik eklemeden)."""
    out: dict[str, float] = {"EUR": 1.0}
    for m in re.finditer(r"currency=['\"]([A-Z]{3})['\"]\s+rate=['\"]([0-9.]+)['\"]", xml_text):
        try:
            out[m.group(1)] = float(m.group(2))
        except ValueError:
            continue
    return out


def load_rates(
    cache_path: Path | str,
    *,
    fetcher: Optional[Callable[[str], str]] = None,
    today: Optional[str] = None,
) -> Rates:
    """
    Gunluk kuru getirir. Sirayla: gunluk disk onbellegi -> ECB -> eski onbellek
    -> statik yedek. Hangisi kullanildiysa `source` alaninda bildirilir.
    """
    cache_path = Path(cache_path)
    bugun = today or date.today().isoformat()

    onbellek: dict = {}
    if cache_path.is_file():
        try:
            onbellek = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            onbellek = {}
    if onbellek.get("fetched_on") == bugun and onbellek.get("rates"):
        return Rates(onbellek["rates"], "cache", bugun)

    if fetcher is not None:
        try:
            kurlar = parse_ecb_xml(fetcher(ECB_URL))
            if len(kurlar) > 5:          # anlamli bir yanit mi
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(
                    json.dumps({"fetched_on": bugun, "rates": kurlar}, indent=1),
                    encoding="utf-8")
                return Rates(kurlar, "ecb", bugun)
        except Exception:
            pass   # asagidaki yedeklere dusulur

    if onbellek.get("rates"):
        # Gunu gecmis ama gercek kur — statik tahminden iyidir.
        return Rates(onbellek["rates"], "cache", onbellek.get("fetched_on", ""))
    return Rates(dict(STATIC_FALLBACK), "static", "")


def to_eur(amount: float, currency: str, rates: Rates) -> Optional[float]:
    """
    Yerel tutari EUR'ya cevirir. Kur bilinmiyorsa None doner — 1:1 VARSAYMAZ.
    Bilinmeyen kuru 1'e esitlemek, SEK fiyatini EUR sanip 10 kat fazla
    kar hesaplamak demektir; sessiz yanlis yerine acik bilinmezlik.
    """
    cur = (currency or "EUR").upper()
    if cur == "EUR":
        return round(float(amount), 2)
    kur = rates.rates.get(cur)
    if not kur:
        return None
    return round(float(amount) / kur, 2)


def platform_currency(platform: str) -> str:
    return PLATFORM_CURRENCY.get((platform or "").lower(), "EUR")


def describe(rates: Rates) -> str:
    """Karlilik raporunda gosterilecek insan-okunur kur kaynagi."""
    if rates.source == "ecb":
        return f"ECB gunluk kuru ({rates.fetched_on})"
    if rates.source == "cache":
        return f"onbellekten ECB kuru ({rates.fetched_on or 'tarih yok'})"
    return "STATIK TAHMIN — ECB'ye ulasilamadi, kar hesabi sapabilir"
