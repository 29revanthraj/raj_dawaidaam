import httpx
import pytest

from backend import catalogue
from backend.connectors.http_connector import HttpConnector
from backend.models import Location, SearchOptions


@pytest.mark.asyncio
@pytest.mark.parametrize("link,expected", [
    ("/products/metformin-500", "https://pharmacy.example/products/metformin-500"),
    ("https://shop.example/metformin", "https://shop.example/metformin"),
    ("javascript:alert(1)", None),
    (None, None),
])
async def test_connector_product_links(monkeypatch, link, expected):
    def handler(request):
        return httpx.Response(200, json={"items": [{"title": "Metformin 500 mg Tablets Strip of 10",
                                                   "price": 20, "stock": True, "url": link}]})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(handler), **kwargs))
    connector = HttpConnector({"id": "partner", "name": "Partner pharmacy", "respect_robots": False,
                               "search_url": "https://pharmacy.example/search?q={query}", "response": "json",
                               "items_path": "items", "fields": {"title": "title", "price": "price",
                                                                     "in_stock": "stock", "url": "url"}})
    quotes = await connector.fetch(catalogue.get_drug("metformin-500-tab"), 30,
                                   Location(lat=17, lng=78), SearchOptions())
    assert len(quotes) == 1
    assert quotes[0].url == expected
    assert quotes[0].item_price == 60


@pytest.mark.asyncio
async def test_liquid_prices_count_bottles_not_concentration_or_volume(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"items": [
            {"title": "Paracetamol 120 mg/5 ml Oral Suspension 60 ml", "price": 50, "stock": True},
            {"title": "Paracetamol 120 mg/5 ml Oral Suspension 100 ml", "price": 10, "stock": True},
        ]})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(handler), **kwargs))
    connector = HttpConnector({"id": "liquid-partner", "name": "Partner pharmacy", "respect_robots": False,
                               "search_url": "https://pharmacy.example/search?q={query}", "response": "json",
                               "items_path": "items", "fields": {"title": "title", "price": "price", "in_stock": "stock"}})
    quotes = await connector.fetch(catalogue.get_drug("paracetamol-120-suspension"), 2,
                                   None, SearchOptions(pincode="500001"))
    assert len(quotes) == 1
    assert quotes[0].item_price == 100