from datetime import datetime, timedelta, timezone

import pytest
from rest_framework.test import APIClient

from routing import views
from routing.providers import HourlySeries, Place, ProviderError, RawRoute


class FakeGeocoder:
    def geocode(self, query):
        if query == "nowhere":
            raise ProviderError('No location found for "nowhere"')
        return Place(40.0, -100.0 if query == "A" else -95.0, query)


class FakeRoutes:
    def routes(self, origin, destination, wanted=3):
        pts = [(40.0, -100.0 + i * 0.5) for i in range(11)]
        return [RawRoute(pts, 260.0, 5.0)]


class FakeWeather:
    def fetch(self, points, start, end):
        return [HourlySeries(start.replace(hour=0, minute=0, second=0, microsecond=0), [10.0] * 96, [0.0] * 96, [0.0] * 96) for _ in points]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(views, "_GEOCODER", FakeGeocoder())
    monkeypatch.setattr(views, "_ROUTES", FakeRoutes())
    monkeypatch.setattr(views, "_WEATHER", FakeWeather())
    return APIClient()


def payload(**over):
    body = {
        "origin": "A",
        "destination": "B",
        "departure": (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
        "load_lbs": 30000,
        "interval_miles": 25,
    }
    body.update(over)
    return body


def test_analyze_happy_path(client):
    resp = client.post("/api/analyze", payload(), format="json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["recommendation"]["route_id"] == 0
    assert data["request"]["origin_label"] == "A"
    assert data["routes"][0]["checkpoints"][0]["risk"] == "low"
    assert "weather_provider" in data


@pytest.mark.parametrize(
    "override",
    [
        {"load_lbs": -1},
        {"load_lbs": 999999},
        {"interval_miles": 15},
        {"departure": "2020-01-01T00:00:00Z"},
        {"departure": "not a date"},
        {"origin": ""},
    ],
)
def test_analyze_validates_input(client, override):
    assert client.post("/api/analyze", payload(**override), format="json").status_code == 400


def test_analyze_rejects_departures_beyond_the_forecast(client):
    far = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    assert client.post("/api/analyze", payload(departure=far), format="json").status_code == 400


def test_provider_failures_become_502(client):
    resp = client.post("/api/analyze", payload(origin="nowhere"), format="json")
    assert resp.status_code == 502 and "nowhere" in resp.json()["detail"]


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}
