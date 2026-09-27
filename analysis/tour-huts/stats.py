"""Statistical routines for the tour-huts study: bootstrap, regression, matching, power."""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats as sps

COVARIATES = "tour + elevation + np.log(capacity) + C(operator) + C(region) + approach_time_min + open_days"
_MODEL_COLUMNS = ["tour", "elevation", "capacity", "operator", "region", "approach_time_min", "open_days"]


def bootstrap_diff(a, b, n=5000, seed=0) -> dict:
    a, b = np.asarray(a, float), np.asarray(b, float)
    rng = np.random.default_rng(seed)
    d = [rng.choice(a, len(a)).mean() - rng.choice(b, len(b)).mean() for _ in range(n)]
    lo, hi = np.percentile(d, [2.5, 97.5])
    return {"diff": float(a.mean() - b.mean()), "lo": float(lo), "hi": float(hi)}


def bootstrap_mean(x, n=5000, seed=0) -> dict:
    x = np.asarray(x, float)
    rng = np.random.default_rng(seed)
    m = [rng.choice(x, len(x)).mean() for _ in range(n)]
    lo, hi = np.percentile(m, [2.5, 97.5])
    return {"mean": float(x.mean()), "lo": float(lo), "hi": float(hi)}


def min_detectable_diff(n1, n2, sd, alpha=0.05, power=0.8) -> float:
    z = sps.norm.ppf(1 - alpha / 2) + sps.norm.ppf(power)
    return float(z * sd * np.sqrt(1 / n1 + 1 / n2))


def _complete(df: pd.DataFrame, extra: list[str]) -> tuple[pd.DataFrame, int]:
    keep = df.dropna(subset=_MODEL_COLUMNS + extra)
    return keep, len(df) - len(keep)


def _coef(res, n, n_dropped) -> dict:
    ci = res.conf_int().loc["tour"]
    return {"coef": float(res.params["tour"]), "lo": float(ci[0]), "hi": float(ci[1]),
            "p": float(res.pvalues["tour"]), "n": int(n), "n_dropped": int(n_dropped)}


def fit_ols(df: pd.DataFrame, outcome: str) -> dict:
    d, dropped = _complete(df, [outcome])
    res = smf.ols(f"{outcome} ~ {COVARIATES}", d).fit(cov_type="HC3")
    return _coef(res, len(d), dropped)


def fit_glm(df: pd.DataFrame, success_col: str, trials_col: str = "cut_open_days") -> dict:
    d, dropped = _complete(df, [success_col, trials_col])
    d = d.assign(_fail=d[trials_col] - d[success_col])
    res = smf.glm(f"{success_col} + _fail ~ {COVARIATES}", d,
                  family=sm.families.Binomial()).fit(cov_type="HC1")
    out = _coef(res, len(d), dropped)
    out["odds_ratio"] = float(np.exp(out["coef"]))
    return out


def match_pairs(df: pd.DataFrame, outcome: str, k: int = 3) -> dict:
    """Each tour hut vs the mean of its k nearest non-tour huts of the same operator."""
    d = df.copy()
    d["_lcap"] = np.log(d.capacity)
    vars_ = ["elevation", "_lcap", "open_days"]
    z = (d[vars_] - d[vars_].mean()) / d[vars_].std(ddof=0).replace(0, 1.0)
    tours = d[d.tour == 1]
    rows, unmatched = [], 0
    for i, t in tours.iterrows():
        cand = d[(d.tour == 0) & (d.operator == t.operator)]
        cand = cand[z.loc[cand.index].notna().all(axis=1)]
        if z.loc[i].isna().any() or cand.empty:
            unmatched += 1
            continue
        dist = np.sqrt(((z.loc[cand.index] - z.loc[i]) ** 2).sum(axis=1))
        near = cand.loc[dist.nsmallest(k).index]
        rows.append({"ohrs_id": t.ohrs_id, "diff": float(t[outcome] - near[outcome].mean()),
                     "n_matches": len(near)})
    return {"n_tour": len(tours), "n_unmatched": unmatched,
            "paired": pd.DataFrame(rows, columns=["ohrs_id", "diff", "n_matches"])}


def replicated(r1: dict, r2: dict) -> bool:
    """Same coefficient sign and overlapping confidence intervals."""
    return bool(np.sign(r1["coef"]) == np.sign(r2["coef"])
                and max(r1["lo"], r2["lo"]) <= min(r1["hi"], r2["hi"]))
