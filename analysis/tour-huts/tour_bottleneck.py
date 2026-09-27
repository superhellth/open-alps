"""Bottleneck choice, treatment series, controls and the difference-in-differences panel."""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

import analyze
import hutdays
from bottleneck_tours import positions, stage_distance
from link_huts import haversine_km

MIN_TOUR_HUTS = 3
CAP_RATIO = 0.7
N_CONTROLS = 3
ELEV_TOL_M = 500
SIZE_TOL_SD = 1.0
MAX_M = 2
PLACEBO_LOG_CAP_TOL = 0.2
PANEL_COLUMNS = ["date", "y", "own_sold_out", "treat", "unit", "cluster", "tour_name", "hut", "tour", "x"]

Scheme = Callable[[pd.Series, int], pd.Series]


def hut_table(huts: list[dict], days: pd.DataFrame, season: int) -> pd.DataFrame:
    """Huts of one season kept by the first study's primary selection, with coordinates."""
    t = analyze.select(hutdays.season_table(huts, days[days.season == season], season), "primary")
    geo = pd.DataFrame(huts)[["ohrs_id", "lat", "lon"]]
    return t.merge(geo, on="ohrs_id").reset_index(drop=True)


def hut_day_index(days: pd.DataFrame, season: int) -> dict[int, pd.DataFrame]:
    """Per hut the season's days indexed by date."""
    cols = ["occupancy", "sold_out", "sold_out_near", "open"]
    return {int(i): g.set_index("date")[cols] for i, g in days[days.season == season].groupby("ohrs_id")}


def candidate_table(tours: list[dict], table: pd.DataFrame) -> pd.DataFrame:
    """Per tour the smallest-capacity eligible hut and whether it qualifies as a bottleneck."""
    cap = table.set_index("ohrs_id")
    rows = []
    for t in tours:
        ids = [o for o in dict.fromkeys(t["ohrs"]) if o is not None and o in cap.index]
        row = {"tour": t["name"], "n_huts": len(t["guids"]), "n_eligible": len(ids), "bottleneck": None,
               "capacity": None, "median_capacity": None, "ratio": None, "qualifies": False}
        if len(ids) >= MIN_TOUR_HUTS:
            c = cap.loc[ids].sort_values(["capacity", "sold_out_share"], ascending=[True, False])
            median = float(c.capacity.median())
            row.update(bottleneck=int(c.index[0]), capacity=float(c.capacity.iloc[0]),
                       median_capacity=median, ratio=float(c.capacity.iloc[0]) / median)
            row["qualifies"] = row["ratio"] <= CAP_RATIO
        rows.append(row)
    return pd.DataFrame(rows)


def bottleneck_ids(cand: pd.DataFrame) -> dict[str, int]:
    return {r.tour: int(r.bottleneck) for r in cand.itertuples() if r.qualifies}


def a_full_series(h: pd.DataFrame, col: str = "sold_out") -> pd.Series:
    """1.0 on open days where the hut is sold out, 0.0 on other open days, NaN on closed days."""
    return h[col].astype(float).where(h.open)


def shift_series(s: pd.Series, k: int) -> pd.Series:
    """Value at day d is the value of `s` at day d - k; NaN where that day is not in `s`."""
    return s.shift(freq=pd.Timedelta(days=k)).reindex(s.index)


def aligned_treatment(s: pd.Series, m: int) -> pd.Series:
    """1 if the bottleneck is sold out on day d - m or d + m; NaN unless it is open on both days."""
    return pd.Series(np.maximum(shift_series(s, m), shift_series(s, -m)), index=s.index)


def shuffle_within_weekday_month(s: pd.Series, rng: np.random.Generator) -> pd.Series:
    """Permutes the non-missing values among days of the same weekday and month."""
    out = s.copy()
    valid = s.dropna()
    for _, g in valid.groupby([valid.index.month, valid.index.dayofweek]):
        out.loc[g.index] = rng.permutation(g.to_numpy())
    return out


def pick_controls(b: pd.Series, pool: pd.DataFrame, log_cap_sd: float, k: int = N_CONTROLS,
                  cap_km: float | None = None) -> list[tuple[int, float]]:
    """The k nearest pool huts within the elevation and size tolerances of `b`, as (ohrs_id, km)."""
    if pool.empty:
        return []
    near_elev = (pool.elevation - b.elevation).abs() <= ELEV_TOL_M
    near_size = (np.log(pool.capacity) - np.log(b.capacity)).abs() / log_cap_sd <= SIZE_TOL_SD
    cand = pool[near_elev & near_size]
    ranked = sorted((haversine_km(b.lat, b.lon, r.lat, r.lon), int(r.ohrs_id)) for r in cand.itertuples())
    if cap_km is not None:
        ranked = [x for x in ranked if x[0] <= cap_km]
    return [(i, float(d)) for d, i in ranked[:k]]


