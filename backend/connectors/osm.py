"""Real nearby pharmacies from OpenStreetMap (Overpass API). Gives location/hours, not prices."""
import time

import httpx

from ..config import STALE_AFTER_HOURS, USER_AGENT
from ..models import Location, SearchOptions
from .. import db
from .base import Connector, store_quotes
from ..normalize import packs_needed

OVERPASS = "https://overpass-api.de/api/interpreter"
_cache: dict = {}


async def find_pharmacies(lat: float, lng: float, radius_km: float) -> list:
    key = (round(lat, 2), round(lng, 2), round(radius_km))
    hit = _cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    r_m = int(radius_km * 1000)
    q = (f'[out:json][timeout:15];(node["amenity"="pharmacy"](around:{r_m},{lat},{lng});'
         f'way["amenity"="pharmacy"](around:{r_m},{lat},{lng}););out center tags;')
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": USER_AGENT}) as c:
        r = await c.post(OVERPASS, data={"data": q})
        r.raise_for_status()
    stores = []
    for el in r.json().get("elements", []):
        t = el.get("tags", {})
        la = el.get("lat") or (el.get("center") or {}).get("lat")
        lo = el.get("lon") or (el.get("center") or {}).get("lon")
        if la is None or lo is None:
            continue
        addr = ", ".join(x for x in [t.get("addr:housenumber"), t.get("addr:street"), t.get("addr:suburb"), t.get("addr:city")] if x)
        stores.append({"id": f"osm-{el['id']}", "name": t.get("name", "Pharmacy"), "lat": la, "lng": lo,
                       "address": addr or None, "phone": t.get("phone") or t.get("contact:phone"),
                       "hours": t.get("opening_hours")})
    _cache[key] = (time.time() + 6 * 3600, stores)
    return stores


class OsmStores(Connector):
    """Real stores from OSM. Prices come from the portal/crowd DB when available; otherwise the
    store is listed with the reference price as an UPPER BOUND and price_known=False."""
    kind = "store"
    id = "osm-stores"
    name = "Nearby stores (OpenStreetMap + portal prices)"

    def __init__(self, use_osm: bool = True):
        self.use_osm = use_osm
        if not use_osm:
            self.id, self.name = "db-stores", "Nearby stores (portal prices)"

    async def fetch(self, drug, qty, loc: Location, opts: SearchOptions):
        out = []
        # 1) verified/portal/crowd prices
        for r in db.nearby_prices(drug["id"], loc.lat, loc.lng, opts.radius_km):
            age_h = (time.time() - r["observed_at"]) / 3600
            conf = r["confidence"] * (0.5 if age_h > STALE_AFTER_HOURS else 1.0)
            store = {"id": f"db-{r['id']}", "name": r["name"], "lat": r["lat"], "lng": r["lng"],
                     "address": r["address"], "phone": r["phone"], "hours": r["hours"],
                     "delivers": bool(r["delivers"]),
                     "delivery": {"base_fee": r["delivery_base_fee"], "free_above": r["delivery_free_above"],
                                  "max_km": r["delivery_max_km"], "eta_minutes": 60}}
            notes = [f"Reported {int(age_h)}h ago"] + (["Price may be stale"] if age_h > STALE_AFTER_HOURS else [])
            out += store_quotes(store, drug, r["pack_price"] * packs_needed(qty, drug["pack_size"]), loc, opts,
                                source=r["source"], confidence=conf, observed_at=r["observed_at"],
                                in_stock=bool(r["in_stock"]), notes=notes)
        known = {(q.lat, q.lng) for q in out}
        # 2) real nearby stores without a price on file
        try:
            osm = await find_pharmacies(loc.lat, loc.lng, opts.radius_km) if self.use_osm else []
        except Exception:
            osm = []
        ref = drug["reference_price"] * packs_needed(qty, drug["pack_size"])
        extra = [s for s in osm if (s["lat"], s["lng"]) not in known]
        extra.sort(key=lambda s: (s["lat"] - loc.lat) ** 2 + (s["lng"] - loc.lng) ** 2)
        for s in extra[:8]:
            out += [q for q in store_quotes(
                s, drug, ref, loc, opts, source="osm+reference", confidence=0.1, observed_at=time.time(),
                price_known=False, notes=["No price on file - reference price shown as upper bound. Call to confirm."])
                if q.fulfilment == "pickup"]
        return out
