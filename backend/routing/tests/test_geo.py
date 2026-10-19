import pytest

from routing.geo import cumulative_miles, decimate, grid_cell, haversine_miles, sample_along, segment_miles

# Roughly a straight line along the equator: 1 degree of longitude ~ 69.17 miles.
LINE = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]


def test_haversine_one_degree_at_equator():
    assert haversine_miles((0, 0), (0, 1)) == pytest.approx(69.17, abs=0.1)


def test_cumulative_miles_starts_at_zero_and_grows():
    cum = cumulative_miles(LINE)
    assert cum[0] == 0 and cum[1] < cum[2]
    assert cum[2] == pytest.approx(138.34, abs=0.2)


def test_sampling_includes_start_and_end():
    cum = cumulative_miles(LINE)
    samples = sample_along(LINE, cum, 50)
    assert samples[0].mile == 0
    assert samples[-1].mile == pytest.approx(cum[-1])
    assert [round(s.mile) for s in samples] == [0, 50, 100, 138]


def test_sampling_interpolates_between_vertices():
    cum = cumulative_miles(LINE)
    mid = sample_along(LINE, cum, 69.17)[1]
    assert mid.lon == pytest.approx(1.0, abs=0.01)


def test_sampling_rejects_bad_input():
    with pytest.raises(ValueError):
        sample_along([(0, 0)], [0.0], 10)
    with pytest.raises(ValueError):
        sample_along(LINE, cumulative_miles(LINE), 0)


def test_segment_miles_add_up_to_route_length():
    marks = [0, 25, 50, 75, 90]
    owned = segment_miles(marks)
    assert sum(owned) == pytest.approx(90)
    assert owned[0] == pytest.approx(12.5)       # start owns half of the first gap
    assert owned[-1] == pytest.approx(7.5)       # end owns half of the last gap


def test_segment_miles_single_point():
    assert segment_miles([0]) == [0.0]


def test_decimate_keeps_endpoints_and_limits_size():
    points = [(float(i), 0.0) for i in range(10_000)]
    out = decimate(points, 1_000)
    assert len(out) <= 1_001
    assert out[0] == points[0] and out[-1] == points[-1]
    assert decimate(points[:10], 1_000) == points[:10]


def test_grid_cell_snaps_to_tenth_of_a_degree():
    assert grid_cell((32.7767, -96.797)) == (32.8, -96.8)
    assert grid_cell((32.7499, -96.7501)) == (32.7, -96.8)


def test_grid_cell_groups_nearby_points_and_normalises_negative_zero():
    assert grid_cell((30.01, -100.04)) == grid_cell((30.04, -100.01))
    assert str(grid_cell((-0.02, 0.02))[0]) == "0.0"
