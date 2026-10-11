import pytest
from fastapi.testclient import TestClient

from backend import db, main


ADDRESS = dict(label="Home", recipient="Test Person", line1="12 Main Road", line2="Near park",
               city="Hyderabad", state="Telangana", pincode="500001", lat=17.38, lng=78.48)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "addresses.db"))
    db.init()
    with TestClient(main.app, base_url="https://testserver") as client:
        yield client


def register(client, email="person@example.com"):
    assert client.post("/api/auth/register", json={"email": email, "password": "correct-password-123"}).status_code == 201


def test_address_crud_and_persistence(client):
    register(client)
    first = client.post("/api/addresses", json=ADDRESS)
    assert first.status_code == 201
    address = first.json()
    assert "user_id" not in address
    second = client.post("/api/addresses", json={**ADDRESS, "label": "Parents' home"}).json()
    assert second["id"] != address["id"]
    assert len(client.get("/api/addresses").json()) == 2
    updated = {**ADDRESS, "label": "Updated home", "line2": "", "pincode": "500002"}
    assert client.put(f'/api/addresses/{address["id"]}', json=updated).json() == {"id": address["id"], **updated}
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "person@example.com", "password": "correct-password-123"})
    assert len(client.get("/api/addresses").json()) == 2
    assert client.delete(f'/api/addresses/{address["id"]}').status_code == 200
    assert client.delete(f'/api/addresses/{address["id"]}').status_code == 404
    assert client.get("/api/addresses").json() == [second]
    db.init()
    assert client.get("/api/addresses").json() == [second]


def test_address_privacy_and_origin_protection(client):
    assert client.get("/api/addresses").status_code == 401
    assert client.post("/api/addresses", json=ADDRESS).status_code == 401
    register(client)
    address_id = client.post("/api/addresses", json=ADDRESS).json()["id"]
    assert client.get("/api/addresses").headers["cache-control"] == "no-store"
    for method, path in [(client.post, "/api/addresses"), (client.put, f"/api/addresses/{address_id}"),
                         (client.delete, f"/api/addresses/{address_id}")]:
        kwargs = {"headers": {"Origin": "https://evil.example"}}
        if method != client.delete:
            kwargs["json"] = ADDRESS
        assert method(path, **kwargs).status_code == 403
    client.post("/api/auth/logout")
    register(client, "other@example.com")
    assert client.get("/api/addresses").json() == []
    assert client.put(f"/api/addresses/{address_id}", json=ADDRESS).status_code == 404
    assert client.delete(f"/api/addresses/{address_id}").status_code == 404
    assert client.get(f"/api/basket/compare?address_id={address_id}").status_code == 404


@pytest.mark.parametrize("field,value", [("label", "  "), ("recipient", ""), ("line1", ""),
    ("city", ""), ("state", ""), ("pincode", "012345"), ("pincode", "50001"),
    ("pincode", "abcdef"), ("lat", 91), ("lng", -181), ("label", "x" * 61)])
def test_address_validation(client, field, value):
    register(client)
    assert client.post("/api/addresses", json={**ADDRESS, field: value}).status_code == 422
    assert client.get("/api/addresses").json() == []


