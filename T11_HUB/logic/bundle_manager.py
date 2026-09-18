"""
Bundle / coklu-alim yonetimi (saf, additive).

Musteri 2+ urun sepete eklediginde paket fiyati + kargo tasarrufu hesaplar.
Dis hesap/DB gerektirmez. Kargo tasarrufu shipping_optimizer ile tutarli.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from .shipping_optimizer import bundle_shipping_saving, is_free_shipping

# Adet bazli bundle indirimi
DISCOUNT_TIERS: list[tuple[int, float]] = [
    (2, 0.10),   # 2 urun -> %10
    (3, 0.15),   # 3+ urun -> %15
]
PICKUP_DISCOUNT_EUR: float = 2.00  # Berlin ici elden teslim indirimi


class BundleItem(BaseModel):
    product_id: str
    price: float
    buy_cost: float = 0.0   # bizim maliyetimiz (kar hesabi icin)
    size: str = "medium"


class BundleQuote(BaseModel):
    n_items: int
    items_total: float
    discount_rate: float
    discount_eur: float
    bundle_price: float
    shipping_cost: float
    free_shipping: bool
    pickup_discount: float
    payable_total: float
    our_cost: float
    net_profit: float


def _discount_rate(n_items: int) -> float:
    rate = 0.0
    for threshold, r in DISCOUNT_TIERS:
        if n_items >= threshold:
            rate = r
    return rate


def quote_bundle(
    items: list[BundleItem],
    *,
    pickup: bool = False,
    customer_chose_bulk_day: bool = False,
    size: str = "medium",
) -> BundleQuote:
    """
    Sepet icin bundle teklifi uretir: indirim, kargo, elden-teslim indirimi,
    odenecek toplam ve bizim net karimiz.
    """
    n = len(items)
    items_total = round(sum(i.price for i in items), 2)
    rate = _discount_rate(n)
    discount = round(items_total * rate, 2)
    bundle_price = round(items_total - discount, 2)

    ship = bundle_shipping_saving(n, size=size)
    shipping_cost = 0.0 if pickup else ship["actual_total"]
    free = is_free_shipping(bundle_price, on_bulk_day=customer_chose_bulk_day)
    if free and not pickup:
        shipping_cost = 0.0

    pickup_disc = PICKUP_DISCOUNT_EUR if pickup else 0.0
    payable = round(bundle_price + shipping_cost - pickup_disc, 2)

    our_cost = round(sum(i.buy_cost for i in items) + ship["actual_total"], 2)
    net_profit = round(payable - our_cost, 2)

    return BundleQuote(
        n_items=n,
        items_total=items_total,
        discount_rate=rate,
        discount_eur=discount,
        bundle_price=bundle_price,
        shipping_cost=shipping_cost,
        free_shipping=free or pickup,
        pickup_discount=pickup_disc,
        payable_total=payable,
        our_cost=our_cost,
        net_profit=net_profit,
    )
