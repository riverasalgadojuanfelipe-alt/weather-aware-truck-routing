"""Open-Meteo -> National Weather Service fallback, with simulated services (no network)."""

from datetime import datetime, timedelta, timezone

import pytest
import requests
from rest_framework.test import APIClient

from routing import views
from routing.providers import NWSWeatherProvider, Place, ProviderError, RawRoute, WeatherProvider
from routing.tests.test_providers import FakeResponse, weather_location

START = datetime(2026, 11, 2, 0, tzinfo=timezone.utc)
NWS_URL = "http://nws"
METEO_URL = "http://meteo"


class RoutedSession:
    """Answers by URL prefix; a value may be a response, an exception to raise, or a callable."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        for prefix, answer in self.routes.items():
            if url.startswith(prefix):
                if callable(answer):
                    answer = answer(url)
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise AssertionError(f"unexpected request to {url}")

    def urls(self, prefix):
        return [u for u, _ in self.calls if u.startswith(prefix)]


def interval(hour, length, value, day=START):
    return {"validTime": f"{day:%Y-%m-%d}T{hour:02d}:00:00+00:00/PT{length}H", "value": value}


def nws_grid(day=START, days=1):
    """Gridpoint forecast starting at midnight UTC of `day`: 10 mph, then 20 mph from noon."""
    later_days = [interval(0, 24, 16.09344, day + timedelta(days=d)) for d in range(1, days)]
    return FakeResponse(
        {
            "properties": {
                "windSpeed": {
                    "uom": "wmoUnit:km_h-1",
                    "values": [interval(0, 12, 16.09344, day), interval(12, 12, 32.18688, day), *later_days],
                },
                "quantitativePrecipitation": {"uom": "wmoUnit:mm", "values": [interval(6, 6, 12.7, day)]},
                "snowfallAmount": {"uom": "wmoUnit:mm", "values": [interval(8, 2, 25.4, day), interval(0, 6, None, day)]},
            }
        }
    )


def nws_point(grid_id="FWD", x=80, y=108):
    return FakeResponse({"properties": {"gridId": grid_id, "gridX": x, "gridY": y}})


def nws_session(points=nws_point, grid=nws_grid):
    return RoutedSession({f"{NWS_URL}/points/": lambda url: points(), f"{NWS_URL}/gridpoints/": lambda url: grid()})


def make_provider(meteo_answer, nws=None):
    nws = nws or nws_session()
    meteo = RoutedSession({METEO_URL: meteo_answer})
    return WeatherProvider(meteo, METEO_URL, fallback=NWSWeatherProvider(nws, NWS_URL)), meteo, nws


RATE_LIMITED = FakeResponse({"error": True, "reason": "Daily API request limit exceeded"}, status_code=429)


def test_nws_is_used_when_open_meteo_is_rate_limited():
    provider, meteo, nws = make_provider(RATE_LIMITED)
    series = provider.fetch([(32.78, -96.8)], START, START)[0]
    assert series.source == "nws"
    assert len(meteo.calls) == 1 and len(nws.urls(f"{NWS_URL}/gridpoints/")) == 1


def test_nws_is_used_when_open_meteo_is_unreachable():
    provider, _, _ = make_provider(requests.ConnectionError("down"))
    assert provider.fetch([(32.78, -96.8)], START, START)[0].source == "nws"


def test_nws_values_are_normalised_to_mph_and_inches_per_hour():
    provider, _, _ = make_provider(RATE_LIMITED)
    series = provider.fetch([(32.78, -96.8)], START, START)[0]
    assert len(series.wind_mph) == 24
    assert series.wind_mph[0] == pytest.approx(10.0) and series.wind_mph[23] == pytest.approx(20.0)
    assert series.rain_in_hr[5] == 0.0
    assert series.rain_in_hr[6] == pytest.approx(0.5 / 6)           # 12.7 mm over 6 h
    assert series.snow_in_hr[8] == pytest.approx(1.0 / 2)           # 25.4 mm over 2 h
    assert series.rain_in_hr[8] == pytest.approx(0.5 / 6 - 0.05)    # melted snow is not counted twice
    assert series.snow_in_hr[10] == 0.0
    assert series.at(datetime(2026, 11, 2, 7, tzinfo=timezone.utc))[0] == pytest.approx(10.0)


def test_open_meteo_is_preferred_and_labelled():
    provider, _, nws = make_provider(FakeResponse(weather_location()))
    assert provider.fetch([(32.78, -96.8)], START, START)[0].source == "open-meteo"
    assert nws.calls == []


def test_without_a_fallback_the_open_meteo_error_is_raised():
    provider = WeatherProvider(RoutedSession({METEO_URL: RATE_LIMITED}), METEO_URL)
    with pytest.raises(ProviderError, match="429"):
        provider.fetch([(32.78, -96.8)], START, START)


def test_fallback_series_are_cached_per_cell():
    provider, meteo, nws = make_provider(RATE_LIMITED)
    provider.fetch([(32.78, -96.8)], START, START)
    provider.fetch([(32.81, -96.84)], START, START)            # same 0.1 degree cell
    assert len(meteo.calls) == 1 and len(nws.urls(f"{NWS_URL}/gridpoints/")) == 1


def test_gridpoint_is_cached_per_cell_across_dates():
    provider, _, nws = make_provider(RATE_LIMITED, nws_session(grid=lambda: nws_grid(days=3)))
    provider.fetch([(32.78, -96.8)], START, START)
    provider.fetch([(32.78, -96.8)], START + timedelta(days=1), START + timedelta(days=1))
    assert len(nws.urls(f"{NWS_URL}/points/")) == 1
    assert len(nws.urls(f"{NWS_URL}/gridpoints/")) == 2         # a different day is a different forecast window


def test_cells_on_the_same_gridpoint_share_one_forecast_request():
    provider, _, nws = make_provider(RATE_LIMITED)
    series = provider.fetch([(32.0, -96.0), (32.1, -96.0), (32.2, -96.0)], START, START)
    assert len(nws.urls(f"{NWS_URL}/points/")) == 3
    assert len(nws.urls(f"{NWS_URL}/gridpoints/")) == 1
    assert series[0] is series[1] is series[2]


def test_only_the_cells_open_meteo_missed_go_to_the_fallback():
    answers = iter([FakeResponse([weather_location()]), RATE_LIMITED])
    provider, _, nws = make_provider(lambda url: next(answers))
    provider.MAX_LOCATIONS_PER_REQUEST = 1
    series = provider.fetch([(30.0, -100.0), (31.0, -99.0)], START, START)
    assert [s.source for s in series] == ["open-meteo", "nws"]
    assert nws.urls(f"{NWS_URL}/points/") == [f"{NWS_URL}/points/31.0000,-99.0000"]


def test_both_services_failing_raises_a_clear_error():
    provider, _, _ = make_provider(RATE_LIMITED, nws_session(points=lambda: FakeResponse({}, status_code=503)))
    with pytest.raises(ProviderError) as err:
        provider.fetch([(32.78, -96.8)], START, START)
    message = str(err.value)
    assert "No weather data available" in message and "Open-Meteo" in message and "National Weather Service" in message


def test_nws_outside_its_coverage_is_an_error():
    nws = nws_session(points=lambda: FakeResponse({"title": "Not Found"}, status_code=404))
    provider, _, _ = make_provider(RATE_LIMITED, nws)
    with pytest.raises(ProviderError):
        provider.fetch([(48.85, 2.35)], START, START)


def test_nws_forecast_that_misses_the_requested_dates_is_an_error():
    provider, _, _ = make_provider(RATE_LIMITED)
    later = START + timedelta(days=10)
    with pytest.raises(ProviderError, match="does not cover"):
        provider.fetch([(32.78, -96.8)], later, later)


def test_nws_rejects_unknown_units():
    bad = FakeResponse({"properties": {"windSpeed": {"uom": "wmoUnit:furlong", "values": []}}})
    provider, _, _ = make_provider(RATE_LIMITED, nws_session(grid=lambda: bad))
    with pytest.raises(ProviderError):
        provider.fetch([(32.78, -96.8)], START, START)


def test_nws_client_identifies_the_app():
    session = views._NWS.session
    assert session.headers["User-Agent"] and "python-requests" not in session.headers["User-Agent"]


# ------------------------------------------------------------------ through the API


class FakeGeocoder:
    def geocode(self, query):
        return Place(40.0, -100.0 if query == "A" else -95.0, query)


class FakeRoutes:
    def routes(self, origin, destination, wanted=3):
        return [RawRoute([(40.0, -100.0 + i * 0.5) for i in range(11)], 260.0, 5.0)]


def api_payload():
    return {
        "origin": "A",
        "destination": "B",
        "departure": (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
        "load_lbs": 30000,
        "interval_miles": 25,
    }


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(views, "_GEOCODER", FakeGeocoder())
    monkeypatch.setattr(views, "_ROUTES", FakeRoutes())
    return APIClient()


def test_api_answers_from_the_fallback_when_open_meteo_is_over_quota(api, monkeypatch):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    provider, _, _ = make_provider(RATE_LIMITED, nws_session(grid=lambda: nws_grid(today, days=5)))
    monkeypatch.setattr(views, "_WEATHER", provider)
    resp = api.post("/api/analyze", api_payload(), format="json")
    assert resp.status_code == 200


def test_api_returns_502_with_a_message_when_both_services_fail(api, monkeypatch):
    provider, _, _ = make_provider(RATE_LIMITED, nws_session(points=lambda: FakeResponse({}, status_code=503)))
    monkeypatch.setattr(views, "_WEATHER", provider)
    resp = api.post("/api/analyze", api_payload(), format="json")
    assert resp.status_code == 502
    assert "No weather data available" in resp.json()["detail"]
