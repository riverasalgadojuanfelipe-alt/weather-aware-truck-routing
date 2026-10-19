"""Provider clients against canned responses (no network)."""

from datetime import datetime, timezone

import pytest

from routing.providers import Geocoder, ProviderError, RouteProvider, WeatherProvider


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload, self.status_code, self.text = payload, status_code, str(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return self.responses.pop(0)


def test_geocoder_accepts_lat_lon_without_a_request():
    session = FakeSession()
    place = Geocoder(session, "http://x").geocode("32.7767, -96.797")
    assert (place.lat, place.lon) == (32.7767, -96.797)
    assert session.calls == []


def test_geocoder_parses_nominatim_result():
    session = FakeSession(FakeResponse([{"lat": "32.78", "lon": "-96.80", "display_name": "Dallas, Texas"}]))
    place = Geocoder(session, "http://x").geocode("Dallas, TX")
    assert place.label == "Dallas, Texas" and place.lat == 32.78


def test_geocoder_reports_unknown_places():
    with pytest.raises(ProviderError):
        Geocoder(FakeSession(FakeResponse([])), "http://x").geocode("zzzzzz")


def osrm_route(lon_a, duration):
    return {
        "distance": 160934.4,   # 100 miles
        "duration": duration,
        "geometry": {"coordinates": [[lon_a, 30.0], [lon_a + 1, 30.0], [lon_a + 2, 30.5]]},
    }


def test_route_provider_converts_units_and_sorts_by_duration():
    session = FakeSession(
        FakeResponse({"code": "Ok", "routes": [osrm_route(-100, 7200), osrm_route(-100.0, 3600), osrm_route(-100.0, 5400)]})
    )
    routes = RouteProvider(session, "http://x").routes((30, -100), (30.5, -98))
    assert [round(r.duration_hours, 1) for r in routes] == [1.0, 1.5, 2.0]
    assert routes[0].distance_miles == pytest.approx(100.0)
    assert routes[0].coords[0] == (30.0, -100)         # (lat, lon), not (lon, lat)


def test_route_provider_surfaces_routing_errors():
    session = FakeSession(FakeResponse({"code": "NoRoute", "message": "no route"}))
    with pytest.raises(ProviderError):
        RouteProvider(session, "http://x").routes((0, 0), (1, 1))


def weather_location():
    day = list(range(24))
    return {
        "hourly": {
            "wind_speed_10m": [float(h) for h in day],
            "rain": [0.1] * 24,
            "showers": [0.05] * 24,
            "snowfall": [None] * 24,
        }
    }


def test_weather_provider_parses_multiple_locations_and_adds_rain_and_showers():
    session = FakeSession(FakeResponse([weather_location(), weather_location()]))
    provider = WeatherProvider(session, "http://x")
    start = datetime(2026, 11, 2, 6, 30, tzinfo=timezone.utc)
    series = provider.fetch([(30.0, -100.0), (31.0, -99.0)], start, start.replace(hour=20))
    assert len(series) == 2
    wind, rain, snow = series[0].at(datetime(2026, 11, 2, 9, 10, tzinfo=timezone.utc))
    assert wind == 9.0 and rain == pytest.approx(0.15) and snow == 0.0
    params = session.calls[0][1]
    assert params["wind_speed_unit"] == "mph" and params["precipitation_unit"] == "inch"


def test_weather_provider_caches_nearby_points():
    session = FakeSession(FakeResponse(weather_location()))
    provider = WeatherProvider(session, "http://x")
    start = datetime(2026, 11, 2, 0, tzinfo=timezone.utc)
    provider.fetch([(30.001, -100.001)], start, start)
    provider.fetch([(30.002, -100.002)], start, start)      # same ~1 km cell
    assert len(session.calls) == 1


def test_weather_provider_wraps_http_errors():
    session = FakeSession(FakeResponse({"reason": "boom"}, status_code=500))
    start = datetime(2026, 11, 2, tzinfo=timezone.utc)
    with pytest.raises(ProviderError):
        WeatherProvider(session, "http://x").fetch([(1.0, 1.0)], start, start)


def test_series_clamps_outside_the_forecast_window():
    session = FakeSession(FakeResponse(weather_location()))
    series = WeatherProvider(session, "http://x").fetch([(1.0, 1.0)], datetime(2026, 11, 2, tzinfo=timezone.utc), datetime(2026, 11, 2, tzinfo=timezone.utc))[0]
    assert series.at(datetime(2026, 11, 5, tzinfo=timezone.utc))[0] == 23.0
