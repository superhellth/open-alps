import numpy as np
import pandas as pd

import stats


def synth(n=600, effect=0.10, seed=1):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "tour": rng.integers(0, 2, n),
        "elevation": rng.uniform(1200, 3000, n),
        "capacity": rng.integers(20, 200, n),
        "operator": rng.choice(["DAV", "OEAV", "other"], n),
        "region": rng.choice(["west", "central", "east"], n),
        "approach_time_min": rng.uniform(20, 240, n),
        "open_days": rng.integers(30, 180, n),
    })
    df["occupancy"] = (0.3 + effect * df.tour + rng.normal(0, 0.05, n)).clip(0, 1)
    df["cut_open_days"] = df.open_days
    p = 1 / (1 + np.exp(-(-1.0 + 1.0 * df.tour)))
    df["sold_out_days"] = rng.binomial(df.open_days, p)
    df["sold_out_share"] = df.sold_out_days / df.open_days
    return df


def test_min_detectable_diff_matches_spec_example():
    assert abs(stats.min_detectable_diff(70, 160, 0.2) - 0.082) < 0.002


def test_bootstrap_diff_ci_contains_true_difference():
    rng = np.random.default_rng(0)
    a, b = rng.normal(0.5, 0.1, 100), rng.normal(0.4, 0.1, 100)
    r = stats.bootstrap_diff(a, b)
    assert r["lo"] < 0.1 < r["hi"] and abs(r["diff"] - 0.1) < 0.03


def test_ols_recovers_tour_effect():
    r = stats.fit_ols(synth(), "occupancy")
    assert abs(r["coef"] - 0.10) < 0.01 and r["lo"] < 0.10 < r["hi"] and r["p"] < 0.001


def test_ols_drops_rows_with_missing_covariates():
    df = synth()
    df.loc[:9, "elevation"] = np.nan
    r = stats.fit_ols(df, "occupancy")
    assert r["n_dropped"] == 10 and r["n"] == len(df) - 10


def test_glm_recovers_log_odds_effect():
    r = stats.fit_glm(synth(), "sold_out_days")
    assert abs(r["coef"] - 1.0) < 0.1 and abs(r["odds_ratio"] - np.exp(r["coef"])) < 1e-9


def test_match_pairs_same_operator_nearest_and_unmatched():
    df = pd.DataFrame({
        "ohrs_id": [1, 2, 3, 4, 5],
        "tour": [1, 0, 0, 0, 1],
        "elevation": [2000, 2010, 2900, 2005, 2000],
        "capacity": [50, 50, 50, 50, 50],
        "open_days": [100] * 5,
        "operator": ["DAV", "DAV", "DAV", "OEAV", "other"],
        "occupancy": [0.8, 0.5, 0.1, 0.9, 0.7],
    })
    r = stats.match_pairs(df, "occupancy", k=1)
    assert r["n_tour"] == 2 and r["n_unmatched"] == 1  # hut 5 has no 'other' non-tour hut
    row = r["paired"].set_index("ohrs_id").loc[1]
    assert row["n_matches"] == 1 and abs(row["diff"] - 0.3) < 1e-9  # nearest is hut 2, not hut 4 (other operator)


def test_match_pairs_skips_tour_hut_with_missing_elevation():
    df = pd.DataFrame({"ohrs_id": [1, 2], "tour": [1, 0], "elevation": [np.nan, 2000],
                       "capacity": [50, 50], "open_days": [100, 100], "operator": ["DAV", "DAV"],
                       "occupancy": [0.5, 0.5]})
    assert stats.match_pairs(df, "occupancy")["n_unmatched"] == 1


def test_replicated_needs_same_sign_and_overlap():
    a = {"coef": 0.05, "lo": 0.0, "hi": 0.10}
    assert stats.replicated(a, {"coef": 0.03, "lo": -0.02, "hi": 0.08})
    assert not stats.replicated(a, {"coef": -0.03, "lo": -0.08, "hi": 0.02})
    assert not stats.replicated(a, {"coef": 0.30, "lo": 0.20, "hi": 0.40})
