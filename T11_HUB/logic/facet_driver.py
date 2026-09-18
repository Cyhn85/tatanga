"""
Faceted "tam-sonuca-kadar-sur" driver (saf, additive, ucretsiz).

SORUN: Her platform bir arama icin sinirli sonuc doner (sayfa/sonuc tavani).
`max_pages=3` ile tek bir sorgu calistirmak, o aramanin sadece ilk diliminden
alir — geri kalani tavan altinda gomulu kalir. Bu yuzden "0 karli urun" cikmasi
gercekten stok olmadigi anlamina gelmez.

COZUM: Sorgu uzayini FACET'lere bolup her dilimi ayri calistirmak. Tavanin
altinda gomulu kalan ilanlar, daralmis bir facet sorgusunda yuzeye cikar.
Driver bunu, DURMA KOSULU saglanana kadar tekrarlar:
  - hedef sayida nitelikli urun (recommendation ∈ buy/watch) bulundu, VEYA
  - facet listesi tukendi, VEYA
  - doygunluk: ust uste N facet hic YENI urun getirmedi, VEYA
  - butce (facet sayisi / duvar saati) doldu, VEYA
  - platform hata verdi -> GERI CEKIL (asla agresif yeniden deneme).

Bu modul SAF'tir: DB/ag/olay otobusu bilmez. `scrape_fn` ve `qualifies_fn`
disaridan enjekte edilir (app.py bagliyor) — boylece gercek ag istegi atmadan
izole test edilebilir ve dairesel import olusmaz.

KAPSAM NOTU (durust sinir): Fiyat-ARALIGI faceti (min_price/max_price URL
parametresi) burada YOK, cunku hicbir platform kazima fonksiyonu boyle bir
parametre kabul etmiyor — eklemek 10 ayri fonksiyonu degistirmek demek. Onun
yerine fiyat ekseni, temel turda `multi_order` ile taranan `price_asc`/
`price_desc` siralamalari uzerinden kapsanir (dagilimin iki ucu). Gercek
aralik-bolmesi ayri bir adim.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from .keyword_localizer import PLATFORM_LANG, detected_type

# --- Butce / durma esikleri (muhafazakar: platformlari yormamak esas) ---
DEFAULT_MAX_FACETS = 8           # platform basina en fazla kac kazima turu
DEFAULT_TARGET_QUALIFIED = 5     # bu kadar buy/watch bulununca dur (basari kriteri)
DEFAULT_SATURATION_STREAK = 2    # ust uste bu kadar tur YENI urun getirmezse dur
DEFAULT_MAX_SECONDS = 600        # duvar saati tavani (10 dk)
DEFAULT_COOLDOWN = 5.0           # turlar arasi bekleme (kazima ici sleep'lere EK)

# Nitelikli sayilan tavsiyeler (basari kriteri: ham sayi degil).
QUALIFIED_RECOMMENDATIONS = ("buy", "watch")

# Renk facet'leri — hedef platformun dilinde. HEPSI BILINCLI OLARAK ASCII:
# keyword bazi platformlarda URL path'ine slug'lanir (_slugify umlaut'u
# translitere eder: grün -> gruen) ve o hali aramada karsilik bulmayabilir.
# Bu yuzden aksanli renkler (weiß/grün/blå/biały) listeye ALINMADI —
# ASCII yazilan, o dilde gercekten yaygin renkler secildi.
COLOR_FACETS: dict[str, list[str]] = {
    "de": ["schwarz", "blau", "rot", "grau", "braun", "beige"],
    "en": ["black", "blue", "red", "grey", "brown", "beige"],
    "fr": ["noir", "bleu", "rouge", "gris", "marron", "beige"],
    "nl": ["zwart", "blauw", "rood", "grijs", "bruin", "beige"],
    "es": ["negro", "azul", "rojo", "gris", "marron", "beige"],
    "sv": ["svart", "vit", "brun", "beige", "rosa"],
    "pl": ["czarny", "niebieski", "czerwony", "szary", "granatowy"],
}

# Numerik beden faceti SADECE ayakkabi tipinde anlamli (ilan basliklarinda
# "Gr. 43" cok yaygin). Harf bedenleri (S/M/L) tek karakterli oldugu icin
# alaka filtresinin token'lastirmasinda zaten eleniyor -> facet olarak eklenmedi.
SHOE_TYPES = {"shoes", "sneakers"}
SHOE_SIZE_FACETS = ["41", "42", "43", "44"]


@dataclass
class FacetPlan:
    """Tek bir kazima turu: hangi kelimeyle, hangi siralama stratejisiyle."""
    label: str        # "base" | "color:schwarz" | "size:43"
    keyword: str
    strategy: str     # "multi_order" | "single"


@dataclass
class FacetDriveResult:
    products: list[dict] = field(default_factory=list)
    qualified: int = 0
    facets_run: list[str] = field(default_factory=list)
    stop_reason: str = "not_started"
    error: Optional[str] = None

    @property
    def blocked(self) -> bool:
        """Platform bloku/hatasi yuzunden mi durduk (geri cekilme sinyali)."""
        return self.stop_reason in ("error_backoff", "no_results")


def _meaningful_tokens(keyword: str) -> list[str]:
    """Alaka filtresiyle AYNI token kurali (len > 1) — facet guvenligi buna dayanir."""
    return [t for t in (keyword or "").lower().split() if len(t) > 1]


def build_facet_plan(
    keyword: str,
    platform: str,
    *,
    max_facets: int = DEFAULT_MAX_FACETS,
) -> list[FacetPlan]:
    """
    Kazima turlerini ucuz/yuksek-verimli olandan baslayarak siralar:
      1) temel kelime + multi_order  (siralama ekseni: relevance/yeni/fiyat iki uc)
      2) renk facet'leri             (hedef dilde, sorgu uzayini genis bolen eksen)
      3) numerik beden facet'leri    (yalniz ayakkabi tipinde)

    KELIME FACET'I GUVENLIK KAPISI: scrape_platform icindeki alaka filtresi,
    baslikta arama kelimesinin token'larinin >= %70'ini arar. Temel kelime TEK
    anlamli token ise, ustune bir facet kelimesi eklemek orani 1/2'ye dusurur
    ve filtre (<=2 token -> hepsi zorunlu) gercek eslesmeleri de eler. Bu yuzden
    tek-token'li aramalarda kelime facet'i URETILMEZ; o durumda yalnizca
    siralama ekseni kullanilir. (2+ token'da matematik guvenli: temel token'lar
    tek basina esigi gecirir.)
    """
    plan = [FacetPlan(label="base", keyword=keyword, strategy="multi_order")]

    base_tokens = _meaningful_tokens(keyword)
    if len(base_tokens) < 2:
        return plan[:max_facets]

    lang = PLATFORM_LANG.get(platform.lower(), "de")
    for color in COLOR_FACETS.get(lang, COLOR_FACETS["de"]):
        if color in base_tokens:
            continue  # kullanici zaten rengi yazmis -> tekrar etme
        plan.append(FacetPlan(label=f"color:{color}",
                              keyword=f"{keyword} {color}", strategy="single"))

    if detected_type(keyword) in SHOE_TYPES:
        for size in SHOE_SIZE_FACETS:
            if size in base_tokens:
                continue
            plan.append(FacetPlan(label=f"size:{size}",
                                  keyword=f"{keyword} {size}", strategy="single"))

    return plan[:max_facets]


def _dedup_key(product: dict) -> str:
    """run_scrape_job DB'de source_url'e gore tekilliyor -> driver da oncelikle onu kullanir."""
    return (product.get("url") or "").strip() or f"sid:{product.get('source_id') or ''}"


async def drive_to_exhaustion(
    platform: str,
    keyword: str,
    *,
    scrape_fn: Callable[..., Awaitable[list[dict]]],
    qualifies_fn: Optional[Callable[[dict], bool]] = None,
    max_pages: int = 3,
    target_qualified: int = DEFAULT_TARGET_QUALIFIED,
    max_facets: int = DEFAULT_MAX_FACETS,
    saturation_streak: int = DEFAULT_SATURATION_STREAK,
    max_seconds: float = DEFAULT_MAX_SECONDS,
    cooldown: float = DEFAULT_COOLDOWN,
    sleep_fn: Optional[Callable[[float], Awaitable[None]]] = None,
    on_facet: Optional[Callable[[str, int, int], None]] = None,
) -> FacetDriveResult:
    """
    Facet planini durma kosulu saglanana kadar surer, TEKILLESTIRILMIS urun
    listesi dondurur.

    scrape_fn(platform, keyword, max_pages, strategy=...) -> list[dict]
    qualifies_fn(product) -> bool   (None ise nitelik sayaci calismaz, sadece
                                     doygunluk/butce durdurur)
    on_facet(label, new_unique, qualified_so_far)  — ilerleme bildirimi (opsiyonel)
    """
    if sleep_fn is None:
        import asyncio
        sleep_fn = asyncio.sleep

    result = FacetDriveResult(stop_reason="facets_exhausted")
    plan = build_facet_plan(keyword, platform, max_facets=max_facets)
    seen: set[str] = set()
    empty_streak = 0        # ust uste YENI urun getirmeyen tur sayisi
    barren_streak = 0       # ust uste HIC urun (ham) getirmeyen tur sayisi
    started = time.monotonic()

    for index, facet in enumerate(plan):
        if index > 0:
            if time.monotonic() - started > max_seconds:
                result.stop_reason = "time_budget"
                break
            if cooldown > 0:
                await sleep_fn(cooldown)

        try:
            batch = await scrape_fn(platform, facet.keyword, max_pages,
                                    strategy=facet.strategy)
        except Exception as exc:  # platform hatasi -> GERI CEKIL, yeniden deneme yok
            result.error = str(exc)[:300]
            result.stop_reason = "error_backoff"
            break

        result.facets_run.append(facet.label)
        batch = batch or []

        new_unique = 0
        for product in batch:
            key = _dedup_key(product)
            if not key or key in seen:
                continue
            seen.add(key)
            result.products.append(product)
            new_unique += 1
            if qualifies_fn is not None:
                try:
                    if qualifies_fn(product):
                        result.qualified += 1
                except Exception:
                    pass  # nitelik skoru hesaplanamadi -> urunu yine de tut

        if on_facet is not None:
            try:
                on_facet(facet.label, new_unique, result.qualified)
            except Exception:
                pass

        # Hic ham sonuc yok: ya facet gercekten bos ya da platform blokluyor.
        # Ust uste olursa daha fazla istek atmanin anlami yok -> geri cekil.
        barren_streak = barren_streak + 1 if not batch else 0
        if barren_streak >= saturation_streak:
            result.stop_reason = "no_results"
            break

        empty_streak = empty_streak + 1 if new_unique == 0 else 0
        if empty_streak >= saturation_streak:
            result.stop_reason = "saturated"
            break

        if qualifies_fn is not None and result.qualified >= target_qualified:
            result.stop_reason = "target_reached"
            break

    return result
