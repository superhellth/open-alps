"""Runs the tour-huts booking study analysis and writes results.json and plots."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime

import numpy as np
import pandas as pd

import common
import hutdays
import stats

OUTCOMES = {"occupancy": ("ols", None), "sold_out": ("glm", "sold_out_days"),
            "sold_out_near": ("glm", "sold_out_near_days")}
MIN_GROUP = 5


def share_col(outcome: str) -> str:
    return "occupancy" if outcome == "occupancy" else f"{outcome}_share"


def select(table: pd.DataFrame, variant: str) -> pd.DataFrame:
    keep = table.eligible.copy()
    if variant != "incl_no_activity":
        keep &= ~table.no_activity
    if variant != "incl_mismatch":
        keep &= ~table.capacity_mismatch
    return table[keep]


def run_spec(table: pd.DataFrame, outcome: str) -> dict:
    kind, success = OUTCOMES[outcome]
    col = share_col(outcome)
    t = table.dropna(subset=[col])
    a, b = t[t.tour == 1][col], t[t.tour == 0][col]
    if len(a) < MIN_GROUP or len(b) < MIN_GROUP:
        return {"skipped": f"group too small ({len(a)} tour / {len(b)} other)"}
    sd = float(t[col].std())
    out = {"n_tour": len(a), "n_other": len(b), "mean_tour": float(a.mean()),
           "mean_other": float(b.mean()), "sd": sd,
           "mde": stats.min_detectable_diff(len(a), len(b), sd)}
    out["raw"] = stats.bootstrap_diff(a, b)
    out["model"] = stats.fit_ols(t, col) if kind == "ols" else stats.fit_glm(t, success)
    m = stats.match_pairs(t, col)
    out["matched"] = {"n_tour": m["n_tour"], "n_unmatched": m["n_unmatched"],
                      **(stats.bootstrap_mean(m["paired"]["diff"]) if len(m["paired"])
                         else {"mean": None, "lo": None, "hi": None})}
    return out


def consistency(new_days: pd.DataFrame, old: dict) -> dict:
    """Compares new calendar free places with the older per-hut proxy totals for overlapping days."""
    compared = off = 0
    for h in old["huts"].values():
        mine = new_days[new_days.ohrs_id == int(h["ohrsHutId"])]
        by_date = {r.date: r.free_place for r in mine.itertuples() if r.open}
        for resp in h["responses"]:
            b = resp.get("body")
            if not (resp.get("ok") and isinstance(b, list) and b and "hutsAvailability" in b[0]):
                continue
            for c in b[0]["hutsAvailability"][0]["calendarDays"]:
                d = datetime.strptime(c["day"], "%d.%m.%Y").date()
                if d not in by_date or "bedCategoriesData" not in c:
                    continue
                old_free = sum(max(x["totalFreePlaces"], 0) for x in c["bedCategoriesData"])
                compared += 1
                off += abs(old_free - by_date[d]) > 1
    return {"days_compared": compared, "days_off_by_more_than_1": int(off)}


def _coverage(tables: dict[int, pd.DataFrame], days: pd.DataFrame) -> tuple[list, list]:
    cov, noact = [], []
    for season, t in tables.items():
        for tour, g in t.groupby("tour"):
            group = "tour" if tour else "other"
            open_days = int(g.open_days.sum())
            cov.append({"season": season, "group": group, "huts": len(g),
                        "eligible": int(g.eligible.sum()), "open_hut_days": open_days})
            e = g[g.eligible]
            noact.append({"season": season, "group": group, "eligible": len(e),
                          "no_activity": int(e.no_activity.sum()),
                          "share": float(e.no_activity.mean()) if len(e) else None,
                          "capacity_mismatch": int(e.capacity_mismatch.sum())})
    return cov, noact


def main(argv=None) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    huts_doc = common.read_json(common.OUT / "huts.json")
    huts = huts_doc["huts"]
    days = pd.read_csv(common.OUT / "hut-days.csv", parse_dates=["date"])
    days["date"] = days["date"].dt.date
    results: dict = {"specs": {}}
    tables = {s: hutdays.season_table(huts, days[days.season == s], s) for s in common.SEASONS}
    cov, noact = _coverage(tables, days)
    results.update(coverage=cov, no_activity_share=noact,
                   unmatched_tour_guids=huts_doc["unmatched_tour_guids"],
                   coord_flags=[{"ohrs_id": h["ohrs_id"], "names": h["names"], "km": h["coord_km"]}
                                for h in huts if h["coord_flag"]])
    results["excluded"] = {
        "tour": sum(1 for h in huts if h["error"] and h["on_tour"]),
        "other": sum(1 for h in huts if h["error"] and not h["on_tour"]),
        "reasons": dict(Counter((h["error"] or "").split(":")[0].split(" ")[0]
                                for h in huts if h["error"])),
        "hut_errors": [{"ohrs_id": h["ohrs_id"], "names": h["names"], "error": h["error"]}
                       for h in huts if h["error"]]}
    results["approach_missing"] = sum(1 for h in huts if not h["error"] and h["approach_time_min"] is None)
    results["regions"] = dict(Counter(h["region"] for h in huts if not h["error"]))

    def spec(season, cut, outcome, variant):
        t = tables[season] if cut == "season" else hutdays.season_table(
            huts, days[days.season == season], season, cut)
        r = run_spec(select(t, variant), outcome)
        results["specs"][f"{season}|{cut}|{outcome}|{variant}"] = r
        return r

    for season in common.SEASONS:
        for cut in hutdays.CUTS:
            for outcome in OUTCOMES:
                spec(season, cut, outcome, "primary")
    for variant in ("incl_no_activity", "incl_mismatch"):
        for outcome in ("occupancy", "sold_out"):
            spec(2025, "season", outcome, variant)
    results["primary"] = results["specs"]["2025|season|occupancy|primary"]
    results["replication"] = {}
    for outcome in OUTCOMES:
        a = results["specs"][f"2025|season|{outcome}|primary"]
        b = results["specs"][f"2026|season|{outcome}|primary"]
        results["replication"][outcome] = (
            None if "skipped" in a or "skipped" in b else bool(stats.replicated(a["model"], b["model"])))

    old_path = common.ROOT / "data" / "analysis" / "hut-availability-raw.json"
    if old_path.exists():
        frames = []
        for h in huts:
            p = common.OUT / "raw" / "calendar-2026" / f"{h['ohrs_id']}.json"
            if h["error"] or not p.exists():
                continue
            frames.append(hutdays.hut_days(common.read_json(p)["body"], h["capacity"], h["ohrs_id"],
                                           date(2026, 9, 23), date(2026, 10, 10)))
        results["consistency"] = consistency(pd.concat(frames), common.read_json(old_path))
    common.write_json(common.OUT / "results.json", results)

    plots = common.OUT / "plots"
    plots.mkdir(exist_ok=True)
    t = select(tables[2025], "primary")
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.boxplot([t[t.tour == 0].occupancy.dropna(), t[t.tour == 1].occupancy.dropna()],
               tick_labels=["other", "tour"])
    ax.set_ylabel("mean occupancy on open days")
    ax.set_title("Season 2025, one point per hut")
    fig.savefig(plots / "occupancy-2025.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    labelled = [(k, v["model"]) for k, v in results["specs"].items()
                if k.split("|")[2] == "occupancy" and "model" in v]
    fig, ax = plt.subplots(figsize=(7, 0.4 * len(labelled) + 1))
    for y, (k, m) in enumerate(labelled):
        ax.plot([m["lo"], m["hi"]], [y, y], color="#345")
        ax.plot(m["coef"], y, "o", color="#345")
    ax.axvline(0, color="#888", lw=1)
    ax.set_yticks(range(len(labelled)), [k for k, _ in labelled], fontsize=7)
    ax.set_xlabel("tour effect on mean occupancy (95% CI)")
    fig.savefig(plots / "tour-effect-occupancy.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    p = results["primary"]
    print("primary:", p if "skipped" in p else
          {"tour_effect": p["model"], "mde": p["mde"], "n": (p["n_tour"], p["n_other"])})


if __name__ == "__main__":
    main()
