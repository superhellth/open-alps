import numpy as np
import pandas as pd

import analyze
from test_stats import synth


def test_select_variants():
    t = pd.DataFrame({"eligible": [True, True, True, False], "no_activity": [False, True, False, False],
                      "capacity_mismatch": [False, False, True, False]})
    assert list(analyze.select(t, "primary").index) == [0]
    assert list(analyze.select(t, "incl_no_activity").index) == [0, 1]
    assert list(analyze.select(t, "incl_mismatch").index) == [0, 2]


def test_run_spec_reports_mde_model_matched():
    df = synth().assign(ohrs_id=lambda d: range(len(d)))
    r = analyze.run_spec(df, "occupancy")
    assert r["n_tour"] + r["n_other"] == len(df)
    assert r["mde"] > 0 and abs(r["model"]["coef"] - 0.10) < 0.02
    assert r["raw"]["lo"] < r["raw"]["diff"] < r["raw"]["hi"]
    assert r["matched"]["n_tour"] > 0


def test_run_spec_glm_outcome():
    df = synth().assign(ohrs_id=lambda d: range(len(d)))
    assert "odds_ratio" in analyze.run_spec(df, "sold_out")["model"]


def test_run_spec_skips_tiny_group():
    df = synth(n=40).assign(ohrs_id=lambda d: range(40))
    df.loc[df.index[:], "tour"] = 0
    df.loc[df.index[:3], "tour"] = 1
    assert "skipped" in analyze.run_spec(df, "occupancy")


def old_file(free):
    day = {"day": "25.09.2026", "status": "RESERVATION_POSSIBLE",
           "bedCategoriesData": [{"totalFreePlaces": free[0]}, {"totalFreePlaces": free[1]}]}
    return {"huts": {"{A}": {"ohrsHutId": 7, "responses": [
        {"ok": True, "body": [{"hutsAvailability": [{"calendarDays": [day]}]}]}]}}}


def test_consistency_counts_days_off_by_more_than_one():
    new = pd.DataFrame({"ohrs_id": [7], "season": [2026], "date": [pd.Timestamp("2026-09-25").date()],
                        "open": [True], "free_place": [10]})
    same = analyze.consistency(new, old_file([4, 5]))
    assert same["days_compared"] == 1 and same["days_off_by_more_than_1"] == 0
    off = analyze.consistency(new, old_file([4, 3]))
    assert off["days_off_by_more_than_1"] == 1
