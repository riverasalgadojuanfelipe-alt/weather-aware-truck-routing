"""Weather risk rules.

This module is intentionally pure (no I/O) so the rules can be unit tested
and explained line by line.

Levels, from best to worst::

    LOW(0) < MODERATE(1) < HIGH(2) < SEVERE(3) < NO_TRAVEL(4)

Boundary convention
-------------------
The spec lists ranges such as "0.10-0.25" and "0.25-0.50" that share an
endpoint. We resolve every shared endpoint **towards the more dangerous
level**: a value exactly equal to a lower bound belongs to that level.
For example 25 mph is MODERATE, 0.25 in/hr of rain is HIGH.

The two "No Travel" thresholds that are written with ">" (rain and snow)
are strict, so exactly 1.00 in/hr of rain is still SEVERE and exactly
3.0 in/hr of snow is still SEVERE. Wind uses ">= 55" as written.
"""

from __future__ import annotations

from dataclasses import dataclass, field

LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = 0, 1, 2, 3, 4

LEVEL_NAMES = {
    LOW: "low",
    MODERATE: "moderate",
    HIGH: "high",
    SEVERE: "severe",
    NO_TRAVEL: "no_travel",
}

# (threshold, level, strict). A value reaches `level` when value >= threshold,
# or value > threshold when `strict` is True. Listed from worst to best.
WIND_MPH_RULES = [(55, NO_TRAVEL, False), (45, SEVERE, False), (35, HIGH, False), (25, MODERATE, False)]
RAIN_IN_HR_RULES = [(1.00, NO_TRAVEL, True), (0.50, SEVERE, False), (0.25, HIGH, False), (0.10, MODERATE, False)]
SNOW_IN_HR_RULES = [(3.0, NO_TRAVEL, True), (2.0, SEVERE, False), (1.0, HIGH, False), (0.5, MODERATE, False)]

# Load rules (pounds).
WIND_NO_TRAVEL_MPH = 55          # any load
HEAVY_WIND_MIN_MPH = 45          # 45-54 mph ...
HEAVY_WIND_LOAD_LBS = 30_000     # ... and load > 30,000 lb  -> NO_TRAVEL
MEDIUM_WIND_MIN_MPH = 35         # 35-44 mph ...
MEDIUM_WIND_LOAD_LBS = 40_000    # ... and load > 40,000 lb  -> SEVERE


def _classify(value: float, rules: list[tuple[float, int, bool]]) -> int:
    for threshold, level, strict in rules:
        if (value > threshold) if strict else (value >= threshold):
            return level
    return LOW


def classify_wind(mph: float) -> int:
    return _classify(mph, WIND_MPH_RULES)


def classify_rain(inches_per_hour: float) -> int:
    return _classify(inches_per_hour, RAIN_IN_HR_RULES)


def classify_snow(inches_per_hour: float) -> int:
    return _classify(inches_per_hour, SNOW_IN_HR_RULES)


def load_adjusted_wind_level(mph: float, load_lbs: float) -> int:
    """Wind level after applying the load rules (never lower than plain wind)."""
    level = classify_wind(mph)
    if mph >= WIND_NO_TRAVEL_MPH:
        return NO_TRAVEL
    if HEAVY_WIND_MIN_MPH <= mph < WIND_NO_TRAVEL_MPH and load_lbs > HEAVY_WIND_LOAD_LBS:
        return NO_TRAVEL
    if MEDIUM_WIND_MIN_MPH <= mph < HEAVY_WIND_MIN_MPH and load_lbs > MEDIUM_WIND_LOAD_LBS:
        return max(level, SEVERE)
    return level


@dataclass(frozen=True)
class RiskResult:
    level: int
    wind_level: int
    rain_level: int
    snow_level: int
    # Human-readable reasons, e.g. "wind 40 mph with 45,000 lb load -> severe".
    reasons: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return LEVEL_NAMES[self.level]


def assess(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lbs: float) -> RiskResult:
    """Overall risk at one checkpoint = worst of wind (load-adjusted), rain, snow."""
    wind_level = load_adjusted_wind_level(wind_mph, load_lbs)
    rain_level = classify_rain(rain_in_hr)
    snow_level = classify_snow(snow_in_hr)
    level = max(wind_level, rain_level, snow_level)

    reasons: list[str] = []
    if wind_level > LOW:
        extra = " (load rule applied)" if wind_level != classify_wind(wind_mph) else ""
        reasons.append(f"wind {wind_mph:.0f} mph -> {LEVEL_NAMES[wind_level]}{extra}")
    if rain_level > LOW:
        reasons.append(f"rain {rain_in_hr:.2f} in/hr -> {LEVEL_NAMES[rain_level]}")
    if snow_level > LOW:
        reasons.append(f"snow {snow_in_hr:.2f} in/hr -> {LEVEL_NAMES[snow_level]}")

    return RiskResult(level, wind_level, rain_level, snow_level, reasons)
