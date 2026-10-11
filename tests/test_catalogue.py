import pytest
from fastapi.testclient import TestClient

from backend import catalogue, main, medicine_info
from backend.normalize import packs_needed, parse_pack_size, search_catalogue, title_matches


def test_catalogue_integrity_and_safety():
    drugs = catalogue.all_drugs()
    assert len(drugs) == 27
    assert len({d["id"] for d in drugs}) == len(drugs)
    for drug in drugs:
        assert drug["pack_size"] > 0 and drug["reference_price"] > 0
        info = medicine_info.details(drug)
        assert all(info[key] for key in ("description", "uses", "usage", "warnings", "side_effects", "reference", "safety_disclaimer"))
        assert "medicinal drug" in info["safety_disclaimer"]
        if drug["rx_required"]:
            assert "Prescription required" in info["safety_disclaimer"]
        if drug.get("antibiotic"):
            assert drug["rx_required"] and "viral colds" in info["safety_disclaimer"]
        if drug["unit"] == "bottle":
            assert drug["pack_size"] == 1 and drug["pack_volume_ml"] > 0
            assert "not a dose" in info["usage"]
            assert "children's doses" in info["safety_disclaimer"]


def test_browse_all_and_liquids():
    with TestClient(main.app) as client:
        assert len(client.get("/api/drugs").json()) == 27
        liquids = client.get("/api/drugs?liquids_only=true").json()
        assert len(liquids) == 6
        assert all(d["unit"] == "bottle" for d in liquids)
        assert any(d["id"] == "cetirizine-5-syrup" for d in client.get("/api/drugs/search?q=syrup").json())
        assert any(d["id"] == "paracetamol-120-suspension" for d in client.get("/api/drugs/search?q=calpol").json())
        assert "Syrups &amp; liquids" in client.get("/").text


@pytest.mark.parametrize("query,expected", [("azithral", "azithromycin-500-tab"), ("duphalac", "lactulose-solution"), ("omez", "omeprazole-20-cap")])
def test_indian_brand_search(query, expected):
    assert search_catalogue(query, catalogue.all_drugs())[0]["id"] == expected


def test_liquids_are_not_matched_to_tablets_or_wrong_concentrations_and_sizes():
    drug = catalogue.get_drug("paracetamol-120-suspension")
    assert title_matches(drug, "Paracetamol 120 mg/5 ml Oral Suspension 60 ml")
    assert not title_matches(drug, "Paracetamol 250 mg/5 ml Oral Suspension 60 ml")
    assert not title_matches(drug, "Paracetamol 120 mg/5 ml Oral Suspension 100 ml")
    assert not title_matches(drug, "Paracetamol 120 mg/5 ml Tablet")
    assert not title_matches(catalogue.get_drug("paracetamol-500-tab"), "Paracetamol 500 mg Syrup 60 ml")
    assert parse_pack_size("Paracetamol 120 mg/5 ml 60 ml Suspension", "bottle") == 1
    assert parse_pack_size("Pack of 2 bottles, 60 ml each", "bottle") == 2
    assert packs_needed(2, drug["pack_size"]) == 2