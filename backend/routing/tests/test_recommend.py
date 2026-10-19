from routing.recommend import RouteMetrics, explain, rank


def m(route_id, no_travel=0.0, severe=0.0, high=0.0, avg=0.0, hours=10.0):
    return RouteMetrics(route_id, no_travel, severe, high, avg, hours)


def ids(routes):
    return [r.route_id for r in rank(routes)]


def test_fewest_severe_miles_wins_even_if_slower():
    assert ids([m(0, severe=30, hours=8), m(1, severe=10, hours=12)]) == [1, 0]


def test_high_miles_break_a_severe_tie():
    assert ids([m(0, high=40), m(1, high=15)]) == [1, 0]


def test_average_risk_breaks_a_high_tie():
    assert ids([m(0, avg=1.2), m(1, avg=0.8)]) == [1, 0]


def test_shortest_time_is_the_last_tiebreaker():
    assert ids([m(0, hours=9.5), m(1, hours=9.0)]) == [1, 0]


def test_no_travel_is_worse_than_any_severe():
    assert ids([m(0, no_travel=5, severe=0), m(1, severe=200)]) == [1, 0]


def test_tiny_float_noise_does_not_decide_the_winner():
    # 0.04 mi apart rounds to the same 0.1 mi bucket, so time decides.
    assert ids([m(0, severe=10.04, hours=9), m(1, severe=10.00, hours=10)]) == [0, 1]


def test_explain_names_the_deciding_factor():
    best, other = m(0, severe=0), m(1, severe=20)
    assert "Severe" in explain(best, [other])[0]


def test_explain_when_everything_is_tied_mentions_time():
    best, other = m(0, hours=9), m(1, hours=10)
    assert "faster" in explain(best, [other])[0]


def test_explain_warns_when_every_route_has_no_travel():
    best, other = m(0, no_travel=10), m(1, no_travel=20)
    assert "delay" in explain(best, [other])[0].lower()
