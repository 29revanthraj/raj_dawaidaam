import asyncio
import json
import time

from . import config
from .connectors.base import Connector
from .connectors.demo import DemoOnline, DemoStores
from .connectors.http_connector import HttpConnector
from .connectors.osm import OsmStores
from .models import ConnectorResult, Location, SearchOptions

_cache: dict = {}


def build_connectors() -> list:
    cfg = json.loads((config.DATA_DIR / "providers.json").read_text())
    cons: list = []
    for p in cfg["online"]:
        if p.get("enabled", True) is False:
            continue
        if p["type"] == "demo" and config.ENABLE_DEMO:
            cons.append(DemoOnline(p))
        elif p["type"] == "http":
            cons.append(HttpConnector(p))
    if config.ENABLE_DEMO:
        cons.append(DemoStores(cfg["demo_store_chains"]))
    # OSM connector always runs: it also serves portal/crowd prices from the DB
    cons.append(OsmStores(use_osm=config.ENABLE_OSM))
    return cons


async def run_connector(c: Connector, drug: dict, qty: int, loc: Location, opts: SearchOptions) -> ConnectorResult:
    key = (c.id, drug["id"], qty, round(loc.lat, 2) if loc else None, round(loc.lng, 2) if loc else None, opts.radius_km,
           opts.travel_cost_per_km, opts.pincode, opts.basket_mode)
    hit = _cache.get(key)
    if hit and hit[0] > time.time():
        return ConnectorResult(connector=c.id, ok=True, cached=True, quotes=hit[1])
    t0 = time.perf_counter()
    try:
        quotes = await asyncio.wait_for(c.fetch(drug, qty, loc, opts), timeout=config.CONNECTOR_TIMEOUT + 12)
        _cache[key] = (time.time() + config.CACHE_TTL, quotes)
        return ConnectorResult(connector=c.id, ok=True, quotes=quotes, took_ms=int((time.perf_counter() - t0) * 1000))
    except Exception as e:  # one broken source must never break the search
        return ConnectorResult(connector=c.id, ok=False, error=f"{type(e).__name__}: {e}",
                               took_ms=int((time.perf_counter() - t0) * 1000))


async def stream_results(connectors, drug, qty, loc, opts):
    tasks = [asyncio.create_task(run_connector(c, drug, qty, loc, opts)) for c in connectors]
    for fut in asyncio.as_completed(tasks):
        yield await fut
