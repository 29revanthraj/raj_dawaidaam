import pytest
from fastapi.testclient import TestClient

from backend import catalogue, db
from backend.main import app
from backend.medicine_info import INFO


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "accounts.db"))
    db.init()
    with TestClient(app, base_url="https://testserver") as client:
        yield client


def register(client, email="person@example.com"):
    return client.post("/api/auth/register", json={"email": email, "password": "correct-password-123"})


def test_registration_session_logout_and_login(client):
    response = register(client, "Person@Example.com")
    assert response.status_code == 201
    assert response.json()["email"] == "person@example.com"
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert client.get("/api/auth/me").status_code == 200
    with db.conn() as c:
        user = c.execute("SELECT * FROM users").fetchone()
        assert user["password_hash"] != "correct-password-123"
        session = c.execute("SELECT * FROM sessions").fetchone()
        assert session["token_hash"] != client.cookies.get("rxcompare_session")
    old_token = client.cookies.get("rxcompare_session")
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.set("rxcompare_session", old_token)
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"email": "person@example.com", "password": "incorrect-password"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "person@example.com", "password": "correct-password-123"}).status_code == 200


def test_validation_duplicates_and_cross_origin(client):
    assert register(client).status_code == 201
    assert register(client).status_code == 409
    assert client.post("/api/auth/register", json={"email": "bad-email", "password": "short"}).status_code == 422
    assert client.post("/api/auth/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/auth/me").headers["cache-control"] == "no-store"


def test_history_and_basket_are_private(client):
    item = {"drug_id": "metformin-500-tab", "qty": 30}
    assert client.get("/api/history").status_code == 401
    assert client.put("/api/basket", json=item).status_code == 401
    register(client)
    assert client.post("/api/history", json=item).status_code == 201
    history = client.get("/api/history").json()
    assert len(history) == 1 and history[0]["drug"]["id"] == item["drug_id"]
    assert "lat" not in history[0] and "pincode" not in history[0]
    assert client.put("/api/basket", json=item).status_code == 200
    assert client.put("/api/basket", json={**item, "qty": 45}).status_code == 200
    basket = client.get("/api/basket").json()
    assert len(basket) == 1 and basket[0]["qty"] == 45
    assert basket[0]["online_searches"]
    client.post("/api/auth/logout")
    register(client, "other@example.com")
    assert client.get("/api/history").json() == []
    assert client.get("/api/basket").json() == []
    client.delete("/api/basket/metformin-500-tab")
    client.delete("/api/history")
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "person@example.com", "password": "correct-password-123"})
    assert len(client.get("/api/basket").json()) == 1
    assert len(client.get("/api/history").json()) == 1
    assert client.delete("/api/history").status_code == 200
    assert client.delete("/api/basket/metformin-500-tab").status_code == 200
    assert client.get("/api/history").json() == []
    assert client.get("/api/basket").json() == []


def test_saved_medicine_validation_and_history_limit(client):
    register(client)
    for endpoint, method in [("/api/history", client.post), ("/api/basket", client.put)]:
        assert method(endpoint, json={"drug_id": "unknown", "qty": 10}).status_code == 404
        for qty in [0, -1, 1001]:
            assert method(endpoint, json={"drug_id": "metformin-500-tab", "qty": qty}).status_code == 422
    for _ in range(102):
        assert client.post("/api/history", json={"drug_id": "metformin-500-tab", "qty": 30}).status_code == 201
    assert len(client.get("/api/history").json()) == 100


def test_expired_sessions_and_login_throttle(client):
    register(client)
    with db.conn() as c:
        c.execute("UPDATE sessions SET expires_at=0")
    assert client.get("/api/auth/me").status_code == 401
    credentials = {"email": "person@example.com", "password": "wrong-password-123"}
    for _ in range(10):
        assert client.post("/api/auth/login", json=credentials).status_code == 401
    assert client.post("/api/auth/login", json=credentials).status_code == 429


def test_all_medicines_have_information_and_search_links(client):
    for drug in catalogue.all_drugs():
        assert drug["ingredient"] in INFO
        response = client.get(f"/api/drugs/{drug['id']}")
        assert response.status_code == 200
        info = response.json()["medicine_info"]
        for field in ["description", "uses", "usage", "side_effects", "warnings", "reference", "notice"]:
            assert info[field]
        for link in response.json()["online_searches"]:
            assert link["url"].startswith("https://")
            assert "name=" in link["url"]
    assert client.get("/api/drugs/unknown").status_code == 404


def test_pages_are_served(client):
    response = client.get("/")
    assert response.status_code == 200
    for page in ["login", "history", "basket", "compare"]:
        assert f'data-page="{page}"' in response.text
    assert client.get("/app.js").status_code == 200