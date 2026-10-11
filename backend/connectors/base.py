import hashlib
from dataclasses import asdict, replace
from abc import ABC, abstractmethod
from typing import Optional

from ..config import ROAD_FACTOR
from ..delivery import DeliveryRule, compute_delivery, travel_cost
from ..geo import haversine_km
from ..models import Location, Quote, SearchOptions
from ..ranking import finalize


def stable_unit(*parts) -> float:
    """Deterministic pseudo-random float in [0,1) from arbitrary parts."""
    h = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2 ** 64


class Connector(ABC):
    id: str = ""
    name: str = ""
    kind: str = "online"

    @property
    def requires_coordinates(self) -> bool:
        return True

    @abstractmethod
    async def fetch(self, drug: dict, qty: int, loc: Location, opts: SearchOptions) -> list:
        ...


def store_quotes(store: dict, drug: dict, item_price: float, loc: Location, opts: SearchOptions, *,
                 source: str, confidence: float, observed_at: float, price_known: bool = True,
                 in_stock: Optional[bool] = None, notes: Optional[list] = None) -> list:
    """Build a pickup quote (and a delivery quote if the store delivers) for one physical store."""
    road_km = round(haversine_km(loc.lat, loc.lng, store["lat"], store["lng"]) * ROAD_FACTOR, 2)
    base = dict(
        provider=store["name"], kind="store", source=source, confidence=confidence, price_known=price_known,
        item_price=round(item_price, 2), in_stock=in_stock, distance_km=road_km, lat=store["lat"], lng=store["lng"],
        address=store.get("address"), phone=store.get("phone"), hours=store.get("hours"),
        observed_at=observed_at, url=store.get("url"),
    )
    sid = store.get("id", store["name"])
    out = [finalize(Quote(
        id=f"{sid}:pickup", fulfilment="pickup",
        travel_cost=travel_cost(road_km, opts.travel_cost_per_km), notes=list(notes or []), **base))]

    if store.get("delivers"):
        rule = DeliveryRule.from_dict(store.get("delivery"))
        res = compute_delivery(replace(rule, min_order=0) if opts.basket_mode else rule, item_price, road_km)
        if res.eligible:
            out.append(finalize(Quote(
                id=f"{sid}:delivery", fulfilment="delivery", delivery_fee=res.fee, platform_fee=res.platform_fee,
                eta_minutes=res.eta_minutes, delivery_rule=asdict(rule), notes=list(notes or []) + res.notes, **base)))
    return out
