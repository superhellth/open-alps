import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

import did


def synth(effect, n_units=30, n_days=60, noise=0.05, seed=1):
    rng = np.random.default_rng(seed)
    hut_fe = rng.normal(0.5, 0.15, 10 * n_units)
    date_fe = rng.normal(0, 0.1, n_days)
    rows = []
    for u in range(n_units):
        treat = (rng.random(n_days) < 0.25).astype(float)
        for hut, is_tour in [(u, 1)] + [(1000 + 3 * u + j, 0) for j in range(3)]:
            y = (hut_fe[hut % len(hut_fe)] + date_fe + effect * is_tour * treat + 0.1 * treat
                 + rng.normal(0, noise, n_days))
            rows.append(pd.DataFrame({"y": y, "x": is_tour * treat, "treat": treat, "hut": hut,
                                      "date": np.arange(n_days), "cluster": u, "tour": is_tour}))
    return pd.concat(rows, ignore_index=True)


def test_fit_did_recovers_effect_and_matches_dummy_regression():
    p = synth(-0.10, n_units=8, n_days=30)
    r = did.fit_did(p)
    assert abs(r["coef"] + 0.10) < 0.02 and r["lo"] < -0.10 < r["hi"] and r["n_clusters"] == 8
    ref = smf.ols("y ~ x + treat + C(hut) + C(date)", p).fit()
    assert abs(r["coef"] - ref.params["x"]) < 1e-6
    assert did.coef_only(p) == r["coef"] or abs(did.coef_only(p) - r["coef"]) < 1e-9


def test_fit_did_zero_effect_interval_contains_zero():
    r = did.fit_did(synth(0.0))
    assert r["lo"] < 0 < r["hi"]


def test_fit_did_returns_skipped_for_degenerate_panels():
    p = synth(-0.1, n_units=3, n_days=10)
    assert "skipped" in did.fit_did(p.iloc[0:0])
    assert "skipped" in did.fit_did(p.assign(x=0.0))
    assert "skipped" in did.fit_did(p[p.cluster == 0])
    assert np.isnan(did.coef_only(p.assign(x=0.0)))


def test_treat_main_effect_dropped_when_absorbed_by_date_effects():
    p = synth(-0.1, n_units=6, n_days=20)
    same = p.groupby("date").treat.transform("mean")
    p = p.assign(treat=same)
    assert "coef" in did.fit_did(p)


def test_cluster_bootstrap_interval_covers_effect_and_is_seeded():
    p = synth(-0.10, n_units=20, n_days=40)
    b = did.cluster_bootstrap(p, n=200, seed=3)
    assert b["lo"] < -0.10 < b["hi"] and b["n_draws"] > 150
    assert b == did.cluster_bootstrap(p, n=200, seed=3)


def test_min_detectable_effect_ignores_the_effect_and_scales_with_noise():
    lo_noise = did.min_detectable_effect(synth(0.0, noise=0.05))["mde"]
    with_effect = did.min_detectable_effect(synth(-0.3, noise=0.05))["mde"]
    hi_noise = did.min_detectable_effect(synth(0.0, noise=0.10))["mde"]
    assert 0.9 < with_effect / lo_noise < 1.1
    assert 1.6 < hi_noise / lo_noise < 2.4
    assert "skipped" in did.min_detectable_effect(synth(0.0).iloc[0:0])
