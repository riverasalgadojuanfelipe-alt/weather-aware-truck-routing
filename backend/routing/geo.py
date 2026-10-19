"""Small geometry helpers: distances along a polyline and sampling points."""

from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass

EARTH_RADIUS_MILES = 3958.7613
METERS_PER_MILE = 1609.344

LatLon = tuple[float, float]


def haversine_miles(a: LatLon, b: LatLon) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(h))


def cumulative_miles(points: list[LatLon]) -> list[float]:
    """Distance from the first point to every point, in miles."""
    total = 0.0
    out = [0.0]
    for prev, cur in zip(points, points[1:]):
        total += haversine_miles(prev, cur)
        out.append(total)
    return out


@dataclass(frozen=True)
class Sample:
    mile: float
    lat: float
    lon: float


def sample_along(points: list[LatLon], cum: list[float], interval_miles: float) -> list[Sample]:
    """Points every `interval_miles` along the line, always including start and end.

    `cum` is the cumulative distance list for `points`, so callers can reuse it.
    """
    if len(points) < 2:
        raise ValueError("a route needs at least two points")
    if interval_miles <= 0:
        raise ValueError("interval must be positive")

    total = cum[-1]
    marks = []
    m = 0.0
    while m < total:
        marks.append(m)
        m += interval_miles
    marks.append(total)

    samples = []
    for mark in marks:
        i = bisect_left(cum, mark)
        if i == 0:
            lat, lon = points[0]
        else:
            seg = cum[i] - cum[i - 1]
            t = 0.0 if seg == 0 else (mark - cum[i - 1]) / seg
            lat = points[i - 1][0] + t * (points[i][0] - points[i - 1][0])
            lon = points[i - 1][1] + t * (points[i][1] - points[i - 1][1])
        samples.append(Sample(mark, lat, lon))
    return samples


def segment_miles(sample_miles: list[float]) -> list[float]:
    """Miles of road each checkpoint is responsible for.

    Every checkpoint "owns" the stretch from the midpoint with the previous
    checkpoint to the midpoint with the next one, so the values add up to
    the full route length.
    """
    n = len(sample_miles)
    if n == 1:
        return [0.0]
    out = []
    for i, mile in enumerate(sample_miles):
        left = mile if i == 0 else (sample_miles[i - 1] + mile) / 2
        right = mile if i == n - 1 else (mile + sample_miles[i + 1]) / 2
        out.append(right - left)
    return out


def decimate(points: list[LatLon], max_points: int) -> list[LatLon]:
    """Reduce a polyline to at most ~max_points, keeping first and last."""
    if len(points) <= max_points:
        return points
    step = math.ceil(len(points) / max_points)
    out = points[::step]
    if out[-1] != points[-1]:
        out.append(points[-1])
    return out
