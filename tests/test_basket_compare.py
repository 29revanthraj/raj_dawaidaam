from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from backend import aggregator, catalogue, db, main
from backend.basket_compare import compare_basket
from backend.connectors.demo import DemoOnline
from backend.delivery import DeliveryRule
from backend.models import Location, Quote, SearchOptions


ITEMS = [{"drug": catalogue.get_drug("metformin-500-tab"), "qty": 30},
         {"drug": catalogue.get_drug("amlodipine-5-tab"), "qty": 20}]
LOC = Location(lat=17, lng=78)


@pytest.mark.asyncio
async def test_coordinate_free_basket_checks_online_and_skips_location_sources():
    online = DemoOnline({"id": "postal-online", "name": "Postal online", "price_factor": 1,
                         "delivery": {"base_fee": 40}})
    local = DemoOnline({"id": "local-online", "name": "Local online", "price_factor": 1,
                        "hyperlocal": True})
    result = await compare_basket([online, local], ITEMS, None, SearchOptions(pincode="500001"))
    assert len(result["offers"]) == 1
    assert result["offers"][0]["total"] is not None
    assert result["offers"][0]["distance_km"] is None
    assert all(s["ok"] and s["connector"] == online.id for s in result["sources"])
    assert result["skipped_sources"][0]["connector"] == local.id
    with_coordinates = await compare_basket([online, local], ITEMS, LOC, SearchOptions(pincode="500001"))
    assert with_coordinates["skipped_sources"] == []
    assert len(with_coordinates["offers"]) == 2


class Source:
    id = "test-source"

    def __init__(self, rows):
        self.rows = rows

    async def fetch(self, drug, qty, loc, opts):
        assert opts.basket_mode
        return self.rows.get(drug["id"], [])


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    monkeypatch.setattr(aggregator, "_cache", {})


def quote(price, **changes):
    fields = dict(id="branch:delivery", provider="Test pharmacy", kind="online", fulfilment="delivery",
                  source="partner", item_price=price, in_stock=True,
                  delivery_fee=49, platform_fee=6,
                  delivery_rule=asdict(DeliveryRule(base_fee=49, platform_fee=6, free_above=499,
                                                   eta_minutes=120)))
    fields.update(changes)
    return Quote(**fields)


def source(first, second):
    return Source({ITEMS[0]["drug"]["id"]: first, ITEMS[1]["drug"]["id"]: second})


@pytest.mark.asyncio
@pytest.mark.parametrize("prices,subtotal,shipping,total", [
    ((100, 200), 300, 49, 355),
    ((250, 249), 499, 0, 505),
])
async def test_shipping_once_and_free_threshold(prices, subtotal, shipping, total):
    result = await compare_basket([source([quote(prices[0])], [quote(prices[1])])], ITEMS, LOC, SearchOptions())
    offer = result["offers"][0]
    assert offer["complete"] and offer["confirmed"] and offer["eligible"]
    assert offer["subtotal"] == subtotal
    assert offer["delivery_fee"] == shipping
    assert offer["platform_fee"] == 6
    assert offer["total"] == total
    assert offer["eta_minutes"] == 120
    assert "not a live checkout quote" in offer["notes"][-1]


@pytest.mark.asyncio
@pytest.mark.parametrize("second,status", [
    ([], "missing"),
    ([quote(200, in_stock=False)], "out_of_stock"),
    ([quote(200, in_stock=None)], "unconfirmed"),
    ([quote(200, price_known=False)], "unconfirmed"),
    ([quote(200, notes=["Price may be stale"])], "unconfirmed"),
])
async def test_incomplete_baskets_never_show_whole_total(second, status):
    result = await compare_basket([source([quote(100)], second)], ITEMS, LOC, SearchOptions())
    offer = result["offers"][0]
    assert offer["items"][1]["status"] == status
    assert not offer["complete"] and not offer["eligible"]
    assert offer["total"] is None and offer["subtotal"] is None


@pytest.mark.asyncio
async def test_different_branches_are_not_combined():
    result = await compare_basket([source([quote(100, id="branch-a:delivery")],
                                         [quote(200, id="branch-b:delivery")])], ITEMS, LOC, SearchOptions())
    assert len(result["offers"]) == 2
    assert all(not offer["complete"] for offer in result["offers"])


@pytest.mark.asyncio
async def test_pickup_travel_is_counted_once():
    fields = dict(kind="store", fulfilment="pickup", id="branch:pickup", lat=17.01, lng=78.01,
                  distance_km=2, address="Main Road", phone="12345", delivery_rule=None)
    result = await compare_basket([source([quote(100, **fields)], [quote(200, **fields)])],
                                  ITEMS, LOC, SearchOptions(travel_cost_per_km=8))
    offer = result["offers"][0]
    assert offer["total"] == 332 and offer["travel_cost"] == 32
    assert offer["delivery_fee"] == 0 and offer["platform_fee"] == 0
    assert offer["eta_minutes"] is None
    assert offer["lat"] == 17.01 and offer["address"] == "Main Road"


