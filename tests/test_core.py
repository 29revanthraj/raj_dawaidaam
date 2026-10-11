import json
import pathlib

import pytest

from backend.delivery import DeliveryRule, compute_delivery, travel_cost
from backend.geo import haversine_km
from backend.normalize import packs_needed, parse_pack_size, search_catalogue, title_matches

DRUGS = json.loads((pathlib.Path(__file__).parent.parent / "data" / "drugs.json").read_text())
METFORMIN = next(d for d in DRUGS if d["id"] == "metformin-500-tab")


def test_free_delivery_threshold():
    rule = DeliveryRule(base_fee=49, free_above=499, platform_fee=6)
    assert compute_delivery(rule, 300).fee == 49
    assert compute_delivery(rule, 500).fee == 0
    assert compute_delivery(rule, 500).platform_fee == 6


def test_per_km_and_range_limit():
    rule = DeliveryRule(base_fee=15, per_km=6, max_km=8, eta_minutes=25, eta_per_km=4)
    r = compute_delivery(rule, 100, 3)
    assert r.fee == 33 and r.eta_minutes == 37
    assert not compute_delivery(rule, 100, 9).eligible


def test_min_order():
    assert not compute_delivery(DeliveryRule(min_order=50), 20).eligible


def test_travel_cost_round_trip():
    assert travel_cost(2.5, 8) == 40.0
    assert travel_cost(2.5, 8, round_trip=False) == 20.0


def test_haversine():
    assert haversine_km(17.385, 78.4867, 17.385, 78.4867) == 0
    assert 110 < haversine_km(0, 0, 1, 0) < 112


def test_packs():
    assert packs_needed(30, 10) == 3 and packs_needed(31, 10) == 4 and packs_needed(0, 10) == 1


def test_search_handles_brand_and_typo():
    assert search_catalogue("glycomet", DRUGS)[0]["id"] == "metformin-500-tab"
    assert search_catalogue("metformn", DRUGS)[0]["id"] == "metformin-500-tab"


def test_title_matching_requires_strength():
    assert title_matches(METFORMIN, "Metformin 500mg Tablets Strip of 10")
    assert not title_matches(METFORMIN, "Metformin 1000 mg Tablet")
    assert parse_pack_size("Dolo 650 Strip of 15 tablets") == 15


def test_total_calculation():
    pytest.importorskip("pydantic")
    from backend.models import Quote
    from backend.ranking import finalize, sort_quotes
    a = finalize(Quote(id="a", provider="A", kind="online", fulfilment="delivery", source="t", item_price=100, delivery_fee=40))
    b = finalize(Quote(id="b", provider="B", kind="store", fulfilment="pickup", source="t", item_price=120, travel_cost=10))
    c = finalize(Quote(id="c", provider="C", kind="store", fulfilment="pickup", source="t", item_price=50, price_known=False))
    assert a.total == 140 and b.total == 130
    assert [q.id for q in sort_quotes([a, b, c])] == ["b", "a", "c"]   # unconfirmed prices rank last
