"""
Capraz-platform arbitraj motoru (additive).

ONEMLI: Tek-urun kar analizi ZATEN app.py'deki analyze_profit()'te var ve
sonuclari products tablosuna yaziliyor (estimated_sell_price, profit_euro,
profit_margin, recommendation, best_sell_platform). Bu modul onu COGALTMAZ.

Bu modulun yaptigi YENI is: AYNI urunun farkli KAYNAK platformlardaki
ilanlarini kumeleyip "ucuzdan al" firsatlarini yuzeye cikarmak. Maliyet
yeniden hesaplanmaz; products satirindaki hazir alanlar okunur.

Salt-okunur (read-only): products tablosunu sadece SELECT eder, yazmaz.
"""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Optional

import aiosqlite
from pydantic import BaseModel

from .product_matcher import match_key as _match_key

_BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_FILE = str(_BASE_DIR / "data" / "hub.db")


class SourceListing(BaseModel):
    product_id: str
    platform: str
    price: float
    url: Optional[str] = None
    est_sell_price: float = 0.0
    est_profit: float = 0.0
    best_sell_platform: Optional[str] = None
    title: Optional[str] = None


class ArbitrageOpportunity(BaseModel):
    match_key: str
    brand: Optional[str] = None
    size: Optional[str] = None
    sample_title: Optional[str] = None
    source_count: int
    cheapest: SourceListing
    all_sources: list[SourceListing]
    median_price: float            # kumenin medyan fiyati (gercekci piyasa)
    robust_spread_eur: float       # medyan - en ucuz (gercekci arbitraj payi)
    max_spread_eur: float          # en pahali - en ucuz (bilgi amacli, outlier'a acik)
    best_target_platform: Optional[str] = None  # ucuz kaynagin onerilen satis platformu
    est_profit_eur: float          # ucuz kaynagin hazir hesaplanmis kari


async def find_cross_platform_opportunities(
    *,
    db_file: str = DEFAULT_DB_FILE,
    min_spread_eur: float = 5.0,
    only_active_source: bool = True,
    limit: int = 100,
) -> list[ArbitrageOpportunity]:
    """
    products tablosundaki aktif ilanlari ayni-urun bazinda kumeler; birden fazla
    KAYNAK platformda gorunen ve fiyat farki (spread) >= min_spread_eur olanlari
    firsat olarak dondurur. En yuksek spread'e gore sirali.
    """
    where = []
    if only_active_source:
        where.append("(source_status IS NULL OR source_status = 'active')")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    async with aiosqlite.connect(db_file) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            f"""SELECT id, source_platform, price, source_url, title, brand, size,
                       category, estimated_sell_price, profit_euro, best_sell_platform
                FROM products {where_sql}"""
        )
        rows = await cur.fetchall()

    # kumele
    clusters: dict[str, list[SourceListing]] = {}
    meta: dict[str, dict] = {}
    for r in rows:
        price = r["price"] or 0
        if price <= 0:
            continue
        # Kategori kapisi + marka/model esasli eslesme anahtari
        key = _match_key(brand=r["brand"], title=r["title"],
                         size=r["size"], category=r["category"])
        if not key:
            continue
        listing = SourceListing(
            product_id=r["id"],
            platform=r["source_platform"],
            price=float(price),
            url=r["source_url"],
            est_sell_price=float(r["estimated_sell_price"] or 0),
            est_profit=float(r["profit_euro"] or 0),
            best_sell_platform=r["best_sell_platform"],
            title=r["title"],
        )
        clusters.setdefault(key, []).append(listing)
        meta.setdefault(key, {"brand": r["brand"], "size": r["size"], "title": r["title"]})

    opportunities: list[ArbitrageOpportunity] = []
    for key, listings in clusters.items():
        platforms = {l.platform for l in listings}
        if len(platforms) < 2:
            continue  # capraz-platform degil
        listings_sorted = sorted(listings, key=lambda l: l.price)
        cheapest = listings_sorted[0]
        prices = [l.price for l in listings_sorted]
        median_price = round(statistics.median(prices), 2)
        # Robust spread: en pahali outlier'a degil, gercekci PIYASA MEDYANINA gore
        # (ucuzdan al -> medyandan sat kazanci). Sahte 500+ spread'leri engeller.
        robust_spread = round(median_price - cheapest.price, 2)
        max_spread = round(prices[-1] - prices[0], 2)
        if robust_spread < min_spread_eur:
            continue
        opportunities.append(ArbitrageOpportunity(
            match_key=key,
            brand=meta[key]["brand"],
            size=meta[key]["size"],
            sample_title=meta[key]["title"],
            source_count=len(listings),
            cheapest=cheapest,
            all_sources=listings_sorted,
            median_price=median_price,
            robust_spread_eur=robust_spread,
            max_spread_eur=max_spread,
            best_target_platform=cheapest.best_sell_platform,
            est_profit_eur=cheapest.est_profit,
        ))

    opportunities.sort(key=lambda o: o.robust_spread_eur, reverse=True)
    return opportunities[:limit]
