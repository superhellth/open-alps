import numpy as np
import pandas as pd

import tour_bottleneck as tb


def tour(name, ids, circular=False):
    return {"name": name, "circular": circular, "guids": [f"{{{i}}}" for i in ids], "ohrs": list(ids)}


def table(caps, shares=None):
    ids = list(caps)
    return pd.DataFrame({"ohrs_id": ids, "capacity": [caps[i] for i in ids],
                         "sold_out_share": [(shares or {}).get(i, 0.1) for i in ids]})


def test_candidates_pick_smallest_apply_ratio_and_three_hut_rule():
    tours = [tour("small", [1, 2, 3, 4]), tour("flat", [5, 6, 7]), tour("few", [8, 9]),
             tour("tie", [10, 11, 12, 13])]
    t = table({1: 20, 2: 100, 3: 100, 4: 100, 5: 90, 6: 100, 7: 100, 8: 10, 9: 100,
               10: 20, 11: 20, 12: 100, 13: 100}, shares={10: 0.1, 11: 0.3})
    c = tb.candidate_table(tours, t).set_index("tour")
    assert c.loc["small", "bottleneck"] == 1 and c.loc["small", "qualifies"]
    assert abs(c.loc["small", "ratio"] - 0.2) < 1e-9
    assert not c.loc["flat", "qualifies"]
    assert not c.loc["few", "qualifies"] and c.loc["few", "n_eligible"] == 2
    assert c.loc["tie", "bottleneck"] == 11
    assert tb.bottleneck_ids(c.reset_index()) == {"small": 1, "tie": 11}


def test_candidates_ignore_huts_missing_from_table():
    c = tb.candidate_table([tour("t", [1, 2, 3, 4])], table({2: 50, 3: 50, 4: 50})).iloc[0]
    assert c.n_huts == 4 and c.n_eligible == 3


