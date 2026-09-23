"""Two-way fixed-effects difference-in-differences: estimate, clustered SE, pairs bootstrap, power."""
from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd
import statsmodels.api as sm

TOL = 1e-10
MIN_VARIANCE = 1e-9


def _group_mean(v: np.ndarray, codes: np.ndarray, k: int) -> np.ndarray:
    cnt = np.bincount(codes, minlength=k)
    return np.bincount(codes, weights=v, minlength=k) / np.maximum(cnt, 1)


def demean(V: np.ndarray, hut: np.ndarray, date: np.ndarray, max_iter: int = 500) -> np.ndarray:
    """Removes hut and date means from each column by alternating projections (works on unbalanced panels)."""
    out = V.astype(float).copy()
    kh, kd = int(hut.max()) + 1, int(date.max()) + 1
    for j in range(out.shape[1]):
        v = out[:, j]
        for _ in range(max_iter):
            before = v
            v = v - _group_mean(v, hut, kh)[hut]
            v = v - _group_mean(v, date, kd)[date]
            if np.abs(v - before).max() < TOL:
                break
        out[:, j] = v
    return out


def _design(panel: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Columns [y, x, treat] and integer codes of hut and date."""
    return (panel[["y", "x", "treat"]].to_numpy(float),
            pd.factorize(panel.hut)[0], pd.factorize(panel.date)[0])


def _kept_regressors(D: np.ndarray) -> list[int]:
    """Column 1 (x) and column 2 (treat) of the demeaned matrix that still vary."""
    return [j for j in (1, 2) if D[:, j].std() > MIN_VARIANCE]


def _coef(V: np.ndarray, hut: np.ndarray, date: np.ndarray) -> float:
    D = demean(V, hut, date)
    keep = _kept_regressors(D)
    if 1 not in keep:
        return float("nan")
    beta = np.linalg.lstsq(D[:, keep], D[:, 0], rcond=None)[0]
    return float(beta[keep.index(1)])


def coef_only(panel: pd.DataFrame) -> float:
    """The interaction coefficient without standard errors; NaN when it is not identified."""
    if len(panel) == 0 or panel.x.sum() == 0:
        return float("nan")
    return _coef(*_design(panel))


def fit_did(panel: pd.DataFrame) -> dict:
    """OLS of y on x = tour*treat (and treat if not absorbed) with hut and date fixed effects.

    Standard errors are clustered by `cluster`; the fixed effects are removed by demeaning, so the
    degrees-of-freedom correction ignores them.
    """
    if len(panel) == 0 or panel.x.sum() == 0:
        return {"skipped": "no treated tour rows"}
    if panel.cluster.nunique() < 2:
        return {"skipped": "fewer than 2 clusters"}
    V, hut, date = _design(panel)
    D = demean(V, hut, date)
    keep = _kept_regressors(D)
    if 1 not in keep:
        return {"skipped": "interaction absorbed by fixed effects"}
    res = sm.OLS(D[:, 0], D[:, keep]).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(panel.cluster)[0]})
    i = keep.index(1)
    lo, hi = res.conf_int()[i]
    return {"coef": float(res.params[i]), "se": float(res.bse[i]), "lo": float(lo), "hi": float(hi),
            "p": float(res.pvalues[i]), "n": int(len(panel)), "n_clusters": int(panel.cluster.nunique()),
            "treated_tour_rows": int((panel.x == 1).sum())}


def cluster_bootstrap(panel: pd.DataFrame, n: int = 2000, seed: int = 0) -> dict:
    """Pairs cluster bootstrap: resample clusters with replacement, refit, take the 2.5% and 97.5% percentiles."""
    V, hut, date = _design(panel)
    groups = list(panel.reset_index(drop=True).groupby("cluster").indices.values())
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(n):
        pick = rng.integers(0, len(groups), len(groups))
        rows = np.concatenate([groups[i] for i in pick])
        c = _coef(V[rows], hut[rows], date[rows])
        if not np.isnan(c):
            draws.append(c)
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return {"lo": float(lo), "hi": float(hi), "se_boot": float(np.std(draws, ddof=1)), "n_draws": len(draws)}


def min_detectable_effect(panel: pd.DataFrame, alpha: float = 0.05, power: float = 0.8) -> dict:
    """Minimum detectable interaction effect from the regression residual variance and the demeaned interaction.

    The variance is that of the residual after fixed effects, x and treat are partialled out, so it does not
    depend on the size of the effect; no coefficient is reported. The standard error is the iid one, so it is a lower bound of the clustered one.
    """
    if len(panel) == 0 or panel.x.sum() == 0:
        return {"skipped": "no treated tour rows"}
    V, hut, date = _design(panel)
    D = demean(V, hut, date)
    x, t = D[:, 1], D[:, 2]
    if t.std() > MIN_VARIANCE:
        x = x - t * (t @ x) / (t @ t)
    ss = float(x @ x)
    if ss <= 0:
        return {"skipped": "interaction absorbed by fixed effects"}
    keep = _kept_regressors(D)
    beta = np.linalg.lstsq(D[:, keep], D[:, 0], rcond=None)[0]
    resid = D[:, 0] - D[:, keep] @ beta
    sigma2 = float(resid @ resid) / max(len(D) - len(keep) - 1, 1)
    z = NormalDist().inv_cdf(1 - alpha / 2) + NormalDist().inv_cdf(power)
    return {"mde": float(z * np.sqrt(sigma2 / ss)), "sigma": float(np.sqrt(sigma2)),
            "treated_tour_rows": int((panel.x == 1).sum())}
