"""Synthetic connectors so the app works end-to-end with zero setup. NOT real prices."""
import asyncio
import math
import time
from dataclasses import asdict, replace

from ..delivery import DeliveryRule, compute_delivery
from ..models import Location, Quote, SearchOptions
from ..normalize import packs_needed
from ..ranking import finalize
from .base import Connector, stable_unit, store_quotes

BUCKET_S = 600  # prices drift every 10 min to mimic a live market


def _price(drug: dict, factor: float, key: str, qty: int) -> float:
    bucket = int(time.time() // BUCKET_S)
    jitter = (stable_unit(key, drug["id"], bucket) - 0.5) * 0.08   # +-4%
    pack = drug["reference_price"] * factor * (1 + jitter)
    return round(pack * packs_needed(qty, drug["pack_size"]), 2)


class DemoOnline(Connector):
    kind = "online"

    @property
    def requires_coordinates(self) -> bool:
        return bool(self.cfg.get("hyperlocal") or self.rule.per_km or self.rule.max_km is not None or self.rule.eta_per_km)

    def __init__(self, cfg: dict):
        self.cfg, self.id, self.name = cfg, cfg["id"], cfg["name"]
        self.rule = DeliveryRule.from_dict(cfg.get("delivery"))

    async def fetch(self, drug, qty, loc: Location, opts: SearchOptions):
        await asyncio.sleep(0.1 + stable_unit(self.id, "lat") * 0.7)   # simulate network
        item = _price(drug, self.cfg["price_factor"], self.id, qty)
        dist = None
        if self.cfg.get("hyperlocal"):
            dist = round(1.0 + stable_unit(self.id, round(loc.lat, 2), round(loc.lng, 2)) * 3.5, 2)
        res = compute_delivery(replace(self.rule, min_order=0) if opts.basket_mode else self.rule, item, dist)
        if not res.eligible:
            return []
        return [finalize(Quote(
            id=f"{self.id}:delivery", provider=self.name, kind="online", fulfilment="delivery",
            source="demo", confidence=0.3, item_price=item, delivery_fee=res.fee, platform_fee=res.platform_fee,
            eta_minutes=res.eta_minutes, distance_km=dist, in_stock=True, url=self.cfg.get("url"),
            delivery_rule=asdict(self.rule),
            notes=res.notes + ["Demo data - not a real price"]))]


class DemoStores(Connector):
    """Generates six plausible stores around the searcher, deterministic per ~1 km grid cell."""
    kind = "store"
    id = "demo-stores"
    name = "Nearby stores (demo)"

    def __init__(self, chains: list):
        self.chains = chains

    async def fetch(self, drug, qty, loc: Location, opts: SearchOptions):
        await asyncio.sleep(0.2)
        cell = (round(loc.lat, 2), round(loc.lng, 2))
        out = []
        for i, ch in enumerate(self.chains):
            ang = stable_unit("ang", i, *cell) * 2 * math.pi
            dist_km = 0.3 + stable_unit("dist", i, *cell) * min(opts.radius_km, 4.5)
            lat = loc.lat + (dist_km * math.cos(ang)) / 111.0
            lng = loc.lng + (dist_km * math.sin(ang)) / (111.0 * max(math.cos(math.radians(loc.lat)), 0.01))
            store = {"id": f"demo-{i}-{cell}", "name": ch["name"], "lat": lat, "lng": lng,
                     "address": "Demo address", "hours": "9:00-22:00", "delivers": ch.get("delivers", False),
                     "delivery": ch.get("delivery")}
            price = _price(drug, ch["price_factor"], ch["name"], qty)
            in_stock = stable_unit("stock", i, drug["id"], *cell) > 0.12
            out += store_quotes(store, drug, price, loc, opts, source="demo", confidence=0.3,
                                observed_at=time.time(), in_stock=in_stock,
                                notes=["Demo data - not a real price"])
        return [q for q in out if q.distance_km <= opts.radius_km * 1.3]
