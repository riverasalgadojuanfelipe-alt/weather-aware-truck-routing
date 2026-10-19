"""Clients for the three third-party services we use.

* Nominatim (OpenStreetMap)  - geocoding
* OSRM                       - driving routes (with alternatives)
* Open-Meteo                 - hourly weather forecast

All of them are free and need no API key. The clients take their base URL
and HTTP session as arguments, which keeps them easy to fake in tests.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

from .geo import LatLon, METERS_PER_MILE, grid_cell, haversine_miles


class ProviderError(Exception):
    """A third-party service failed or returned something unusable."""


def _get_json(session: requests.Session, url: str, params: dict, timeout: float) -> dict | list:
    try:
        resp = session.get(url, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise ProviderError(f"Could not reach {url}: {exc}") from exc
    if resp.status_code != 200:
        raise ProviderError(f"{url} returned HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        return resp.json()
    except ValueError as exc:
        raise ProviderError(f"{url} returned invalid JSON") from exc


# --------------------------------------------------------------------------- geocoding


@dataclass(frozen=True)
class Place:
    lat: float
    lon: float
    label: str


class Geocoder:
    def __init__(self, session: requests.Session, base_url: str, timeout: float = 20):
        self.session, self.base_url, self.timeout = session, base_url.rstrip("/"), timeout

    def geocode(self, query: str) -> Place:
        """Accepts either free text ("Dallas, TX") or "lat,lon"."""
        query = query.strip()
        parts = [p.strip() for p in query.split(",")]
        if len(parts) == 2:
            try:
                lat, lon = float(parts[0]), float(parts[1])
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    return Place(lat, lon, f"{lat:.4f}, {lon:.4f}")
            except ValueError:
                pass
        data = _get_json(
            self.session,
            f"{self.base_url}/search",
            {"q": query, "format": "jsonv2", "limit": 1},
            self.timeout,
        )
        if not data:
            raise ProviderError(f'No location found for "{query}"')
        hit = data[0]
        return Place(float(hit["lat"]), float(hit["lon"]), hit.get("display_name", query))


# --------------------------------------------------------------------------- routing


@dataclass(frozen=True)
class RawRoute:
    coords: list[LatLon]      # (lat, lon) polyline
    distance_miles: float     # as reported by the router
    duration_hours: float     # as reported by the router


class RouteProvider:
    """OSRM client that always tries to hand back up to `wanted` distinct routes."""

    def __init__(self, session: requests.Session, base_url: str, timeout: float = 20):
        self.session, self.base_url, self.timeout = session, base_url.rstrip("/"), timeout

    def _route(self, waypoints: list[LatLon], alternatives: bool) -> list[RawRoute]:
        path = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in waypoints)
        data = _get_json(
            self.session,
            f"{self.base_url}/route/v1/driving/{path}",
            {
                "overview": "full",
                "geometries": "geojson",
                "steps": "false",
                "alternatives": "3" if alternatives else "false",
            },
            self.timeout,
        )
        if data.get("code") != "Ok" or not data.get("routes"):
            raise ProviderError(f"Routing failed: {data.get('code')} {data.get('message', '')}".strip())
        return [
            RawRoute(
                coords=[(lat, lon) for lon, lat in r["geometry"]["coordinates"]],
                distance_miles=r["distance"] / METERS_PER_MILE,
                duration_hours=r["duration"] / 3600,
            )
            for r in data["routes"]
        ]

    def routes(self, origin: LatLon, destination: LatLon, wanted: int = 3) -> list[RawRoute]:
        found = self._route([origin, destination], alternatives=True)

        # OSRM often returns fewer than 3 alternatives. Top up by routing through
        # a detour waypoint to the left and right of the straight line, and keep
        # only candidates that really follow a different road.
        if len(found) < wanted:
            for via in _detour_waypoints(origin, destination):
                if len(found) >= wanted:
                    break
                try:
                    candidates = self._route([origin, via, destination], alternatives=False)
                except ProviderError:
                    continue
                for cand in candidates:
                    if len(found) < wanted and all(not _same_road(cand.coords, r.coords) for r in found):
                        found.append(cand)

        found.sort(key=lambda r: r.duration_hours)
        return found[:wanted]


def _detour_waypoints(a: LatLon, b: LatLon) -> list[LatLon]:
    """Waypoints beside the midpoint of a->b, at 18% and 30% of the trip length."""
    mid_lat, mid_lon = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    dlat, dlon = b[0] - a[0], b[1] - a[1]
    # Perpendicular direction (in degrees, good enough for picking a via point).
    norm = math.hypot(dlat, dlon) or 1.0
    perp_lat, perp_lon = -dlon / norm, dlat / norm
    out = []
    for frac in (0.18, 0.30):
        for sign in (1, -1):
            out.append((mid_lat + sign * perp_lat * norm * frac, mid_lon + sign * perp_lon * norm * frac))
    return out


def _same_road(a: list[LatLon], b: list[LatLon], tolerance_miles: float = 1.5, share: float = 0.85) -> bool:
    """True when at least `share` of route `a` runs within `tolerance_miles` of route `b`."""
    sample_a = a[:: max(1, len(a) // 60)]
    sample_b = b[:: max(1, len(b) // 300)]
    close = sum(1 for p in sample_a if min(haversine_miles(p, q) for q in sample_b) <= tolerance_miles)
    return close / len(sample_a) >= share


# --------------------------------------------------------------------------- weather


@dataclass(frozen=True)
class HourlySeries:
    """Hourly conditions for one location. Index 0 is `start` (UTC)."""

    start: datetime
    wind_mph: list[float]
    rain_in_hr: list[float]
    snow_in_hr: list[float]

    def at(self, when: datetime) -> tuple[float, float, float]:
        """Conditions at the hour closest to `when` (clamped to the data we have)."""
        hours = (when - self.start).total_seconds() / 3600
        i = min(max(round(hours), 0), len(self.wind_mph) - 1)
        return self.wind_mph[i], self.rain_in_hr[i], self.snow_in_hr[i]


class WeatherProvider:
    """Open-Meteo hourly forecast with a small in-process cache."""

    MAX_LOCATIONS_PER_REQUEST = 200
    CACHE_SECONDS = 60 * 60
    HOURLY_VARS = "wind_speed_10m,rain,showers,snowfall"

    def __init__(self, session: requests.Session, base_url: str, timeout: float = 20):
        self.session, self.base_url, self.timeout = session, base_url.rstrip("/"), timeout
        self._cache: dict[tuple, tuple[float, HourlySeries]] = {}

    def fetch(self, points: list[LatLon], start: datetime, end: datetime) -> list[HourlySeries]:
        """Series for each point, covering [start, end] (UTC, whole hours)."""
        start = start.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        end = end.astimezone(timezone.utc)
        first_day, last_day = start.date(), end.date()
        day0 = datetime(first_day.year, first_day.month, first_day.day, tzinfo=timezone.utc)

        # One cache entry (and one billed API location) per 0.1 degree cell.
        keys = [(*grid_cell(p), first_day, last_day) for p in points]
        now = time.time()
        missing = sorted({k for k in keys if k not in self._cache or now - self._cache[k][0] > self.CACHE_SECONDS})

        for i in range(0, len(missing), self.MAX_LOCATIONS_PER_REQUEST):
            chunk = missing[i : i + self.MAX_LOCATIONS_PER_REQUEST]
            data = _get_json(
                self.session,
                f"{self.base_url}/v1/forecast",
                {
                    "latitude": ",".join(f"{k[0]:.1f}" for k in chunk),
                    "longitude": ",".join(f"{k[1]:.1f}" for k in chunk),
                    "hourly": self.HOURLY_VARS,
                    "wind_speed_unit": "mph",
                    "precipitation_unit": "inch",
                    "timezone": "UTC",
                    "start_date": first_day.isoformat(),
                    "end_date": last_day.isoformat(),
                },
                self.timeout,
            )
            if isinstance(data, dict):
                if data.get("error"):
                    raise ProviderError(f"Weather service error: {data.get('reason')}")
                data = [data]
            if len(data) != len(chunk):
                raise ProviderError("Weather service returned an unexpected number of locations")
            for key, loc in zip(chunk, data):
                self._cache[key] = (now, _parse_series(loc["hourly"], day0))

        return [self._cache[k][1] for k in keys]


def _parse_series(hourly: dict, day0: datetime) -> HourlySeries:
    def clean(values: list) -> list[float]:
        return [0.0 if v is None else float(v) for v in values]

    rain = [r + s for r, s in zip(clean(hourly["rain"]), clean(hourly["showers"]))]
    return HourlySeries(
        start=day0,
        wind_mph=clean(hourly["wind_speed_10m"]),
        rain_in_hr=rain,
        snow_in_hr=clean(hourly["snowfall"]),
    )


def forecast_window(departure: datetime, trip_hours: float, heatmap_hours: int = 48) -> tuple[datetime, datetime]:
    """Time span we need weather for: the whole trip and the heatmap slider."""
    return departure, departure + timedelta(hours=max(trip_hours, heatmap_hours) + 1)