def daily(values, start="2025-06-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values)), dtype=float)


def test_a_full_masks_closed_days_that_report_sold_out():
    idx = pd.date_range("2025-06-01", periods=3)
    h = pd.DataFrame({"open": [True, False, True], "sold_out": [True, True, False],
                      "sold_out_near": [True, True, True]}, index=idx)
    s = tb.a_full_series(h)
    assert s.iloc[0] == 1.0 and np.isnan(s.iloc[1]) and s.iloc[2] == 0.0
    assert tb.a_full_series(h, "sold_out_near").iloc[2] == 1.0


def test_shift_series_both_signs():
    s = daily([0, 1, 0, 0, 1])
    assert tb.shift_series(s, 1).tolist()[1:] == [0, 1, 0, 0] and np.isnan(tb.shift_series(s, 1).iloc[0])
    assert tb.shift_series(s, -1).tolist()[:4] == [1, 0, 0, 1] and np.isnan(tb.shift_series(s, -1).iloc[4])
    assert tb.shift_series(s, 0).tolist() == s.tolist()


def test_aligned_treatment_is_either_direction_and_nan_at_edges_or_closed():
    s = daily([0, 1, 0, 0, 1])
    out = tb.aligned_treatment(s, 1)
    assert np.isnan(out.iloc[0]) and np.isnan(out.iloc[4])
    assert out.iloc[1:4].tolist() == [0, 1, 1]
    closed = daily([0, 1, np.nan, 0, 1])
    assert np.isnan(tb.aligned_treatment(closed, 1).iloc[1])


def test_shuffle_keeps_weekday_month_counts_and_nan_positions():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2025-05-01", periods=150)
    s = pd.Series((np.arange(150) % 3 == 0).astype(float), index=idx)
    s.iloc[[10, 50]] = np.nan
    out = tb.shuffle_within_weekday_month(s, rng)
    assert out.isna().tolist() == s.isna().tolist()
    for _, g in s.dropna().groupby([s.dropna().index.month, s.dropna().index.dayofweek]):
        assert sorted(out.loc[g.index]) == sorted(g)
    assert not out.equals(s)


def geo_table(rows):
    """rows: (ohrs_id, tour_flag, elevation, capacity, lat_offset_deg)"""
    return pd.DataFrame([{"ohrs_id": i, "tour": f, "elevation": e, "capacity": c, "lat": 47 + d, "lon": 11.0,
                          "sold_out_share": 0.1} for i, f, e, c, d in rows])


def test_pick_controls_applies_tolerances_orders_by_distance_and_caps_radius():
    pool = geo_table([(10, 0, 2100, 60, 0.01), (11, 0, 2800, 50, 0.005), (12, 0, 2000, 500, 0.005),
                      (13, 0, 2000, 50, 0.02), (14, 0, 1900, 55, 0.03), (15, 0, 2000, 50, 0.5),
                      (16, 0, np.nan, 50, 0.001)])
    b = geo_table([(1, 1, 2000, 50, 0.0)]).iloc[0]
    assert [i for i, _ in tb.pick_controls(b, pool, 0.5)] == [10, 13, 14]
    assert [i for i, _ in tb.pick_controls(b, pool, 0.5, k=2)] == [10, 13]
    assert [i for i, _ in tb.pick_controls(b, pool, 0.5, cap_km=2.5)] == [10, 13]
    no_elev = geo_table([(1, 1, np.nan, 50, 0.0)]).iloc[0]
    assert tb.pick_controls(no_elev, pool, 0.5) == []


def mini_table():
    return geo_table([(1, 1, 2000, 30, 0.0), (2, 1, 2000, 90, 0.01), (3, 1, 2000, 90, 0.02),
                      (4, 1, 2000, 90, 0.03), (5, 1, 2000, 90, 0.04),
                      (11, 0, 2000, 90, 0.011), (12, 0, 2000, 80, 0.012), (13, 0, 2000, 100, 0.013),
                      (14, 0, 2000, 30, 0.001)])


def test_make_units_stage_distance_max_m_circular_and_no_control():
    t = tour("t", [1, 2, 3, 4, 5])
    a = pd.Series(0.0, index=pd.date_range("2025-06-01", periods=5))
    units, none = tb.make_units(t, 1, mini_table(), a)
    assert {u["b"]: u["m"] for u in units} == {2: 1, 3: 2}
    assert none == 0 and all(len(u["controls"]) == 3 for u in units)
    circ = tour("c", [1, 2, 3, 4, 5], circular=True)
    units, _ = tb.make_units(circ, 1, mini_table(), a)
    assert {u["b"]: u["m"] for u in units} == {2: 1, 3: 2, 4: 2, 5: 1}
    lonely = mini_table()
    lonely.loc[lonely.ohrs_id == 2, "elevation"] = np.nan
    units, none = tb.make_units(t, 1, lonely, a)
    assert [u["b"] for u in units] == [3] and none == 1


def test_make_units_placebo_uses_reference_positions_and_excludes_placebo_from_controls():
    t = tour("t", [1, 2, 3])
    a = pd.Series(0.0, index=pd.date_range("2025-06-01", periods=5))
    units, _ = tb.make_units(t, 14, mini_table(), a, ref_id=1)
    assert {u["b"] for u in units} == {2, 3}
    assert all(14 not in [c for c, _ in u["controls"]] for u in units)
    assert tb.pick_placebo_a(1, mini_table()) == 14


def world_days(ids, n=6, open_=True):
    idx = pd.date_range("2025-06-01", periods=n)
    return {i: pd.DataFrame({"occupancy": 0.5, "sold_out": False, "sold_out_near": False, "open": open_},
                            index=idx) for i in ids}


def test_build_panel_shared_hut_gives_two_rows_per_day_one_cluster_and_drops_closed_a_days():
    hd = world_days([2, 11, 12, 13])
    idx = pd.date_range("2025-06-01", periods=6)
    a1 = pd.Series([0, 1, 0, 0, 1, 0.0], index=idx)
    a2 = pd.Series([1, 0, 0, 1, 0, 0.0], index=idx)
    u1 = {"tour": "t1", "a": 1, "b": 2, "m": 1, "controls": [(11, 1.0), (12, 2.0), (13, 3.0)], "a_series": a1}
    u2 = {"tour": "t2", "a": 9, "b": 2, "m": 1, "controls": [(11, 1.0), (12, 2.0), (13, 3.0)], "a_series": a2}
    p = tb.build_panel([u1, u2], hd, tb.aligned_treatment)
    assert list(p.columns) == tb.PANEL_COLUMNS
    b_rows = p[(p.hut == 2)]
    assert len(b_rows) == 2 * 4 and set(b_rows.cluster) == {2}
    assert set(b_rows.groupby("tour_name").size()) == {4}
    assert p[p.tour == 0].x.eq(0).all()
    closed = a1.copy()
    closed.iloc[2] = np.nan
    p2 = tb.build_panel([dict(u1, a_series=closed)], hd, tb.aligned_treatment)
    assert len(p2[p2.hut == 2]) < 4


def test_controls_km_summary():
    u = {"controls": [(1, 2.0), (2, 4.0)]}
    assert tb.controls_km([u]) == {"n": 2, "median": 3.0, "max": 4.0}
    assert tb.controls_km([]) == {"n": 0, "median": None, "max": None}
