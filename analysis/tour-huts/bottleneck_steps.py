"""Analysis steps of the bottleneck study: primary test, offsets, per-tour effects, rank test, placebo dates."""
from __future__ import annotations

import numpy as np
import pandas as pd

import did
import tour_bottleneck as tb


def primary_test(units: list[dict], hut_days: dict[int, pd.DataFrame], scheme: tb.Scheme = tb.aligned_treatment,
                 n_boot: int = 0, seed: int = 0) -> dict:
    """Power first, then the DiD coefficient, then the bootstrap interval when `n_boot` > 0."""
    panel = tb.build_panel(units, hut_days, scheme)
    out = {"n_units": len(units), "power": did.min_detectable_effect(panel)}
    out["did"] = did.fit_did(panel)
    if n_boot and "coef" in out["did"]:
        out["bootstrap"] = did.cluster_bootstrap(panel, n_boot, seed)
    return out


def offset_profile(units: list[dict], hut_days: dict[int, pd.DataFrame], ks=range(-3, 4)) -> dict[int, dict]:
    """The DiD with the treatment A_full(d - k) for each signed offset k."""
    return {k: did.fit_did(tb.build_panel(units, hut_days, lambda s, m, k=k: tb.shift_series(s, k)))
            for k in ks}


def per_tour(units: list[dict], hut_days: dict[int, pd.DataFrame],
             scheme: tb.Scheme = tb.aligned_treatment) -> dict[str, dict]:
    """One DiD per tour."""
    return {name: did.fit_did(tb.build_panel([u for u in units if u["tour"] == name], hut_days, scheme))
            for name in sorted({u["tour"] for u in units})}


def effect_by_a(tour: dict, table: pd.DataFrame, hut_days: dict[int, pd.DataFrame],
                col: str = "sold_out") -> dict[int, float]:
    """The tour's DiD coefficient with each of its eligible huts in turn as the bottleneck."""
    in_table = set(table.ohrs_id)
    out = {}
    for a in dict.fromkeys(o for o in tour["ohrs"] if o is not None):
        if a not in hut_days or a not in in_table:
            continue
        units, _ = tb.make_units(tour, a, table, tb.a_full_series(hut_days[a], col))
        r = did.fit_did(tb.build_panel(units, hut_days, tb.aligned_treatment))
        if "coef" in r:
            out[a] = r["coef"]
    return out


def rank_test(effects: dict[str, dict[int, float]], chosen: dict[str, int],
              n_sim: int = 10000, seed: int = 0) -> dict:
    """Share of tours whose chosen bottleneck has the most negative effect of all its huts, against chance."""
    usable = {t: e for t, e in effects.items() if chosen.get(t) in e and len(e) >= 2}
    if not usable:
        return {"skipped": "no tour with two or more fitted bottleneck candidates"}
    hits = [min(e, key=e.get) == chosen[t] for t, e in usable.items()]
    p_chance = np.array([1 / len(e) for e in usable.values()])
    observed = float(np.mean(hits))
    sims = (np.random.default_rng(seed).random((n_sim, len(p_chance))) < p_chance).mean(axis=1)
    return {"n_tours": len(hits), "observed_share": observed, "chance_share": float(p_chance.mean()),
            "p_value": float((sims >= observed).mean())}


def placebo_dates(units: list[dict], hut_days: dict[int, pd.DataFrame], n: int = 200, seed: int = 0) -> dict:
    """Refits the DiD with each tour's A series shuffled within weekday and month."""
    rng = np.random.default_rng(seed)
    observed = did.coef_only(tb.build_panel(units, hut_days, tb.aligned_treatment))
    a_by_tour = {u["tour"]: u["a_series"] for u in units}
    draws = []
    for _ in range(n):
        shuffled = {t: tb.shuffle_within_weekday_month(s, rng) for t, s in a_by_tour.items()}
        c = did.coef_only(tb.build_panel([dict(u, a_series=shuffled[u["tour"]]) for u in units],
                                         hut_days, tb.aligned_treatment))
        if not np.isnan(c):
            draws.append(c)
    return {"n": n, "observed": observed, "perm_mean": float(np.mean(draws)), "perm_sd": float(np.std(draws, ddof=1)),
            "p_two_sided": float(np.mean(np.abs(draws) >= abs(observed)))}
