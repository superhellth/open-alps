import numpy as np
import pandas as pd

import bottleneck_steps as bs
import tour_bottleneck as tb


def mini_world(effect=-0.2, n_days=150, seed=0):
    """One tour of huts 1..4 (A = 1, small); B occupancy falls by `effect` on days A is sold out (same day)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-05-01", periods=n_days)
    a_out = rng.random(n_days) < 0.3
    days = {}
    for i in (1, 2, 3, 4, 11, 12, 13, 14, 15, 16):
        y = 0.5 + rng.normal(0, 0.05, n_days) + (effect * a_out if i in (2, 3) else 0)
        days[i] = pd.DataFrame({"occupancy": y, "sold_out": (a_out if i == 1 else np.zeros(n_days, bool)),
                                "sold_out_near": False, "open": True}, index=idx)
    rows = [(1, 1, 2000, 30, 0.0), (2, 1, 2000, 90, 0.01), (3, 1, 2000, 90, 0.02), (4, 1, 2000, 90, 0.03),
            (11, 0, 2000, 90, 0.011), (12, 0, 2000, 80, 0.012), (13, 0, 2000, 100, 0.013),
            (14, 0, 2000, 90, 0.014), (15, 0, 2000, 85, 0.015), (16, 0, 2000, 95, 0.016)]
    table = pd.DataFrame([{"ohrs_id": i, "tour": f, "elevation": e, "capacity": c, "lat": 47 + d, "lon": 11.0,
                           "sold_out_share": 0.1} for i, f, e, c, d in rows])
    tour = {"name": "t", "circular": False, "guids": ["{1}", "{2}", "{3}", "{4}"], "ohrs": [1, 2, 3, 4]}
    units, _ = tb.make_units(tour, 1, table, tb.a_full_series(days[1]))
    return tour, table, days, units


def test_offset_profile_peaks_at_zero_for_same_day_effect():
    _, _, days, units = mini_world()
    prof = bs.offset_profile(units, days)
    assert sorted(prof) == list(range(-3, 4))
    assert prof[0]["coef"] < -0.15
    assert all(abs(prof[k]["coef"]) < 0.06 for k in prof if k != 0)


def test_primary_test_reports_power_before_effect_and_bootstrap_when_asked():
    _, _, days, units = mini_world()
    r = bs.primary_test(units, days, scheme=lambda s, m: tb.shift_series(s, 0), n_boot=100, seed=1)
    assert list(r)[:2] == ["n_units", "power"]
    assert r["did"]["coef"] < -0.15 and r["bootstrap"]["lo"] < r["did"]["coef"] < r["bootstrap"]["hi"]
    assert "bootstrap" not in bs.primary_test(units, days)


def test_per_tour_and_effect_by_a_and_placebo_dates():
    tour, table, days, units = mini_world()
    assert list(bs.per_tour(units, days)) == ["t"]
    eff = bs.effect_by_a(tour, table, days)
    assert 1 in eff and len(eff) >= 1
    pl = bs.placebo_dates(units, days, n=20, seed=2)
    assert pl["n"] == 20 and 0 <= pl["p_two_sided"] <= 1


def test_rank_test_all_hits_and_no_hits():
    effects = {f"t{i}": {1: -0.3, 2: -0.1, 3: 0.0} for i in range(12)}
    hit = bs.rank_test(effects, {f"t{i}": 1 for i in range(12)}, n_sim=2000, seed=0)
    assert hit["observed_share"] == 1.0 and hit["p_value"] < 0.001
    assert abs(hit["chance_share"] - 1 / 3) < 1e-9
    miss = bs.rank_test(effects, {f"t{i}": 3 for i in range(12)}, n_sim=2000, seed=0)
    assert miss["observed_share"] == 0.0 and miss["p_value"] > 0.99
    assert "skipped" in bs.rank_test({"t": {1: 0.0}}, {"t": 1})
