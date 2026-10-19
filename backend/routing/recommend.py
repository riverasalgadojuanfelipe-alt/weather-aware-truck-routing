"""Route ranking.

Order of preference (from the spec), applied lexicographically:

0. no-travel miles  - a route that crosses "No Travel" weather can never beat
                      one that does not (No Travel is worse than Severe).
1. fewest Severe miles
2. fewest High miles
3. lowest average risk (0 = low ... 4 = no travel, weighted by miles)
4. shortest travel time

Values are rounded before comparing (0.1 mile, 0.01 risk point, 1 minute) so
floating point noise does not decide a winner.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RouteMetrics:
    route_id: int
    no_travel_miles: float
    severe_miles: float
    high_miles: float
    avg_risk: float
    duration_hours: float


def sort_key(m: RouteMetrics) -> tuple:
    return (
        round(m.no_travel_miles, 1),
        round(m.severe_miles, 1),
        round(m.high_miles, 1),
        round(m.avg_risk, 2),
        round(m.duration_hours * 60),
    )


def rank(routes: list[RouteMetrics]) -> list[RouteMetrics]:
    return sorted(routes, key=sort_key)


def explain(best: RouteMetrics, others: list[RouteMetrics]) -> list[str]:
    """Plain-English reasons why `best` won, for the UI."""
    if not others:
        return ["Only one route was available."]

    reasons = []
    if best.no_travel_miles > 0:
        reasons.append(
            f"All routes cross No Travel weather; this one has the least ({best.no_travel_miles:.0f} mi). "
            "Consider delaying departure."
        )
        return reasons

    runner_up = rank(others)[0]
    keys = [
        ("no_travel_miles", "No Travel miles"),
        ("severe_miles", "Severe miles"),
        ("high_miles", "High-risk miles"),
    ]
    for attr, label in keys:
        mine, theirs = getattr(best, attr), getattr(runner_up, attr)
        if round(mine, 1) < round(theirs, 1):
            reasons.append(f"Fewest {label}: {mine:.0f} mi vs {theirs:.0f} mi on the next best route.")
            return reasons
    if round(best.avg_risk, 2) < round(runner_up.avg_risk, 2):
        reasons.append(
            f"Same Severe/High miles as the next best route, but lower average risk "
            f"({best.avg_risk:.2f} vs {runner_up.avg_risk:.2f})."
        )
    else:
        diff = (runner_up.duration_hours - best.duration_hours) * 60
        reasons.append(f"Weather risk is tied with the next best route; this one is {diff:.0f} min faster.")
    return reasons
