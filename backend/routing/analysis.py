"""Orchestration: routes -> checkpoints -> weather -> risk -> recommendation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from . import risk
from .geo import cumulative_miles, decimate, grid_cell, sample_along, segment_miles
from .providers import RawRoute, forecast_window
from .recommend import RouteMetrics, explain, rank

HEATMAP_HOURS = 48
MAX_GEOMETRY_POINTS = 1500
ALLOWED_INTERVALS = (10, 25, 50)


@dataclass(frozen=True)
class TripRequest:
    origin: tuple[float, float]
    destination: tuple[float, float]
    departure: datetime          # timezone-aware
    load_lbs: float
    interval_miles: int = 25


def analyze(req: TripRequest, route_provider, weather_provider) -> dict:
    """Run the full analysis. Providers are passed in so tests can fake them."""
    raw_routes: list[RawRoute] = route_provider.routes(req.origin, req.destination)

    # Checkpoints for every route first, so weather is fetched in one batch.
    prepared = []
    for raw in raw_routes:
        cum = cumulative_miles(raw.coords)
        samples = sample_along(raw.coords, cum, req.interval_miles)
        prepared.append((raw, cum, samples))

    longest_trip = max(r.duration_hours for r in raw_routes)
    start, end = forecast_window(req.departure, longest_trip, HEATMAP_HOURS)

    # Routes share many stretches, and the forecast has no finer resolution than
    # the grid anyway: look each cell up once, in a single batch.
    cells = sorted({grid_cell((s.lat, s.lon)) for _, _, samples in prepared for s in samples})
    by_cell = dict(zip(cells, weather_provider.fetch(cells, start, end)))

    routes_out = []
    metrics = []
    for route_id, (raw, cum, samples) in enumerate(prepared):
        series = [by_cell[grid_cell((s.lat, s.lon))] for s in samples]

        total_miles = cum[-1]
        owned = segment_miles([s.mile for s in samples])
        miles_by_level = {name: 0.0 for name in risk.LEVEL_NAMES.values()}
        weighted_risk = 0.0
        checkpoints = []

        for idx, (sample, hourly, seg) in enumerate(zip(samples, series, owned)):
            fraction = sample.mile / total_miles if total_miles else 0.0
            eta = req.departure + timedelta(hours=raw.duration_hours * fraction)
            wind, rain, snow = hourly.at(eta)
            result = risk.assess(wind, rain, snow, req.load_lbs)

            miles_by_level[result.name] += seg
            weighted_risk += result.level * seg

            # Heatmap data: this spot's risk level for each hour after departure.
            hourly_levels = [
                risk.assess(*hourly.at(req.departure + timedelta(hours=h)), req.load_lbs).level
                for h in range(HEATMAP_HOURS + 1)
            ]

            checkpoints.append(
                {
                    "index": idx,
                    "mile": round(sample.mile, 1),
                    "lat": round(sample.lat, 5),
                    "lon": round(sample.lon, 5),
                    "eta": eta.isoformat(),
                    "weather": {
                        "wind_mph": round(wind, 1),
                        "rain_in_hr": round(rain, 3),
                        "snow_in_hr": round(snow, 3),
                    },
                    "risk": result.name,
                    "risk_level": result.level,
                    "reasons": result.reasons,
                    "hourly_risk": hourly_levels,
                }
            )

        avg_risk = weighted_risk / total_miles if total_miles else 0.0
        metrics.append(
            RouteMetrics(
                route_id=route_id,
                no_travel_miles=miles_by_level["no_travel"],
                severe_miles=miles_by_level["severe"],
                high_miles=miles_by_level["high"],
                avg_risk=avg_risk,
                duration_hours=raw.duration_hours,
            )
        )
        routes_out.append(
            {
                "id": route_id,
                "geometry": [[round(la, 5), round(lo, 5)] for la, lo in decimate(raw.coords, MAX_GEOMETRY_POINTS)],
                "checkpoints": checkpoints,
                "summary": {
                    "distance_miles": round(raw.distance_miles, 1),
                    "duration_hours": round(raw.duration_hours, 2),
                    "arrival": (req.departure + timedelta(hours=raw.duration_hours)).isoformat(),
                    "miles_by_risk": {k: round(v, 1) for k, v in miles_by_level.items()},
                    "avg_risk": round(avg_risk, 2),
                    "worst_risk": max((c["risk"] for c in checkpoints), key=lambda n: _level_of(n)),
                    "has_no_travel": miles_by_level["no_travel"] > 0,
                },
            }
        )

    ranked = rank(metrics)
    best = ranked[0]
    for position, m in enumerate(ranked, start=1):
        routes_out[m.route_id]["summary"]["rank"] = position
        routes_out[m.route_id]["summary"]["recommended"] = m.route_id == best.route_id

    return {
        "request": {
            "origin": list(req.origin),
            "destination": list(req.destination),
            "departure": req.departure.isoformat(),
            "load_lbs": req.load_lbs,
            "interval_miles": req.interval_miles,
        },
        "routes": routes_out,
        "recommendation": {
            "route_id": best.route_id,
            "reasons": explain(best, [m for m in ranked if m.route_id != best.route_id]),
        },
        "heatmap_hours": HEATMAP_HOURS,
    }


def _level_of(name: str) -> int:
    return {v: k for k, v in risk.LEVEL_NAMES.items()}[name]
