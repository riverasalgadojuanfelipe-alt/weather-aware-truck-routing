"""Clients for the three third-party services we use.

* Nominatim (OpenStreetMap)  - geocoding
* OSRM                       - driving routes (with alternatives)
* Open-Meteo                 - hourly weather forecast
* National Weather Service   - hourly forecast fallback (United States only)

All of them are free and need no API key. The clients take their base URL
and HTTP session as arguments, which keeps them easy to fake in tests.
"""

from __future__ import annotations

import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
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
    source: str = ""             # which service produced the data

    def at(self, when: datetime) -> tuple[float, float, float]:
        """Conditions at the hour closest to `when` (clamped to the data we have)."""
        hours = (when - self.start).total_seconds() / 3600
        i = min(max(round(hours), 0), len(self.wind_mph) - 1)
        return self.wind_mph[i], self.rain_in_hr[i], self.snow_in_hr[i]


OPEN_METEO = "open-meteo"
NWS = "nws"


class WeatherProvider:
    """Hourly forecast per 0.1 degree cell: Open-Meteo, with an optional fallback.

    When Open-Meteo fails (quota exhausted, outage), the cells still missing are
    asked of `fallback`, an object with `fetch_cells(cells, day0, last_day)`.
    Results from either service share one in-process cache.
    """

    MAX_LOCATIONS_PER_REQUEST = 200
    CACHE_SECONDS = 60 * 60
    HOURLY_VARS = "wind_speed_10m,rain,showers,snowfall"

    def __init__(self, session: requests.Session, base_url: str, timeout: float = 20, fallback=None):
        self.session, self.base_url, self.timeout = session, base_url.rstrip("/"), timeout
        self.fallback = fallback
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

        if missing:
            try:
                self._fetch_open_meteo(missing, day0, now)
            except ProviderError as primary:
                if self.fallback is None:
                    raise
                self._fetch_fallback([k for k in missing if k not in self._cache or now - self._cache[k][0] > self.CACHE_SECONDS], day0, now, primary)

        return [self._cache[k][1] for k in keys]

    def _fetch_open_meteo(self, missing: list[tuple], day0: datetime, now: float) -> None:
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
                    "start_date": chunk[0][2].isoformat(),
                    "end_date": chunk[0][3].isoformat(),
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

    def _fetch_fallback(self, missing: list[tuple], day0: datetime, now: float, primary: ProviderError) -> None:
        cells = [(k[0], k[1]) for k in missing]
        try:
            found = self.fallback.fetch_cells(cells, day0, missing[0][3])
        except ProviderError as exc:
            raise ProviderError(
                f"No weather data available. Open-Meteo failed ({primary}); "
                f"the National Weather Service fallback failed too ({exc})"
            ) from exc
        for key in missing:
            self._cache[key] = (now, found[(key[0], key[1])])


def _parse_series(hourly: dict, day0: datetime) -> HourlySeries:
    def clean(values: list) -> list[float]:
        return [0.0 if v is None else float(v) for v in values]

    rain = [r + s for r, s in zip(clean(hourly["rain"]), clean(hourly["showers"]))]
    return HourlySeries(
        start=day0,
        wind_mph=clean(hourly["wind_speed_10m"]),
        rain_in_hr=rain,
        snow_in_hr=clean(hourly["snowfall"]),
        source=OPEN_METEO,
    )


