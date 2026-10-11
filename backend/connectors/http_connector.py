"""Config-driven connector for sites/APIs you are PERMITTED to query.

Before enabling one: read the site's Terms of Service, prefer an official/partner API,
keep respect_robots=true, and keep min_interval_s generous. See README.
"""
import asyncio
import math
import re
import time
from dataclasses import asdict, replace
from urllib.parse import quote_plus, urljoin, urlsplit

import httpx

from ..config import CONNECTOR_TIMEOUT, USER_AGENT
from ..delivery import DeliveryRule, compute_delivery
from ..models import Location, Quote, SearchOptions
from ..normalize import parse_pack_size, title_matches
from ..ranking import finalize
from .base import Connector
from .robots import robots


def get_path(obj, path: str):
    for part in path.split("."):
        if obj is None:
            return None
        obj = obj[int(part)] if isinstance(obj, list) and part.isdigit() else (obj.get(part) if isinstance(obj, dict) else None)
    return obj


def parse_price(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"\d[\d,]*(?:\.\d+)?", v)
        if m:
            return float(m.group(0).replace(",", ""))
    return None


class HttpConnector(Connector):
    kind = "online"

    @property
    def requires_coordinates(self) -> bool:
        return bool(self.cfg.get("hyperlocal") or "{lat" in self.cfg["search_url"] or "{lng" in self.cfg["search_url"]
                    or self.rule.per_km or self.rule.max_km is not None or self.rule.eta_per_km)

    def __init__(self, cfg: dict):
        self.cfg, self.id, self.name = cfg, cfg["id"], cfg["name"]
        self.rule = DeliveryRule.from_dict(cfg.get("delivery"))
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def _throttle(self):
        async with self._lock:
            wait = self.cfg.get("min_interval_s", 2) - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()

    def _items_json(self, data) -> list:
        items = get_path(data, self.cfg["items_path"]) or []
        f = self.cfg["fields"]
        return [{"title": str(get_path(i, f["title"]) or ""), "price": parse_price(get_path(i, f["price"])),
                 "in_stock": get_path(i, f["in_stock"]) if "in_stock" in f else None,
                 "url": (self.cfg.get("url_prefix", "") + str(get_path(i, f["url"]))) if "url" in f and get_path(i, f["url"]) else None}
                for i in items]

    def _items_html(self, html: str) -> list:
        from bs4 import BeautifulSoup  # lazy: only needed for HTML sources
        soup, f, out = BeautifulSoup(html, "html.parser"), self.cfg["fields"], []
        for card in soup.select(self.cfg["item_selector"]):
            t, p = card.select_one(f["title"]), card.select_one(f["price"])
            link = None
            if "url" in f:
                sel, _, attr = f["url"].partition("@")
                el = card.select_one(sel) if sel else card
                link = el.get(attr or "href") if el else None
            if t and p:
                out.append({"title": t.get_text(" ", strip=True), "price": parse_price(p.get_text()),
                            "in_stock": None, "url": link})
        return out

    async def fetch(self, drug, qty, loc: Location, opts: SearchOptions):
        url = self.cfg["search_url"].format(
            query=quote_plus(f"{drug['ingredient']} {drug['strength']} {drug['form']}"),
            lat=loc.lat if loc else "", lng=loc.lng if loc else "", pincode=opts.pincode or "")
        if self.cfg.get("respect_robots", True) and not await robots.allowed(url):
            raise PermissionError("Blocked by robots.txt")
        await self._throttle()
        headers = {"User-Agent": USER_AGENT, **self.cfg.get("headers", {})}
        async with httpx.AsyncClient(timeout=CONNECTOR_TIMEOUT, headers=headers, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
        items = self._items_json(r.json()) if self.cfg["response"] == "json" else self._items_html(r.text)

        matches = [i for i in items if i["price"] and title_matches(drug, i["title"])]
        if not matches:
            return []
        best = min(matches, key=lambda i: i["price"] / (parse_pack_size(i["title"], drug["unit"]) or drug["pack_size"]))
        pack = parse_pack_size(best["title"], drug["unit"]) or drug["pack_size"]
        item_price = round(best["price"] * math.ceil(qty / pack), 2)
        res = compute_delivery(replace(self.rule, min_order=0) if opts.basket_mode else self.rule, item_price, None)
        if not res.eligible:
            return []
        product_url = urljoin(str(r.url), best["url"]) if best["url"] else None
        if product_url and urlsplit(product_url).scheme not in {"http", "https"}:
            product_url = None
        return [finalize(Quote(
            id=f"{self.id}:delivery", provider=self.name, kind="online", fulfilment="delivery",
            source=self.id, confidence=0.7, item_price=item_price, delivery_fee=res.fee,
            platform_fee=res.platform_fee, eta_minutes=res.eta_minutes, in_stock=best["in_stock"],
            url=product_url, delivery_rule=asdict(self.rule), notes=res.notes + [f"Listing: {best['title'][:60]}"]))]
