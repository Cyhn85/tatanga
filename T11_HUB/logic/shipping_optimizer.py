"""
Kargo optimizasyonu (saf, additive).

Berlin ici toplu kargo gunleri, bolge rotalari, bedava kargo politikasi,
manifesto ve bundle kargo tasarrufu. Dis hesap/DB gerektirmez; hepsi saf
hesap. Karar/onay kullaniciya aittir — bu modul yalnizca hesaplar ve oneri
uretir.
"""

from __future__ import annotations

from datetime import date, timedelta
from enum import IntEnum
from typing import Optional

from pydantic import BaseModel


class Weekday(IntEnum):
    MON = 0
    TUE = 1
    WED = 2
    THU = 3
    FRI = 4
    SAT = 5
    SUN = 6


# Toplu kargo gunleri: Pazartesi, Carsamba, Cuma
SHIPPING_DAYS: tuple[int, ...] = (Weekday.MON, Weekday.WED, Weekday.FRI)
SHIPPING_DAY_NAMES = {
    Weekday.MON: "Pazartesi", Weekday.WED: "Carsamba", Weekday.FRI: "Cuma",
}

FREE_SHIPPING_THRESHOLD_EUR: float = 50.0

# Almanya ici yurtici kargo maliyet matrisi (yaklasik, EUR) — boy: small/medium/large
CARRIER_COSTS: dict[str, dict[str, float]] = {
    "dhl":    {"small": 3.99, "medium": 4.99, "large": 6.99},
    "hermes": {"small": 3.70, "medium": 4.50, "large": 6.20},
    "gls":    {"small": 4.30, "medium": 5.20, "large": 6.80},
}

# Berlin bolge rotalari (elden teslim / toplu dagitim icin)
DISTRICT_ROUTES: dict[str, list[str]] = {
    "kreuzberg":       ["Kottbusser Tor", "Gorlitzer Park", "Wrangelstrasse"],
    "neukolln":        ["Hermannplatz", "Schillerkiez", "Reuterstrasse"],
    "prenzlauer_berg": ["Kollwitzplatz", "Mauerpark", "Danziger Strasse"],
    "friedrichshain":  ["Boxhagener Platz", "Simon-Dach-Strasse", "Warschauer Strasse"],
}
# Toplu dagitim gunlerinde bolge sirasi (dogu-bati mantikli, kaba)
ROUTE_ORDER = ["kreuzberg", "neukolln", "friedrichshain", "prenzlauer_berg"]


def cheapest_carrier(size: str = "medium") -> tuple[str, float]:
    """Verilen boy icin en ucuz tasiyiciyi dondurur."""
    options = {c: costs.get(size, costs["medium"]) for c, costs in CARRIER_COSTS.items()}
    carrier = min(options, key=options.get)
    return carrier, options[carrier]


def next_shipping_day(from_date: Optional[date] = None, *, before_hour_ok: bool = True) -> date:
    """from_date'ten (dahil) sonraki ilk toplu kargo gununu dondurur."""
    d = from_date or date.today()
    for offset in range(0, 8):
        cand = d + timedelta(days=offset)
        if cand.weekday() in SHIPPING_DAYS:
            return cand
    return d  # teorik olarak ulasilmaz


def is_free_shipping(order_value: float, *, on_bulk_day: bool = False) -> bool:
    """
    Bedava kargo hakki: siparis >= 50 EUR VEYA musteri toplu kargo gununu sectiyse.
    Toplu gun secimi bize maliyeti dusurdugu icin (tek seferde toplu gonderim)
    o gun ucretsiz sunulabilir.
    """
    return order_value >= FREE_SHIPPING_THRESHOLD_EUR or on_bulk_day


def bundle_shipping_saving(n_items: int, *, size: str = "medium") -> dict:
    """
    3+ urun ayni alicida ise tek kargo ucretiyle gider; birim maliyet duser.
    Dondurur: birim maliyet, tekil-toplam, gercek-toplam, tasarruf.
    """
    _, unit = cheapest_carrier(size)
    if n_items <= 0:
        return {"n_items": 0, "unit_cost": unit, "naive_total": 0.0,
                "actual_total": 0.0, "saving": 0.0}
    naive = round(unit * n_items, 2)
    # 1-2 urun: her biri ayri; 3+ : tek kargo (paketlenebilir varsayimi)
    actual = unit if n_items >= 3 else naive
    return {
        "n_items": n_items,
        "unit_cost": unit,
        "naive_total": naive,
        "actual_total": round(actual, 2),
        "saving": round(naive - actual, 2),
    }


class ShipmentPlan(BaseModel):
    order_id: str
    district: Optional[str] = None
    order_value: float
    shipping_day: str
    shipping_date: str
    free_shipping: bool
    carrier: str
    carrier_cost: float
    pickup_route: list[str] = []


def plan_shipment(
    order_id: str,
    order_value: float,
    *,
    district: Optional[str] = None,
    size: str = "medium",
    from_date: Optional[date] = None,
    customer_chose_bulk_day: bool = False,
) -> ShipmentPlan:
    """Tek bir siparis icin kargo plani uretir (saf hesap, yan etkisiz)."""
    day = next_shipping_day(from_date)
    free = is_free_shipping(order_value, on_bulk_day=customer_chose_bulk_day)
    carrier, cost = cheapest_carrier(size)
    route = DISTRICT_ROUTES.get((district or "").lower(), [])
    return ShipmentPlan(
        order_id=order_id,
        district=district,
        order_value=order_value,
        shipping_day=SHIPPING_DAY_NAMES.get(Weekday(day.weekday()), str(day.weekday())),
        shipping_date=day.isoformat(),
        free_shipping=free,
        carrier=carrier,
        carrier_cost=0.0 if free else cost,
        pickup_route=route,
    )


def build_manifest(plans: list[ShipmentPlan]) -> dict:
    """Ayni gunun siparislerini bolgeye gore gruplayip dagitim manifestosu uretir."""
    by_district: dict[str, list[ShipmentPlan]] = {}
    for p in plans:
        by_district.setdefault((p.district or "diger").lower(), []).append(p)

    ordered_route: list[dict] = []
    for district in ROUTE_ORDER + [d for d in by_district if d not in ROUTE_ORDER]:
        for p in by_district.get(district, []):
            for stop in (DISTRICT_ROUTES.get(district, []) or [None]):
                ordered_route.append({
                    "order_id": p.order_id,
                    "district": district,
                    "stop": stop,
                    "free_shipping": p.free_shipping,
                })

    total = len(plans)
    return {
        "total_packages": total,
        "free_count": sum(1 for p in plans if p.free_shipping),
        "paid_count": sum(1 for p in plans if not p.free_shipping),
        "route": ordered_route,
        "estimated_minutes": total * 15,
    }