class NWSWeatherProvider:
    """api.weather.gov gridded forecast. No key, but it wants an identifying User-Agent.

    A point is resolved to an NWS gridpoint once (cached per cell, the grid never
    changes), then the gridpoint's raw forecast layers are normalised to the units
    `risk.py` expects: wind in mph, rain and snow in inches per hour.
    """

    MAX_WORKERS = 8
    MM_PER_INCH = 25.4
    WIND_TO_MPH = {"wmoUnit:km_h-1": 1 / 1.609344, "wmoUnit:m_s-1": 2.236936, "wmoUnit:kn": 1.150779}
    LENGTH_TO_MM = {"wmoUnit:mm": 1.0, "wmoUnit:cm": 10.0, "wmoUnit:m": 1000.0}
    SNOW_TO_WATER = 0.1       # 10:1 snow-to-liquid ratio

    def __init__(self, session: requests.Session, base_url: str, timeout: float = 20):
        self.session, self.base_url, self.timeout = session, base_url.rstrip("/"), timeout
        self._gridpoints: dict[LatLon, tuple[str, int, int]] = {}

    def fetch_cells(self, cells: list[LatLon], day0: datetime, last_day) -> dict[LatLon, HourlySeries]:
        """Series for each cell, from `day0` to the end of `last_day` (same layout as Open-Meteo)."""
        hours = ((last_day - day0.date()).days + 1) * 24
        cells = sorted(set(cells))
        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as pool:
            for cell, grid in zip(cells, pool.map(self._gridpoint, cells)):
                self._gridpoints[cell] = grid
            grids = sorted({self._gridpoints[c] for c in cells})
            by_grid = dict(zip(grids, pool.map(lambda g: self._series(g, day0, hours), grids)))
        return {c: by_grid[self._gridpoints[c]] for c in cells}

    def _gridpoint(self, cell: LatLon) -> tuple[str, int, int]:
        if cell in self._gridpoints:
            return self._gridpoints[cell]
        data = _get_json(self.session, f"{self.base_url}/points/{cell[0]:.4f},{cell[1]:.4f}", {}, self.timeout)
        try:
            props = data["properties"]
            return props["gridId"], int(props["gridX"]), int(props["gridY"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("National Weather Service returned an unexpected gridpoint") from exc

    def _series(self, grid: tuple[str, int, int], day0: datetime, hours: int) -> HourlySeries:
        office, x, y = grid
        data = _get_json(self.session, f"{self.base_url}/gridpoints/{office}/{x},{y}", {}, self.timeout)
        try:
            props = data["properties"]
            wind, covered = self._layer(props["windSpeed"], day0, hours, self.WIND_TO_MPH, per_hour=True)
            qpf, _ = self._layer(props["quantitativePrecipitation"], day0, hours, self.LENGTH_TO_MM, per_hour=False)
            snow, _ = self._layer(props["snowfallAmount"], day0, hours, self.LENGTH_TO_MM, per_hour=False)
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("National Weather Service returned an unexpected forecast") from exc
        if not covered:
            raise ProviderError("National Weather Service forecast does not cover the requested dates")
        snow_in = [mm / self.MM_PER_INCH for mm in snow]
        # QPF is liquid-equivalent and includes melted snow; Open-Meteo's rain does not.
        rain_in = [max(0.0, mm / self.MM_PER_INCH - s * self.SNOW_TO_WATER) for mm, s in zip(qpf, snow_in)]
        return HourlySeries(day0, wind, rain_in, snow_in, source=NWS)

    @staticmethod
    def _layer(layer: dict, day0: datetime, hours: int, units: dict[str, float], per_hour: bool):
        """Spread an NWS layer ("start/PT6H" intervals) over `hours` hourly slots.

        `per_hour` layers hold a rate (wind); the others hold an amount per interval,
        which is divided evenly over its hours. Returns the hourly values converted
        with `units` (to mph for wind, to mm for amounts) and whether any hour was filled.
        """
        factor = units[layer["uom"]]
        out, covered = [0.0] * hours, False
        for item in layer["values"]:
            if item["value"] is None:
                continue
            begin, length = _parse_interval(item["validTime"])
            value = float(item["value"]) * factor
            if not per_hour:
                value /= length
            first = int((begin - day0).total_seconds() // 3600)
            for i in range(max(first, 0), min(first + length, hours)):
                out[i] = value
                covered = True
        return out, covered


_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?)?$")


def _parse_interval(text: str) -> tuple[datetime, int]:
    """"2026-11-02T12:00:00+00:00/PT6H" -> (start in UTC floored to the hour, hours)."""
    begin, _, duration = text.partition("/")
    match = _DURATION.match(duration)
    if not match:
        raise ValueError(f"unsupported interval {text!r}")
    days, hrs = (int(g or 0) for g in match.groups())
    return datetime.fromisoformat(begin).astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0), max(days * 24 + hrs, 1)


def forecast_window(departure: datetime, trip_hours: float, heatmap_hours: int = 48) -> tuple[datetime, datetime]:
    """Time span we need weather for: the whole trip and the heatmap slider."""
    return departure, departure + timedelta(hours=max(trip_hours, heatmap_hours) + 1)
