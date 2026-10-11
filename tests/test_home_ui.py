from html.parser import HTMLParser

from fastapi.testclient import TestClient

from backend import catalogue, main


class HomeParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.cards = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if "data-home-drug" in attrs:
            self.cards.append((tag, attrs))


def test_home_cards_are_accessible_buttons_for_existing_medicines():
    with TestClient(main.app) as client:
        response = client.get("/")
        assert response.status_code == 200
        page = HomeParser()
        page.feed(response.text)
        assert len(page.ids) == len(set(page.ids))
        assert len(page.cards) == 4
        for tag, attrs in page.cards:
            assert tag == "button" and attrs["type"] == "button"
            drug = catalogue.get_drug(attrs["data-home-drug"])
            assert drug is not None
            assert client.get(f'/api/drugs/{drug["id"]}').status_code == 200
        assert 'href="#q"' in response.text
        assert 'aria-labelledby="hero-title"' in response.text
        assert "not self-medication" in response.text
        assert "python-host-7" in response.text
        for element in ("q", "qty", "geo", "go", "welcome", "medicine-details", "checkout-address"):
            assert element in page.ids


def test_home_styles_and_card_handler_are_served():
    with TestClient(main.app) as client:
        styles = client.get("/styles.css?v=colourful-home-5")
        script = client.get("/app.js?v=colourful-home-5")
        assert styles.status_code == script.status_code == 200
        assert ".home-hero" in styles.text
        assert "@media(max-width:600px)" in styles.text
        assert "prefers-reduced-motion" in styles.text
        assert "[data-home-drug]" in script.text
        assert "selectDrug(button.dataset.homeDrug)" in script.text