def test_checkout_uses_owned_saved_address_and_updated_location(client, monkeypatch):
    calls = []

    async def fake_compare(connectors, items, location, options):
        calls.append((location.model_dump(), options.pincode))
        return {"offers": [], "sources": []}

    monkeypatch.setattr(main, "compare_basket", fake_compare)
    register(client)
    address_id = client.post("/api/addresses", json=ADDRESS).json()["id"]
    client.put("/api/basket", json={"drug_id": "metformin-500-tab", "qty": 30})
    response = client.get(f"/api/basket/compare?address_id={address_id}&lat=0&lng=0&pincode=999999")
    assert response.status_code == 200
    assert calls[-1] == ({"lat": ADDRESS["lat"], "lng": ADDRESS["lng"]}, ADDRESS["pincode"])
    assert response.json()["selected_address"]["id"] == address_id
    assert response.json()["location"] == {"lat": ADDRESS["lat"], "lng": ADDRESS["lng"], "pincode": ADDRESS["pincode"]}
    updated = {**ADDRESS, "lat": 18, "pincode": "500002"}
    client.put(f"/api/addresses/{address_id}", json=updated)
    assert client.get(f"/api/basket/compare?address_id={address_id}").status_code == 200
    assert calls[-1] == ({"lat": 18, "lng": ADDRESS["lng"]}, "500002")
    assert client.get("/api/basket/compare").status_code == 422
    assert client.get("/api/basket/compare?lat=17&lng=78").json()["selected_address"] is None
    client.delete(f"/api/addresses/{address_id}")
    assert client.get(f"/api/basket/compare?address_id={address_id}").status_code == 404


def test_address_page_and_selector_served(client):
    html = client.get("/").text
    assert 'data-page="addresses"' in html
    assert 'id="checkout-address"' in html
    assert 'id="address-form"' in html
    assert "Select on map" not in html
    assert 'id="address-geo"' in html
    assert 'id="address-lat" type="number" min="-90" max="90" step="any" required' not in html


def test_address_coordinates_optional_and_checkout_fallback(client, monkeypatch):
    register(client)
    body = {key: value for key, value in ADDRESS.items() if key not in {"lat", "lng"}}
    response = client.post("/api/addresses", json=body)
    assert response.status_code == 201
    address = response.json()
    assert address["lat"] is None and address["lng"] is None
    assert client.put(f'/api/addresses/{address["id"]}', json={**body, "lat": None, "lng": None}).status_code == 200
    assert client.post("/api/addresses", json={**body, "lat": 17}).status_code == 422
    assert client.post("/api/addresses", json={**body, "lng": 78}).status_code == 422
    without_coordinates = client.get(f'/api/basket/compare?address_id={address["id"]}')
    assert without_coordinates.status_code == 200
    assert without_coordinates.json()["location"] == {"lat": None, "lng": None, "pincode": body["pincode"]}
    client.put("/api/basket", json={"drug_id": "metformin-500-tab", "qty": 30})
    calls = []

    async def fake_compare(connectors, items, location, options):
        calls.append((location, options.pincode))
        return {"offers": [], "sources": [], "skipped_sources": []}

    monkeypatch.setattr(main, "compare_basket", fake_compare)
    assert client.get(f'/api/basket/compare?address_id={address["id"]}').status_code == 200
    assert calls == [(None, body["pincode"])]
    assert client.get(f'/api/basket/compare?address_id={address["id"]}&lat=17').status_code == 422
    result = client.get(f'/api/basket/compare?address_id={address["id"]}&lat=17&lng=78&pincode=999999')
    assert result.status_code == 200
    assert result.json()["selected_address"]["id"] == address["id"]
    assert result.json()["location"] == {"lat": 17, "lng": 78, "pincode": body["pincode"]}


def test_existing_required_coordinate_table_migration(client):
    register(client)
    address = client.post("/api/addresses", json=ADDRESS).json()
    with db.conn() as c:
        c.execute("ALTER TABLE home_addresses RENAME TO old_addresses")
        c.execute("DROP INDEX ix_address_user")
        c.execute("""CREATE TABLE home_addresses(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            label TEXT NOT NULL, recipient TEXT NOT NULL, line1 TEXT NOT NULL, line2 TEXT NOT NULL,
            city TEXT NOT NULL, state TEXT NOT NULL, pincode TEXT NOT NULL,
            lat REAL NOT NULL, lng REAL NOT NULL)""")
        c.execute("INSERT INTO home_addresses SELECT * FROM old_addresses")
        c.execute("DROP TABLE old_addresses")
    db.init()
    assert client.get("/api/addresses").json() == [address]
    assert client.post("/api/addresses", json={**ADDRESS, "lat": None, "lng": None}).status_code == 201