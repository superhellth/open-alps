import bottleneck_tours as bt


def huts():
    return [{"ohrs_id": 1, "guids": ["{A}"]}, {"ohrs_id": 2, "guids": ["{B}", "{B2}"]},
            {"ohrs_id": 3, "guids": ["{C}"]}]


def test_load_tours_maps_guids_and_keeps_gap_for_unmapped_hut():
    raw = [{"name": "T", "guids": ["{A}", "{X}", "{B2}", "{C}"], "circular": False},
           {"name": "empty", "guids": [], "circular": False}]
    tours = bt.load_tours(raw, huts())
    assert len(tours) == 1
    assert tours[0]["ohrs"] == [1, None, 2, 3]
    assert bt.positions(tours[0]) == {1: 0, 2: 2, 3: 3}


def test_stage_distance_counts_gap_and_circular_takes_short_way():
    assert bt.stage_distance(0, 3, 4, False) == 3
    assert bt.stage_distance(0, 3, 4, True) == 1
    assert bt.stage_distance(1, 4, 6, True) == 3


def test_order_agreement_same_reversed_disagree_and_membership():
    p = ["{A}", "{B}", "{C}"]
    assert bt.order_agreement(["{A}", "{B}", "{C}"], p)["verdict"] == "same"
    assert bt.order_agreement(["{C}", "{B}", "{A}"], p)["verdict"] == "reversed"
    assert bt.order_agreement(["{B}", "{A}", "{C}"], p)["verdict"] == "disagree"
    r = bt.order_agreement(["{A}", "{X}", "{B}", "{C}"], p)
    assert r["verdict"] == "same" and r["api_only"] == ["{X}"] and r["pipeline_only"] == []
    assert bt.order_agreement(["{A}", "{B}"], p)["verdict"] == "too_few_shared"


def test_validate_orders_matches_names_and_gates():
    hut_ids = ["{A}", "{B}", "{C}"]
    leg = lambda a, b: {"from": {"type": "hut", "id": a}, "to": {"type": "hut", "id": b}}
    pipe = [{"name": "Tauernhöhenweg", "legs": [leg(0, 1), leg(1, 2)]},
            {"name": "Ghost", "legs": [leg(0, 1)]}]
    tours = [{"name": "Tauern Höhenweg 8 Tage", "guids": ["{A}", "{B}", "{C}"], "ohrs": [], "circular": False}]
    rows = bt.validate_orders(tours, pipe, hut_ids)
    assert rows[0]["verdict"] == "same" and rows[0]["api"] == "Tauern Höhenweg 8 Tage"
    assert rows[1]["verdict"] == "no_api_match"
    assert not bt.orders_validated(rows)
    assert bt.orders_validated(rows[:1])
    assert bt.pipeline_sequence(pipe[0], hut_ids) == ["{A}", "{B}", "{C}"]
