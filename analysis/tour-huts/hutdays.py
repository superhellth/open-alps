"""Per-day and per-hut-season booking metrics from OHRS availability calendars."""
from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd

MIN_OPEN_DAYS = 14
SOLD_OUT_NEAR = 0.05

CUTS = {
    "season": None,
    "jul_aug": lambda d: d.map(lambda x: x.month in (7, 8)).astype(bool),
    "fri_sun": lambda d: d.map(lambda x: x.weekday() >= 4).astype(bool),
}

DAY_COLUMNS = ["ohrs_id", "date", "status", "open", "free_place", "capacity",
               "free_above_capacity", "occupancy", "sold_out", "sold_out_near"]


def hut_days(rows: list[dict], capacity: int, ohrs_id: int, start: date, end: date) -> pd.DataFrame:
    """One row per calendar day in [start, end]; occupancy is NaN on closed days."""
    recs = []
    for r in rows:
        d = datetime.strptime(r["date"], "%d.%m.%Y").date()
        if start <= d <= end:
            recs.append({"ohrs_id": ohrs_id, "date": d, "status": r["hutStatus"],
                         "open": r["hutStatus"] == "SERVICED", "free_place": r["freePlace"],
                         "capacity": capacity})
    df = pd.DataFrame(recs, columns=["ohrs_id", "date", "status", "open", "free_place", "capacity"])
    free = df.free_place.clip(lower=0, upper=capacity)
    df["free_above_capacity"] = df.free_place > capacity
    df["occupancy"] = ((capacity - free) / capacity).where(df.open, np.nan)
    df["sold_out"] = df.free_place <= 0
    df["sold_out_near"] = df.free_place <= SOLD_OUT_NEAR * capacity
    return df[DAY_COLUMNS]


def hut_season(days: pd.DataFrame, cut: str = "season") -> dict:
    """Season-level scalars of one hut; eligibility/flags use the full season, outcomes only the cut."""
    op = days[days.open]
    mask = CUTS[cut]
    sub = op if mask is None else op[mask(op.date)]
    n = len(sub)
    constant = len(op) > 0 and op.free_place.nunique() == 1 and op.free_place.iloc[0] != 0
    so, sn = int(sub.sold_out.sum()), int(sub.sold_out_near.sum())
    return {
        "open_days": len(op), "eligible": len(op) >= MIN_OPEN_DAYS, "no_activity": bool(constant),
        "capacity_mismatch": bool(op.free_above_capacity.any()), "cut_open_days": n,
        "occupancy": float(sub.occupancy.mean()) if n else np.nan,
        "sold_out_days": so, "sold_out_share": so / n if n else np.nan,
        "sold_out_near_days": sn, "sold_out_near_share": sn / n if n else np.nan,
    }


def season_table(huts: list[dict], days: pd.DataFrame, season: int, cut: str = "season") -> pd.DataFrame:
    """One row per non-excluded hut for one season and cut."""
    by_hut = {i: g for i, g in days.groupby("ohrs_id")}
    rows = []
    for h in huts:
        if h["error"] or h["ohrs_id"] not in by_hut:
            continue
        rows.append({"ohrs_id": h["ohrs_id"], "season": season, "tour": int(h["on_tour"]),
                     "elevation": h["elevation"], "capacity": h["capacity"],
                     "operator": h["operator"], "region": h["region"],
                     "approach_time_min": h["approach_time_min"],
                     **hut_season(by_hut[h["ohrs_id"]], cut)})
    return pd.DataFrame(rows)
