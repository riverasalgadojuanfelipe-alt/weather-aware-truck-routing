import pytest

from routing import risk
from routing.risk import HIGH, LOW, MODERATE, NO_TRAVEL, SEVERE


@pytest.mark.parametrize(
    "mph, expected",
    [(0, LOW), (24.9, LOW), (25, MODERATE), (34.9, MODERATE), (35, HIGH), (44.9, HIGH), (45, SEVERE), (54.9, SEVERE), (55, NO_TRAVEL), (80, NO_TRAVEL)],
)
def test_wind_thresholds(mph, expected):
    assert risk.classify_wind(mph) == expected


@pytest.mark.parametrize(
    "rain, expected",
    [(0, LOW), (0.09, LOW), (0.10, MODERATE), (0.24, MODERATE), (0.25, HIGH), (0.49, HIGH), (0.50, SEVERE), (1.00, SEVERE), (1.01, NO_TRAVEL)],
)
def test_rain_thresholds(rain, expected):
    assert risk.classify_rain(rain) == expected


@pytest.mark.parametrize(
    "snow, expected",
    [(0, LOW), (0.4, LOW), (0.5, MODERATE), (0.99, MODERATE), (1.0, HIGH), (1.99, HIGH), (2.0, SEVERE), (3.0, SEVERE), (3.01, NO_TRAVEL)],
)
def test_snow_thresholds(snow, expected):
    assert risk.classify_snow(snow) == expected


def test_55_mph_is_no_travel_for_any_load():
    assert risk.load_adjusted_wind_level(55, 0) == NO_TRAVEL
    assert risk.load_adjusted_wind_level(70, 1_000) == NO_TRAVEL


def test_heavy_load_in_45_to_54_mph_is_no_travel():
    assert risk.load_adjusted_wind_level(45, 30_001) == NO_TRAVEL
    assert risk.load_adjusted_wind_level(54, 60_000) == NO_TRAVEL


def test_load_at_exactly_30000_is_not_heavy():
    # "> 30,000 lb": 30,000 itself does not trigger the rule.
    assert risk.load_adjusted_wind_level(50, 30_000) == SEVERE


def test_medium_wind_with_very_heavy_load_is_severe():
    assert risk.load_adjusted_wind_level(35, 40_001) == SEVERE
    assert risk.load_adjusted_wind_level(44, 80_000) == SEVERE


def test_medium_wind_with_load_at_exactly_40000_stays_high():
    assert risk.load_adjusted_wind_level(40, 40_000) == HIGH


def test_load_rules_never_lower_the_level():
    assert risk.load_adjusted_wind_level(10, 100_000) == LOW
    assert risk.load_adjusted_wind_level(30, 100_000) == MODERATE


def test_overall_risk_is_the_worst_condition():
    result = risk.assess(wind_mph=20, rain_in_hr=0.6, snow_in_hr=0.0, load_lbs=20_000)
    assert result.level == SEVERE
    assert result.rain_level == SEVERE and result.wind_level == LOW
    assert any("rain" in r for r in result.reasons)


def test_load_rule_shows_up_in_reasons():
    result = risk.assess(wind_mph=40, rain_in_hr=0, snow_in_hr=0, load_lbs=45_000)
    assert result.level == SEVERE
    assert any("load rule applied" in r for r in result.reasons)


def test_calm_weather_is_low_with_no_reasons():
    result = risk.assess(5, 0, 0, 40_000)
    assert result.level == LOW and result.reasons == [] and result.name == "low"
