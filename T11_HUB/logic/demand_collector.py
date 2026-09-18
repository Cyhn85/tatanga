"""
Talep olcumu toplayici — demand_intel'in ihtiyaci olan HAM sayilari getirir.

TASARIM KARARI: Tek tek ilan kazimayiz. Sell-through orani icin yalnizca IKI
sayi gerekir: kac aktif ilan var, kac tanesi satildi. Her ikisi de arama
sonucu sayfasinin BASLIGINDA yazili ("2.500+ Ergebnisse"). Yani aday basina
2 hafif istek yeterli — 60 aday icin 120 istek, tam kazimada bu 60.000 istek
olurdu. Talep taramasi ucuz olmali ki sik yapilabilsin.

Kaynaklar ve neden bunlar:
  eBay  : LH_Sold=1&LH_Complete=1 ile SATILMIS arsivi aciktir. Ucretsiz,
          anahtarsiz, gercek satis kaniti. Ikinci el talebi icin altin standart.
  Vinted: satilan ilan API'den kaybolur; ama bizim deep-liveness kontrolumuz
          source_status='sold' yaziyor — yani KENDI verimizden satis hizi
          cikarilabilir. Disaridan alinamayan, bize ozgu bir avantaj.
  Aktif : her platform toplam sonuc sayisini veriyor (rekabet olcusu).

Saf modul degil (ag kullanir) ama fetch fonksiyonu disaridan verilebilir ->
testte sahte veriyle kosulur.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import quote

from .demand_intel import MarketSample

# "2.500 + Ergebnisse", "1,234 results", "45 Ergebnisse"
_COUNT_RE = re.compile(
    r"([\d][\d.,\s]*)\s*\+?\s*(?:Ergebnisse|results|Resultate|resultaten|risultati)",
    re.IGNORECASE)


def parse_result_count(html: str) -> Optional[int]:
    """
    Arama sonucu sayisini sayfa metninden cikarir.
    Bulunamazsa None doner — 0 DEGIL. "sonuc yok" ile "okuyamadim" ayrimi
    kritik: 0 dersek talep skoru yanlis hesaplanir.
    """
    if not html:
        return None
    # Once basligi ara (en guvenilir), sonra tum govdeyi
    for parca in (html[:200000],):
        m = _COUNT_RE.search(parca)
        if m:
            ham = m.group(1)
            temiz = re.sub(r"[^\d]", "", ham.replace(",", "").replace(".", ""))
            if temiz.isdigit():
                return int(temiz)
    return None


@dataclass
class CollectResult:
    sample: Optional[MarketSample]
    ok: bool
    note: str = ""


def collect_ebay(query: str, fetch_html: Callable[[str], Optional[str]],
                 *, tld: str = "de", window_days: int = 30) -> CollectResult:
    """
    eBay'den aktif + satilmis sayilarini getirir.

    fetch_html disaridan verilir: uretimde gercek tarayici (eBay duz istegi
    403'ler), testte sahte fonksiyon.
    """
    q = quote(query)
    aktif_url = f"https://www.ebay.{tld}/sch/i.html?_nkw={q}&_ipg=60"
    satilmis_url = f"{aktif_url}&LH_Sold=1&LH_Complete=1"

    aktif_html = fetch_html(aktif_url)
    aktif = parse_result_count(aktif_html or "")
    if aktif is None:
        return CollectResult(None, False,
                             "aktif ilan sayisi okunamadi (engel veya sayfa degisikligi)")

    satilmis_html = fetch_html(satilmis_url)
    satilmis = parse_result_count(satilmis_html or "")
    if satilmis is None:
        return CollectResult(None, False,
                             f"aktif={aktif} okundu ama SATILMIS sayisi okunamadi — "
                             "sell-through hesaplanamaz")

    return CollectResult(
        MarketSample(query=query, platform=f"ebay_{tld}",
                     active_count=aktif, sold_count=satilmis,
                     window_days=window_days),
        True, f"aktif={aktif} satilmis={satilmis}")


def collect_from_own_history(query: str, rows: list[dict],
                             *, window_days: int = 30) -> CollectResult:
    """
    KENDI veritabanimizdan talep olcumu.

    rows: products tablosundan (source_status, price, currency) satirlari.
    Deep-liveness kontrolu ilan kaynakta kaybolunca source_status='sold'
    yaziyor — yani her kazidigimiz urun zamanla bir talep gozlemine donusuyor.
    Bu, disaridan satin alinamayan kendi verimizdir ve zamanla guclenir.
    """
    if not rows:
        return CollectResult(None, False, "bu sorgu icin gecmis veri yok")

    satilan = [r for r in rows if (r.get("source_status") or "") == "sold"]
    aktif = [r for r in rows
             if (r.get("source_status") or "active") not in ("sold", "removed")]

    return CollectResult(
        MarketSample(
            query=query, platform="tatanga_gecmis",
            active_count=len(aktif), sold_count=len(satilan),
            window_days=window_days,
            sold_prices=[float(r["price"]) for r in satilan
                         if r.get("price") and float(r["price"]) > 0],
            active_prices=[float(r["price"]) for r in aktif
                           if r.get("price") and float(r["price"]) > 0],
        ),
        True, f"kendi gecmisimiz: {len(aktif)} aktif, {len(satilan)} satildi")


def merge_samples(samples: list[MarketSample]) -> Optional[MarketSample]:
    """
    Ayni sorgu icin farkli kaynaklardan gelen olcumleri birlestirir.
    Sayilar toplanir, fiyatlar havuzlanir — daha genis gozlem, daha guvenilir
    oran. Farkli kaynaklarin agirligini esitlemek bilincli bir sadelik:
    hangi kaynagin daha dogru oldugunu HENUZ bilmiyoruz; bilince
    (outcome_learning verisi birikince) agirlik verilebilir.
    """
    if not samples:
        return None
    ilk = samples[0]
    birlesik = MarketSample(query=ilk.query, platform="+".join(
        sorted({s.platform for s in samples if s.platform})))
    for s in samples:
        birlesik.active_count += s.active_count
        birlesik.sold_count += s.sold_count
        birlesik.sold_prices.extend(s.sold_prices)
        birlesik.active_prices.extend(s.active_prices)
    birlesik.window_days = max((s.window_days for s in samples), default=30)
    return birlesik