@pytest.mark.asyncio
async def test_store_delivery_fee_and_eta_use_distance_once():
    rule = asdict(DeliveryRule(base_fee=20, per_km=5, max_km=4, eta_minutes=30, eta_per_km=6))
    fields = dict(kind="store", distance_km=2, delivery_rule=rule)
    result = await compare_basket([source([quote(100, **fields)], [quote(200, **fields)])],
                                  ITEMS, LOC, SearchOptions())
    offer = result["offers"][0]
    assert offer["total"] == 330 and offer["delivery_fee"] == 30
    assert offer["eta_minutes"] == 42


@pytest.mark.asyncio
async def test_minimum_order_evaluated_on_whole_basket():
    connector = DemoOnline({"id": "demo-basket-test", "name": "Demo", "price_factor": 1,
                            "delivery": {"min_order": 50, "base_fee": 35, "eta_minutes": 60}})
    # Each line is below the minimum, but together they exceed it.
    result = await compare_basket([connector], ITEMS, LOC, SearchOptions())
    offer = result["offers"][0]
    assert offer["complete"] and offer["eligible"] and offer["demo"]
    assert not offer["confirmed"]
    assert all(line["item_price"] < 50 for line in offer["items"])
    assert offer["subtotal"] > 50 and offer["total"] == round(offer["subtotal"] + 35, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("rule", [None, asdict(DeliveryRule(min_order=500))])
async def test_unknown_shipping_or_unmet_minimum_has_no_total(rule):
    result = await compare_basket([source([quote(100, delivery_rule=rule)], [quote(200, delivery_rule=rule)])],
                                  ITEMS, LOC, SearchOptions())
    assert result["offers"][0]["complete"]
    assert not result["offers"][0]["eligible"]
    assert result["offers"][0]["total"] is None


@pytest.mark.asyncio
async def test_source_failure_does_not_hide_other_results():
    class Broken:
        id = "broken"

        async def fetch(self, *args):
            raise RuntimeError("Source unavailable")

    result = await compare_basket([Broken(), source([quote(100)], [quote(200)])], ITEMS, LOC, SearchOptions())
    assert len(result["offers"]) == 1
    assert len([s for s in result["sources"] if not s["ok"]]) == 2


def test_basket_comparison_endpoint_uses_private_saved_items(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "basket.db"))
    monkeypatch.setattr(main, "CONNECTORS", [source([quote(100)], [quote(200)])])
    db.init()
    url = "/api/basket/compare?lat=17&lng=78"
    with TestClient(main.app, base_url="https://testserver") as client:
        assert client.get(url).status_code == 401
        assert client.post("/api/auth/register", json={"email": "basket@example.com", "password": "secure-password-123"}).status_code == 201
        assert client.get(url).json()["offers"] == []
        for item in ITEMS:
            assert client.put("/api/basket", json={"drug_id": item["drug"]["id"], "qty": item["qty"]}).status_code == 200
        response = client.get(url)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["item_count"] == 2
        assert response.json()["offers"][0]["total"] == 355
        assert client.get("/api/basket/compare?lat=100&lng=78").status_code == 422
        client.post("/api/auth/logout")
        client.post("/api/auth/register", json={"email": "other@example.com", "password": "secure-password-123"})
        assert client.get(url).json()["offers"] == []


def test_basket_defaults_exclude_travel_and_checkout_controls(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "defaults.db"))
    fields = dict(kind="store", fulfilment="pickup", id="branch:pickup", lat=17.01, lng=78.01,
                  distance_km=2, delivery_rule=None)
    monkeypatch.setattr(main, "CONNECTORS", [source([quote(100, **fields)], [quote(200, **fields)])])
    db.init()
    with TestClient(main.app, base_url="https://testserver") as client:
        page = client.get("/").text
        assert "<h1>DawaiDaam</h1>" in page
        assert "<title>DawaiDaam" in page
        assert "basket-radius" not in page and "basket-travel" not in page
        assert client.get("/openapi.json").json()["info"]["title"] == "DawaiDaam"
        script = client.get("/app.js").text
        assert "basket-radius" not in script and "basket-travel" not in script
        assert "Copy medicine list" in script
        assert "Items have not been added to an external basket" in script
        client.post("/api/auth/register", json={"email": "defaults@example.com", "password": "secure-password-123"})
        for item in ITEMS:
            client.put("/api/basket", json={"drug_id": item["drug"]["id"], "qty": item["qty"]})
        offer = client.get("/api/basket/compare?lat=17&lng=78").json()["offers"][0]
        assert offer["total"] == 300 and offer["travel_cost"] == 0