def make_units(tour: dict, a_id: int, table: pd.DataFrame, a_series: pd.Series,
               cap_km: float | None = None, ref_id: int | None = None) -> tuple[list[dict], int]:
    """One unit per tour hut within MAX_M nights of the reference hut that has a control.

    `a_series` is the treatment series of hut `a_id`. `ref_id` (default `a_id`) is the hut whose place in
    the tour defines the stage distance and which is not itself a tour hut of the unit set. Returns the
    units and the number of tour huts dropped for lack of a control.
    """
    ref = a_id if ref_id is None else ref_id
    pos = positions(tour)
    if ref not in pos:
        return [], 0
    n = len(tour["guids"])
    by = table.set_index("ohrs_id", drop=False)
    pool = table[(table.tour == 0) & (table.ohrs_id != a_id)]
    sd = float(np.log(table.capacity).std(ddof=0))
    units, no_control = [], 0
    for b_id, i in pos.items():
        if b_id == ref or b_id not in by.index:
            continue
        m = stage_distance(pos[ref], i, n, tour["circular"])
        if m < 1 or m > MAX_M:
            continue
        controls = pick_controls(by.loc[b_id], pool, sd, cap_km=cap_km)
        if not controls:
            no_control += 1
            continue
        units.append({"tour": tour["name"], "a": a_id, "b": int(b_id), "m": m,
                      "controls": controls, "a_series": a_series})
    return units, no_control


def tour_units(tours: list[dict], bottlenecks: dict[str, int], table: pd.DataFrame,
               hut_days: dict[int, pd.DataFrame], col: str = "sold_out",
               cap_km: float | None = None) -> tuple[list[dict], dict]:
    """Units of every tour with a bottleneck; a tour whose bottleneck is not in this season's table is skipped."""
    units: list[dict] = []
    info = {"no_control": 0, "skipped_tours": []}
    in_table = set(table.ohrs_id)
    for t in tours:
        a = bottlenecks.get(t["name"])
        if a is None:
            continue
        if a not in hut_days or a not in in_table:
            info["skipped_tours"].append(t["name"])
            continue
        u, none = make_units(t, a, table, a_full_series(hut_days[a], col), cap_km)
        units += u
        info["no_control"] += none
    return units, info


def build_panel(units: list[dict], hut_days: dict[int, pd.DataFrame], scheme: Scheme) -> pd.DataFrame:
    """One row per unit, hut and open day with a defined treatment; x = tour * treat."""
    frames = []
    for uid, u in enumerate(units):
        treat = scheme(u["a_series"], u["m"])
        for hut, is_tour in [(u["b"], 1)] + [(c, 0) for c, _ in u["controls"]]:
            h = hut_days[hut]
            f = pd.DataFrame({"y": h.occupancy, "own_sold_out": h.sold_out.astype(bool),
                              "treat": treat.reindex(h.index)}).dropna(subset=["y", "treat"])
            f = f.assign(unit=uid, cluster=u["b"], tour_name=u["tour"], hut=hut, tour=is_tour)
            frames.append(f.rename_axis("date").reset_index())
    if not frames:
        return pd.DataFrame(columns=PANEL_COLUMNS)
    panel = pd.concat(frames, ignore_index=True)
    panel["x"] = panel.tour * panel.treat
    return panel[PANEL_COLUMNS]


def pick_placebo_a(a_id: int, table: pd.DataFrame) -> int | None:
    """Non-tour hut of nearly the same capacity as `a_id`, the nearest one; None if there is none."""
    a = table.set_index("ohrs_id", drop=False).loc[a_id]
    pool = table[table.tour == 0]
    pool = pool[(np.log(pool.capacity) - np.log(a.capacity)).abs() <= PLACEBO_LOG_CAP_TOL]
    if pool.empty:
        return None
    km = [haversine_km(a.lat, a.lon, r.lat, r.lon) for r in pool.itertuples()]
    return int(pool.ohrs_id.iloc[int(np.argmin(km))])


def controls_km(units: list[dict]) -> dict:
    """Distances of all chosen controls."""
    d = [km for u in units for _, km in u["controls"]]
    if not d:
        return {"n": 0, "median": None, "max": None}
    return {"n": len(d), "median": float(np.median(d)), "max": float(max(d))}
