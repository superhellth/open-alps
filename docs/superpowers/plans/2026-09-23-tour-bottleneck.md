# Tour Bottleneck-Hut Study Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, in-session on the current checkout. This repo forbids git worktrees and subagent-driven development (`.claude/CLAUDE.md`). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test whether the other huts of an official tour have lower occupancy than similar non-tour huts on the days the tour's smallest hut is sold out.

**Architecture:** Offline Python study under `analysis/tour-huts/`, reading the first study's `hut-days.csv`, `huts.json` and `raw/tours.json` from gitignored `data/analysis/tour-huts/`. Four small modules: tour order (`bottleneck_tours.py`), design construction (`tour_bottleneck.py`: candidates, treatment, controls, panel), estimation (`did.py`: two-way fixed-effects DiD, clustered SE, pairs bootstrap, power), and analysis steps (`bottleneck_steps.py`) driven by `run_bottleneck.py`.

**Tech Stack:** Python 3.11, pandas, numpy, statsmodels, matplotlib, pytest, run through `pixi` in `analysis/tour-huts/`.

**Spec:** `docs/superpowers/specs/2026-09-23-tour-bottleneck-design.md` (extends `2026-09-23-tour-hut-booking-study-design.md`).

## Global Constraints

- No new network fetch. Run no fetch script. No change to `pipeline/`, the doit DAG or `huts/`. Never run a doit task.
- Estimation uses only numpy and statsmodels (plus pandas for tables). The MDE uses `statistics.NormalDist`, not scipy.
- Occupancy per hut-day is defined as in the first study (`hutdays.hut_days`); closed days are dropped.
- Season 2025 is primary, season 2026 is the replication.
- Bottleneck = smallest-capacity eligible hut of a tour, chosen from capacity only, ties broken by the higher 2025 `sold_out_share`. A tour qualifies with at least 3 eligible huts and capacity ≤ 0.7 × the median capacity of its eligible huts.
- Treatment for tour hut B at stage distance m nights from bottleneck A: 1 if A is sold out on day d − m or d + m. Primary uses m ≤ 2. Circular tours use the shorter way round.
- Controls: the 3 nearest non-tour huts within ±500 m elevation and similar size; no distance cap in the primary run; caps of 15, 25, 40 km as sensitivity.
- Model: `occupancy ~ tour × A_full + hut FE + date FE`; SE clustered by tour hut; the primary 95% interval is a pairs cluster bootstrap (2000 draws, fixed seed).
- One pre-defined test: 2025, aligned treatment, bottleneck by capacity. Everything else is exploratory and labelled so in the output.
- Comments describe what the code does now; no history. Work stays on branch `analysis/tour-huts-booking`. Commit trailer: `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.

## Review Focus

- **Closed days count as sold out.** In `hut-days.csv` 95% of closed days have `sold_out = True` (free places 0). A must be treated as sold out only on open days. Pinned in Task 3.
- **Hut without elevation, or with no control inside the tolerances.** The tour hut is counted and dropped, no crash. Pinned in Task 4.
- **Tour GUID with no hut in `huts.geojson`** (5 exist). It keeps its position in the order so stage distances still count its night. Pinned in Task 1.
- **Season edges.** Days where d ± m falls outside the season, or A is closed there, are dropped, not treated as 0. Pinned in Task 3.
- **Empty or degenerate fits.** A panel with no treated tour row, one cluster, or an interaction absorbed by the fixed effects returns a `skipped` record, not an exception. Pinned in Task 5.
- **A hut on two tours or matched as control twice.** Two rows per day, one cluster per tour hut. Pinned in Task 4.

## File Structure

All under `analysis/tour-huts/`:

- Modify `fetch_tours.py`: `parse_tours` also returns `circular` (API field `Rundtour`).
- Modify `tests/test_fetch.py`: expect `circular`.
- Create `bottleneck_tours.py`: tour order, positions, stage distance, pipeline-order validation.
- Create `tour_bottleneck.py`: eligible-hut table, candidates, treatment series, placebo shuffle, controls, units, panel. (Not named `bottleneck.py`: pandas optionally imports the PyPI package `bottleneck`, and a local module of that name shadows it.)
- Create `did.py`: demeaning, `fit_did`, `coef_only`, `cluster_bootstrap`, `min_detectable_effect`.
- Create `bottleneck_steps.py`: primary test, offsets, per-tour, bottleneck-by-A, rank test, placebo dates.
- Create `run_bottleneck.py`: loads inputs, gates on order validation, runs both seasons, writes results and plots.
- Create `tests/test_bottleneck_tours.py`, `tests/test_tour_bottleneck.py`, `tests/test_did.py`, `tests/test_bottleneck_steps.py`.
- Modify `README.md`, `docs/tour-hut-booking-analysis.md`, `docs/superpowers/STATUS.md`, the spec.

## Interface Summary

```python
# bottleneck_tours.py
load_tours(tours: list[dict], huts: list[dict]) -> list[dict]      # {name, circular, guids, ohrs}
positions(tour: dict) -> dict[int, int]                            # ohrs_id -> index in order
stage_distance(i: int, j: int, n: int, circular: bool) -> int
pipeline_sequence(tour: dict, hut_ids: list[str]) -> list[str]
order_agreement(api: list[str], pipeline: list[str]) -> dict       # verdict, shared, api_only, pipeline_only
validate_orders(tours, pipeline_tours, hut_ids) -> list[dict]
orders_validated(rows: list[dict]) -> bool

# tour_bottleneck.py
hut_table(huts, days, season) -> DataFrame
hut_day_index(days, season) -> dict[int, DataFrame]                # indexed by date
candidate_table(tours, table) -> DataFrame
bottleneck_ids(cand: DataFrame) -> dict[str, int]
a_full_series(h: DataFrame, col="sold_out") -> Series              # 1/0, NaN when closed
shift_series(s, k) -> Series                                       # value at d is s at d-k
aligned_treatment(s, m) -> Series                                  # Scheme
shuffle_within_weekday_month(s, rng) -> Series
pick_controls(b, pool, log_cap_sd, k=3, cap_km=None) -> list[tuple[int, float]]
make_units(tour, a_id, table, a_series, cap_km=None, ref_id=None) -> tuple[list[dict], int]
tour_units(tours, bottlenecks, table, hut_days, col="sold_out", cap_km=None) -> tuple[list[dict], dict]
build_panel(units, hut_days, scheme) -> DataFrame                  # PANEL_COLUMNS
pick_placebo_a(a_id, table) -> int | None
controls_km(units) -> dict

# did.py
fit_did(panel) -> dict          # coef, se, lo, hi, p, n, n_clusters, treated_tour_rows | {"skipped": str}
coef_only(panel) -> float
cluster_bootstrap(panel, n=2000, seed=0) -> dict   # lo, hi, se_boot, n_draws
min_detectable_effect(panel, alpha=0.05, power=0.8) -> dict

# bottleneck_steps.py
primary_test(units, hut_days, scheme=aligned_treatment, n_boot=0, seed=0) -> dict
offset_profile(units, hut_days, ks=range(-3, 4)) -> dict[int, dict]
per_tour(units, hut_days, scheme=aligned_treatment) -> dict[str, dict]
effect_by_a(tour, table, hut_days, col="sold_out") -> dict[int, float]
rank_test(effects, chosen, n_sim=10000, seed=0) -> dict
placebo_dates(units, hut_days, n=200, seed=0) -> dict
```

---

### Task 0: Baseline and spec amendment

Investigation of the data showed two places where the spec cannot be followed literally. The spec says to stop if the API order differs from the pipeline order for any of the five matched tours.

- Tauernhöhenweg: the API lists 8 huts, the pipeline 7 (Mindener Hütte is extra in the API). The 7 shared huts are in the same order.
- Welser Höhenweg: the API has Wildensee-Hütte where the pipeline has Albert-Appel-Haus. The 3 shared huts are in the same order.
- Lechquellenrunde, Pitztaltour and Verwallrunde match exactly.

So the order agrees everywhere; only membership differs (the GPX skips or swaps a hut). The amended rule compares the relative order of shared huts and reports membership differences.

**Files:**
- Modify: `docs/superpowers/specs/2026-09-23-tour-bottleneck-design.md` (section "Stage order")

- [ ] **Step 1: Confirm the branch and a green baseline**

Run: `git branch --show-current && cd analysis/tour-huts && pixi run pytest -q`
Expected: `analysis/tour-huts-booking`, all existing tests pass.

- [ ] **Step 2: Amend the spec's stage-order rule**

In the "Stage order" section, replace the sentences from "It is validated against the five tours" through "the plan stops and re-decides the order source." with:

```markdown
It is validated against the five tours that the pipeline matched (`huts/public/data/tours.json`:
Lechquellenrunde, Pitztaltour, Tauernhöhenweg, Verwallrunde, Welser Höhenweg). Their leg sequence is
the ground truth. The API order is valid for a tour when the huts that both lists contain (at least 3)
appear in the same relative order, or in exactly the reverse order. Hut membership may differ, because
the GPX track can skip or swap a hut; each difference is listed in the results. The number of tours
with an agreeing order is reported. If any of the five has a disagreeing order, the run stops and the
order source is re-decided. A hut that has no entry in `huts.geojson` keeps its position in the order.
```

Also replace "A tour with no reliable order enters only the offset-0 test." with "Every tour has an API order; there is no fallback for a tour without one."

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-09-23-tour-bottleneck-design.md docs/superpowers/plans/2026-09-23-tour-bottleneck.md
git commit -m "docs(analysis): amend bottleneck spec order validation, add plan" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 1: Tour order and pipeline validation

**Files:**
- Modify: `analysis/tour-huts/fetch_tours.py:12-19`
- Modify: `analysis/tour-huts/tests/test_fetch.py:9-19`
- Create: `analysis/tour-huts/bottleneck_tours.py`
- Test: `analysis/tour-huts/tests/test_bottleneck_tours.py`

**Interfaces:**
- Consumes: `fetch_tours.parse_tours(payload) -> list[dict]`; `huts.json` hut entries (`ohrs_id`, `guids`).
- Produces: the `bottleneck_tours.py` functions listed in the Interface Summary. A tour dict is `{"name": str, "circular": bool, "guids": list[str], "ohrs": list[int | None]}`; `ohrs[i]` is the OHRS id of `guids[i]`.

- [ ] **Step 1: Update the fetch test to expect `circular`**

In `tests/test_fetch.py` replace the test body with:

```python
def test_parse_tours_handles_empty_list_missing_name_and_case():
    payload = {"features": [
        {"attributes": {"Bezeichnung": "A", "Huettenliste": "{abc-1},{DEF-2}", "Rundtour": 1}},
        {"attributes": {"Bezeichnung": "B", "Huettenliste": "", "Rundtour": 0}},
        {"attributes": {"Bezeichnung": None, "Huettenliste": None}},
    ]}
    tours = fetch_tours.parse_tours(payload)
    assert tours[0] == {"name": "A", "guids": ["{ABC-1}", "{DEF-2}"], "circular": True}
    assert tours[1]["guids"] == [] and tours[1]["circular"] is False
    assert tours[2] == {"name": None, "guids": [], "circular": False}
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd analysis/tour-huts && pixi run pytest tests/test_fetch.py -q`
Expected: FAIL (`KeyError`/assert on `circular`).

- [ ] **Step 3: Add `circular` to `parse_tours`**

In `fetch_tours.py` change the docstring and append line:

```python
def parse_tours(payload: dict) -> list[dict]:
    """Tours as {name, guids, circular}; GUIDs keep their braces and are upper-cased, in the catalogue's order."""
    tours = []
    for feat in payload.get("features", []):
        a = feat["attributes"]
        guids = [g.upper() for g in re.findall(r"\{[^}]+\}", a.get("Huettenliste") or "")]
        tours.append({"name": a.get("Bezeichnung") or None, "guids": guids,
                      "circular": bool(a.get("Rundtour"))})
    return tours
```

- [ ] **Step 4: Write the failing tests for `bottleneck_tours`**

`tests/test_bottleneck_tours.py`:

```python
import bottleneck_tours as bt


def huts():
    return [{"ohrs_id": 1, "guids": ["{A}"]}, {"ohrs_id": 2, "guids": ["{B}", "{B2}"]},
            {"ohrs_id": 3, "guids": ["{C}"]}]


def test_load_tours_maps_guids_and_keeps_gap_for_unmapped_hut():
    raw = [{"name": "T", "guids": ["{A}", "{X}", "{B2}", "{C}"], "circular": False},
           {"name": "empty", "guids": [], "circular": False}]
    tours = bt.load_tours(raw, huts())
    assert len(tours) == 1
    assert tours[0]["ohrs"] == [1, None, 2, 3]
    assert bt.positions(tours[0]) == {1: 0, 2: 2, 3: 3}


def test_stage_distance_counts_gap_and_circular_takes_short_way():
    assert bt.stage_distance(0, 3, 4, False) == 3
    assert bt.stage_distance(0, 3, 4, True) == 1
    assert bt.stage_distance(1, 4, 6, True) == 3


def test_order_agreement_same_reversed_disagree_and_membership():
    p = ["{A}", "{B}", "{C}"]
    assert bt.order_agreement(["{A}", "{B}", "{C}"], p)["verdict"] == "same"
    assert bt.order_agreement(["{C}", "{B}", "{A}"], p)["verdict"] == "reversed"
    assert bt.order_agreement(["{B}", "{A}", "{C}"], p)["verdict"] == "disagree"
    r = bt.order_agreement(["{A}", "{X}", "{B}", "{C}"], p)
    assert r["verdict"] == "same" and r["api_only"] == ["{X}"] and r["pipeline_only"] == []
    assert bt.order_agreement(["{A}", "{B}"], p)["verdict"] == "too_few_shared"


def test_validate_orders_matches_names_and_gates():
    hut_ids = ["{A}", "{B}", "{C}"]
    leg = lambda a, b: {"from": {"type": "hut", "id": a}, "to": {"type": "hut", "id": b}}
    pipe = [{"name": "Tauernhöhenweg", "legs": [leg(0, 1), leg(1, 2)]},
            {"name": "Ghost", "legs": [leg(0, 1)]}]
    tours = [{"name": "Tauern Höhenweg 8 Tage", "guids": ["{A}", "{B}", "{C}"], "ohrs": [], "circular": False}]
    rows = bt.validate_orders(tours, pipe, hut_ids)
    assert rows[0]["verdict"] == "same" and rows[0]["api"] == "Tauern Höhenweg 8 Tage"
    assert rows[1]["verdict"] == "no_api_match"
    assert not bt.orders_validated(rows)
    assert bt.orders_validated(rows[:1])
    assert bt.pipeline_sequence(pipe[0], hut_ids) == ["{A}", "{B}", "{C}"]
```

- [ ] **Step 5: Run to verify failure**

Run: `pixi run pytest tests/test_bottleneck_tours.py -q`
Expected: FAIL, `ModuleNotFoundError: bottleneck_tours`.

- [ ] **Step 6: Implement `bottleneck_tours.py`**

```python
"""Official-tour hut order, stage distance and validation of the API order against the pipeline's tours."""
from __future__ import annotations

import re

MIN_SHARED = 3


def load_tours(tours: list[dict], huts: list[dict]) -> list[dict]:
    """Tours with at least one hut; `ohrs[i]` is the OHRS id of `guids[i]`, None for a GUID without a hut."""
    by_guid = {g.upper(): h["ohrs_id"] for h in huts for g in h["guids"]}
    out = []
    for i, t in enumerate(tours):
        if not t["guids"]:
            continue
        out.append({"name": t["name"] or f"tour-{i}", "circular": bool(t["circular"]),
                    "guids": t["guids"], "ohrs": [by_guid.get(g) for g in t["guids"]]})
    return out


def positions(tour: dict) -> dict[int, int]:
    """OHRS id to first index in the tour's order."""
    pos: dict[int, int] = {}
    for i, o in enumerate(tour["ohrs"]):
        if o is not None:
            pos.setdefault(o, i)
    return pos


def stage_distance(i: int, j: int, n: int, circular: bool) -> int:
    """Nights between two positions of a tour with n huts; a circular tour takes the shorter way round."""
    d = abs(i - j)
    return min(d, n - d) if circular else d


def _norm(name: str) -> str:
    return re.sub(r"[^a-zäöüß0-9]", "", name.lower())


def pipeline_sequence(tour: dict, hut_ids: list[str]) -> list[str]:
    """Hut GUIDs in leg order, consecutive repeats collapsed."""
    seq: list[str] = []
    for leg in tour["legs"]:
        for end in (leg["from"], leg["to"]):
            if end["type"] == "hut":
                g = hut_ids[end["id"]]
                if not seq or seq[-1] != g:
                    seq.append(g)
    return seq


def order_agreement(api: list[str], pipeline: list[str]) -> dict:
    """Compares the relative order of the huts both lists contain."""
    api_set, pipe_set = set(api), set(pipeline)
    a = [g for g in api if g in pipe_set]
    p = [g for g in pipeline if g in api_set]
    if len(a) < MIN_SHARED:
        verdict = "too_few_shared"
    elif a == p:
        verdict = "same"
    elif a == p[::-1]:
        verdict = "reversed"
    else:
        verdict = "disagree"
    return {"verdict": verdict, "shared": len(a),
            "api_only": [g for g in api if g not in pipe_set],
            "pipeline_only": [g for g in pipeline if g not in api_set]}


def validate_orders(tours: list[dict], pipeline_tours: list[dict], hut_ids: list[str]) -> list[dict]:
    """One row per pipeline tour: the API tour whose name starts with it and how the orders compare."""
    rows = []
    for p in pipeline_tours:
        match = [t for t in tours if _norm(t["name"]).startswith(_norm(p["name"]))]
        if len(match) != 1:
            rows.append({"pipeline": p["name"], "api": None, "verdict": "no_api_match"})
            continue
        rows.append({"pipeline": p["name"], "api": match[0]["name"],
                     **order_agreement(match[0]["guids"], pipeline_sequence(p, hut_ids))})
    return rows


def orders_validated(rows: list[dict]) -> bool:
    return all(r["verdict"] in ("same", "reversed") for r in rows)
```

- [ ] **Step 7: Run tests**

Run: `pixi run pytest tests/test_fetch.py tests/test_bottleneck_tours.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add analysis/tour-huts/fetch_tours.py analysis/tour-huts/bottleneck_tours.py analysis/tour-huts/tests/test_fetch.py analysis/tour-huts/tests/test_bottleneck_tours.py
git commit -m "feat(analysis): tour order and pipeline-order validation for bottleneck study" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Eligible-hut table and bottleneck candidates

**Files:**
- Create: `analysis/tour-huts/tour_bottleneck.py`
- Test: `analysis/tour-huts/tests/test_tour_bottleneck.py`

**Interfaces:**
- Consumes: `analyze.select(table, "primary")`, `hutdays.season_table(huts, days, season)`, `bottleneck_tours.load_tours` dicts.
- Produces: `hut_table`, `hut_day_index`, `candidate_table`, `bottleneck_ids` as in the Interface Summary. `hut_table` columns: everything from `season_table` plus `lat`, `lon`. `candidate_table` columns: `tour, n_huts, n_eligible, bottleneck, capacity, median_capacity, ratio, qualifies`.

- [ ] **Step 1: Write the failing test**

`tests/test_tour_bottleneck.py`:

```python
import numpy as np
import pandas as pd

import tour_bottleneck as tb


def tour(name, ids, circular=False):
    return {"name": name, "circular": circular, "guids": [f"{{{i}}}" for i in ids], "ohrs": list(ids)}


def table(caps, shares=None):
    ids = list(caps)
    return pd.DataFrame({"ohrs_id": ids, "capacity": [caps[i] for i in ids],
                         "sold_out_share": [(shares or {}).get(i, 0.1) for i in ids]})


def test_candidates_pick_smallest_apply_ratio_and_three_hut_rule():
    tours = [tour("small", [1, 2, 3, 4]), tour("flat", [5, 6, 7]), tour("few", [8, 9]),
             tour("tie", [10, 11, 12, 13])]
    t = table({1: 20, 2: 100, 3: 100, 4: 100, 5: 90, 6: 100, 7: 100, 8: 10, 9: 100,
               10: 20, 11: 20, 12: 100, 13: 100}, shares={10: 0.1, 11: 0.3})
    c = tb.candidate_table(tours, t).set_index("tour")
    assert c.loc["small", "bottleneck"] == 1 and c.loc["small", "qualifies"]
    assert abs(c.loc["small", "ratio"] - 0.2) < 1e-9
    assert not c.loc["flat", "qualifies"]
    assert not c.loc["few", "qualifies"] and c.loc["few", "n_eligible"] == 2
    assert c.loc["tie", "bottleneck"] == 11
    assert tb.bottleneck_ids(c.reset_index()) == {"small": 1, "tie": 11}


def test_candidates_ignore_huts_missing_from_table():
    c = tb.candidate_table([tour("t", [1, 2, 3, 4])], table({2: 50, 3: 50, 4: 50})).iloc[0]
    assert c.n_huts == 4 and c.n_eligible == 3
```

- [ ] **Step 2: Run to verify failure**

Run: `pixi run pytest tests/test_tour_bottleneck.py -q`
Expected: FAIL, `ModuleNotFoundError: tour_bottleneck`.

- [ ] **Step 3: Implement**

`tour_bottleneck.py`:

```python
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
```

- [ ] **Step 4: Run tests**

Run: `pixi run pytest tests/test_tour_bottleneck.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/tour-huts/tour_bottleneck.py analysis/tour-huts/tests/test_tour_bottleneck.py
git commit -m "feat(analysis): bottleneck candidate table" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Treatment series and date shuffle

**Files:**
- Modify: `analysis/tour-huts/tour_bottleneck.py` (append)
- Modify: `analysis/tour-huts/tests/test_tour_bottleneck.py` (append)

**Interfaces:**
- Consumes: a `hut_day_index` frame (`open`, `sold_out`, `sold_out_near`, indexed by date).
- Produces: `a_full_series(h, col) -> Series` (float, NaN when closed), `shift_series(s, k)`, `aligned_treatment(s, m)` (a `Scheme`), `shuffle_within_weekday_month(s, rng)`.

- [ ] **Step 1: Append the failing tests**

```python
def daily(values, start="2025-06-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values)), dtype=float)


def test_a_full_masks_closed_days_that_report_sold_out():
    idx = pd.date_range("2025-06-01", periods=3)
    h = pd.DataFrame({"open": [True, False, True], "sold_out": [True, True, False],
                      "sold_out_near": [True, True, True]}, index=idx)
    s = tb.a_full_series(h)
    assert s.iloc[0] == 1.0 and np.isnan(s.iloc[1]) and s.iloc[2] == 0.0
    assert tb.a_full_series(h, "sold_out_near").iloc[2] == 1.0


def test_shift_series_both_signs():
    s = daily([0, 1, 0, 0, 1])
    assert tb.shift_series(s, 1).tolist()[1:] == [0, 1, 0, 0] and np.isnan(tb.shift_series(s, 1).iloc[0])
    assert tb.shift_series(s, -1).tolist()[:4] == [1, 0, 0, 1] and np.isnan(tb.shift_series(s, -1).iloc[4])
    assert tb.shift_series(s, 0).tolist() == s.tolist()


def test_aligned_treatment_is_either_direction_and_nan_at_edges_or_closed():
    s = daily([0, 1, 0, 0, 1])
    out = tb.aligned_treatment(s, 1)
    assert np.isnan(out.iloc[0]) and np.isnan(out.iloc[4])
    assert out.iloc[1:4].tolist() == [0, 1, 1]
    closed = daily([0, 1, np.nan, 0, 1])
    assert np.isnan(tb.aligned_treatment(closed, 1).iloc[1])


def test_shuffle_keeps_weekday_month_counts_and_nan_positions():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2025-05-01", periods=150)
    s = pd.Series((np.arange(150) % 3 == 0).astype(float), index=idx)
    s.iloc[[10, 50]] = np.nan
    out = tb.shuffle_within_weekday_month(s, rng)
    assert out.isna().tolist() == s.isna().tolist()
    for _, g in s.dropna().groupby([s.dropna().index.month, s.dropna().index.dayofweek]):
        assert sorted(out.loc[g.index]) == sorted(g)
    assert not out.equals(s)
```

- [ ] **Step 2: Run to verify failure**

Run: `pixi run pytest tests/test_tour_bottleneck.py -q`
Expected: FAIL, `AttributeError` for `a_full_series`.

- [ ] **Step 3: Implement (append to `tour_bottleneck.py`)**

```python
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
```

- [ ] **Step 4: Run tests**

Run: `pixi run pytest tests/test_tour_bottleneck.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/tour-huts/tour_bottleneck.py analysis/tour-huts/tests/test_tour_bottleneck.py
git commit -m "feat(analysis): bottleneck treatment series and date shuffle" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Controls, units, panel

**Files:**
- Modify: `analysis/tour-huts/tour_bottleneck.py` (append)
- Modify: `analysis/tour-huts/tests/test_tour_bottleneck.py` (append)

**Interfaces:**
- Consumes: `hut_table` output (needs `ohrs_id, tour, elevation, capacity, lat, lon`), `positions`, `stage_distance`, `a_full_series`, a `Scheme`.
- Produces:
  - `pick_controls(b: Series, pool: DataFrame, log_cap_sd: float, k=3, cap_km=None) -> list[(ohrs_id, km)]`
  - `make_units(tour, a_id, table, a_series, cap_km=None, ref_id=None) -> (units, n_no_control)`; a unit is `{"tour", "a", "b", "m", "controls", "a_series"}`. `a_id` is the hut whose series is the treatment; `ref_id` (default `a_id`) is the hut whose tour position defines m and which is excluded as B.
  - `tour_units(tours, bottlenecks, table, hut_days, col="sold_out", cap_km=None) -> (units, {"no_control": int, "skipped_tours": list[str]})`
  - `build_panel(units, hut_days, scheme) -> DataFrame` with `PANEL_COLUMNS`; `cluster` is the unit's tour hut.
  - `pick_placebo_a(a_id, table) -> int | None`, `controls_km(units) -> dict`.

- [ ] **Step 1: Append the failing tests**

```python
def geo_table(rows):
    """rows: (ohrs_id, tour_flag, elevation, capacity, lat_offset_deg)"""
    return pd.DataFrame([{"ohrs_id": i, "tour": f, "elevation": e, "capacity": c, "lat": 47 + d, "lon": 11.0,
                          "sold_out_share": 0.1} for i, f, e, c, d in rows])


def test_pick_controls_applies_tolerances_orders_by_distance_and_caps_radius():
    pool = geo_table([(10, 0, 2100, 60, 0.01), (11, 0, 2800, 50, 0.005), (12, 0, 2000, 500, 0.005),
                      (13, 0, 2000, 50, 0.02), (14, 0, 1900, 55, 0.03), (15, 0, 2000, 50, 0.5),
                      (16, 0, np.nan, 50, 0.001)])
    b = geo_table([(1, 1, 2000, 50, 0.0)]).iloc[0]
    assert [i for i, _ in tb.pick_controls(b, pool, 0.5)] == [10, 13, 14]
    assert [i for i, _ in tb.pick_controls(b, pool, 0.5, k=2)] == [10, 13]
    assert [i for i, _ in tb.pick_controls(b, pool, 0.5, cap_km=2.5)] == [10, 13]
    no_elev = geo_table([(1, 1, np.nan, 50, 0.0)]).iloc[0]
    assert tb.pick_controls(no_elev, pool, 0.5) == []


def mini_table():
    return geo_table([(1, 1, 2000, 30, 0.0), (2, 1, 2000, 90, 0.01), (3, 1, 2000, 90, 0.02),
                      (4, 1, 2000, 90, 0.03), (5, 1, 2000, 90, 0.04),
                      (11, 0, 2000, 90, 0.011), (12, 0, 2000, 80, 0.012), (13, 0, 2000, 100, 0.013),
                      (14, 0, 2000, 30, 0.001)])


def test_make_units_stage_distance_max_m_circular_and_no_control():
    t = tour("t", [1, 2, 3, 4, 5])
    a = pd.Series(0.0, index=pd.date_range("2025-06-01", periods=5))
    units, none = tb.make_units(t, 1, mini_table(), a)
    assert {u["b"]: u["m"] for u in units} == {2: 1, 3: 2}
    assert none == 0 and all(len(u["controls"]) == 3 for u in units)
    circ = tour("c", [1, 2, 3, 4, 5], circular=True)
    units, _ = tb.make_units(circ, 1, mini_table(), a)
    assert {u["b"]: u["m"] for u in units} == {2: 1, 3: 2, 4: 2, 5: 1}
    lonely = mini_table()
    lonely.loc[lonely.ohrs_id == 2, "elevation"] = np.nan
    units, none = tb.make_units(t, 1, lonely, a)
    assert [u["b"] for u in units] == [3] and none == 1


def test_make_units_placebo_uses_reference_positions_and_excludes_placebo_from_controls():
    t = tour("t", [1, 2, 3])
    a = pd.Series(0.0, index=pd.date_range("2025-06-01", periods=5))
    units, _ = tb.make_units(t, 14, mini_table(), a, ref_id=1)
    assert {u["b"] for u in units} == {2, 3}
    assert all(14 not in [c for c, _ in u["controls"]] for u in units)
    assert tb.pick_placebo_a(1, mini_table()) == 14


def world_days(ids, n=6, open_=True):
    idx = pd.date_range("2025-06-01", periods=n)
    return {i: pd.DataFrame({"occupancy": 0.5, "sold_out": False, "sold_out_near": False, "open": open_},
                            index=idx) for i in ids}


def test_build_panel_shared_hut_gives_two_rows_per_day_one_cluster_and_drops_closed_a_days():
    hd = world_days([2, 11, 12, 13])
    idx = pd.date_range("2025-06-01", periods=6)
    a1 = pd.Series([0, 1, 0, 0, 1, 0.0], index=idx)
    a2 = pd.Series([1, 0, 0, 1, 0, 0.0], index=idx)
    u1 = {"tour": "t1", "a": 1, "b": 2, "m": 1, "controls": [(11, 1.0), (12, 2.0), (13, 3.0)], "a_series": a1}
    u2 = {"tour": "t2", "a": 9, "b": 2, "m": 1, "controls": [(11, 1.0), (12, 2.0), (13, 3.0)], "a_series": a2}
    p = tb.build_panel([u1, u2], hd, tb.aligned_treatment)
    assert list(p.columns) == tb.PANEL_COLUMNS
    b_rows = p[(p.hut == 2)]
    assert len(b_rows) == 2 * 4 and set(b_rows.cluster) == {2}
    assert set(b_rows.groupby("tour_name").size()) == {4}
    assert p[p.tour == 0].x.eq(0).all()
    closed = a1.copy()
    closed.iloc[2] = np.nan
    p2 = tb.build_panel([dict(u1, a_series=closed)], hd, tb.aligned_treatment)
    assert len(p2[p2.hut == 2]) < 4


def test_controls_km_summary():
    u = {"controls": [(1, 2.0), (2, 4.0)]}
    assert tb.controls_km([u]) == {"n": 2, "median": 3.0, "max": 4.0}
    assert tb.controls_km([]) == {"n": 0, "median": None, "max": None}
```

- [ ] **Step 2: Run to verify failure**

Run: `pixi run pytest tests/test_tour_bottleneck.py -q`
Expected: FAIL, `AttributeError: pick_controls`.

- [ ] **Step 3: Implement (append to `tour_bottleneck.py`)**

```python
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
```

- [ ] **Step 4: Run tests**

Run: `pixi run pytest tests/test_tour_bottleneck.py -q`
Expected: PASS. If `test_pick_controls…` fails on distance order, check that 0.01° latitude ≈ 1.1 km, so caps of 2.5 km keep ids 10 and 13 only.

- [ ] **Step 5: Commit**

```bash
git add analysis/tour-huts/tour_bottleneck.py analysis/tour-huts/tests/test_tour_bottleneck.py
git commit -m "feat(analysis): bottleneck controls, units and DiD panel" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Two-way fixed-effects DiD, bootstrap, power

**Files:**
- Create: `analysis/tour-huts/did.py`
- Test: `analysis/tour-huts/tests/test_did.py`

**Interfaces:**
- Consumes: a panel with columns `y, x, treat, hut, date, cluster` (extra columns ignored). `date` may be any hashable.
- Produces: `fit_did`, `coef_only`, `cluster_bootstrap`, `min_detectable_effect` as in the Interface Summary. `fit_did` returns `{"skipped": reason}` for an empty/degenerate panel; `treat` main effect is dropped from the regression when the fixed effects absorb it.

- [ ] **Step 1: Write the failing tests**

`tests/test_did.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `pixi run pytest tests/test_did.py -q`
Expected: FAIL, `ModuleNotFoundError: did`.

- [ ] **Step 3: Implement `did.py`**

```python
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
    """Minimum detectable interaction effect from the fixed-effects residual variance and the demeaned interaction.

    Uses only the outcome's fixed-effects residual and the design; the treatment coefficient is not estimated.
    The standard error is the iid one, so it is a lower bound of the clustered one.
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
    sigma2 = float(D[:, 0] @ D[:, 0]) / (len(D) - 1)
    z = NormalDist().inv_cdf(1 - alpha / 2) + NormalDist().inv_cdf(power)
    return {"mde": float(z * np.sqrt(sigma2 / ss)), "sigma": float(np.sqrt(sigma2)),
            "treated_tour_rows": int((panel.x == 1).sum())}
```

- [ ] **Step 4: Run tests**

Run: `pixi run pytest tests/test_did.py -q`
Expected: PASS. If the MDE noise-ratio test is off, check that `synth`'s noise is the only thing that changes between the two calls (`seed` is fixed).

- [ ] **Step 5: Commit**

```bash
git add analysis/tour-huts/did.py analysis/tour-huts/tests/test_did.py
git commit -m "feat(analysis): two-way FE DiD with cluster bootstrap and MDE" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Analysis steps

**Files:**
- Create: `analysis/tour-huts/bottleneck_steps.py`
- Test: `analysis/tour-huts/tests/test_bottleneck_steps.py`

**Interfaces:**
- Consumes: everything in `tour_bottleneck.py` and `did.py`.
- Produces: the `bottleneck_steps.py` functions in the Interface Summary. `primary_test` computes `power` before it fits the coefficient. `rank_test` counts a tour as a "hit" when the chosen bottleneck has the most negative coefficient of all huts of the tour tried as A. `placebo_dates` returns `{"observed", "perm_mean", "perm_sd", "p_two_sided", "n"}`.

- [ ] **Step 1: Write the failing tests**

`tests/test_bottleneck_steps.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `pixi run pytest tests/test_bottleneck_steps.py -q`
Expected: FAIL, `ModuleNotFoundError: bottleneck_steps`.

- [ ] **Step 3: Implement `bottleneck_steps.py`**

```python
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
```

- [ ] **Step 4: Run tests**

Run: `pixi run pytest tests/test_bottleneck_steps.py -q`
Expected: PASS. In `test_offset_profile…` the mini world's tour huts 2 and 3 carry the effect; hut 4 has `m = 3` and is outside the units, which is intended.

- [ ] **Step 5: Run the whole suite**

Run: `pixi run pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add analysis/tour-huts/bottleneck_steps.py analysis/tour-huts/tests/test_bottleneck_steps.py
git commit -m "feat(analysis): bottleneck analysis steps" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Orchestrator, order gate and real run

**Files:**
- Create: `analysis/tour-huts/run_bottleneck.py`

**Interfaces:**
- Consumes: all modules above; files `huts.json`, `hut-days.csv`, `raw/tours.json` in `data/analysis/tour-huts/`; `huts/public/data/tours.json` and `hut-edge-payload.json` (`hut_ids`) for the order validation.
- Produces: `data/analysis/tour-huts/bottleneck-results.json`, `bottleneck-candidates.csv`, `plots/bottleneck-offsets.png`, `plots/bottleneck-tours.png`.

- [ ] **Step 1: Write `run_bottleneck.py`**

```python
"""Runs the tour bottleneck-hut study; writes bottleneck-results.json, bottleneck-candidates.csv and plots."""
from __future__ import annotations

import numpy as np
import pandas as pd

import bottleneck_steps as bs
import bottleneck_tours as bt
import common
import did
import fetch_tours
import stats
import tour_bottleneck as tb

N_BOOT = 2000
N_PLACEBO = 200
CAPS_KM = (15, 25, 40)
PUBLIC = common.ROOT / "huts" / "public" / "data"


def load_inputs():
    huts = common.read_json(common.OUT / "huts.json")["huts"]
    days = pd.read_csv(common.OUT / "hut-days.csv", parse_dates=["date"])
    raw = fetch_tours.parse_tours(common.read_json(common.OUT / "raw" / "tours.json")["body"])
    return huts, days, bt.load_tours(raw, huts)


def order_validation(tours: list[dict]) -> list[dict]:
    pipeline_tours = common.read_json(PUBLIC / "tours.json")
    hut_ids = common.read_json(PUBLIC / "hut-edge-payload.json")["hut_ids"]
    return bt.validate_orders(tours, pipeline_tours, hut_ids)


def season_results(season: int, tours: list[dict], bottlenecks: dict[str, int], huts: list[dict],
                   days: pd.DataFrame) -> dict:
    table = tb.hut_table(huts, days, season)
    hd = tb.hut_day_index(days, season)
    circular = {t["name"]: t["circular"] for t in tours}
    units, info = tb.tour_units(tours, bottlenecks, table, hd)
    out: dict = {"n_units": len(units), **info, "controls_km": tb.controls_km(units)}
    # The pre-defined test: power is computed before the coefficient inside primary_test.
    out["primary"] = bs.primary_test(units, hd, n_boot=N_BOOT)
    panel = tb.build_panel(units, hd, tb.aligned_treatment)
    tour_rows = panel[panel.tour == 1]
    out["ceiling"] = {
        "own_sold_out_share": float(tour_rows.own_sold_out.mean()) if len(tour_rows) else None,
        "did": did.fit_did(panel[~panel.own_sold_out])}
    out["cuts"] = {"fri_sun": did.fit_did(panel[panel.date.dt.dayofweek >= 4]),
                   "jul_aug": did.fit_did(panel[panel.date.dt.month.isin([7, 8])])}
    out["radius_km"] = {}
    for cap in CAPS_KM:
        u, _ = tb.tour_units(tours, bottlenecks, table, hd, cap_km=cap)
        out["radius_km"][cap] = did.fit_did(tb.build_panel(u, hd, tb.aligned_treatment))
    u_near, _ = tb.tour_units(tours, bottlenecks, table, hd, col="sold_out_near")
    out["sold_out_near"] = did.fit_did(tb.build_panel(u_near, hd, tb.aligned_treatment))
    out["offsets"] = bs.offset_profile([u for u in units if not circular[u["tour"]]], hd)
    out["per_tour"] = bs.per_tour(units, hd)
    effects = {t["name"]: bs.effect_by_a(t, table, hd) for t in tours if t["name"] in bottlenecks}
    out["effects_by_a"] = {t: {str(a): c for a, c in e.items()} for t, e in effects.items()}
    out["rank_test"] = bs.rank_test(effects, bottlenecks)
    placebo_units = []
    in_table = set(table.ohrs_id)
    for t in tours:
        a = bottlenecks.get(t["name"])
        if a is None or a not in in_table:
            continue
        p = tb.pick_placebo_a(a, table)
        if p is not None and p in hd:
            u, _ = tb.make_units(t, p, table, tb.a_full_series(hd[p]), ref_id=a)
            placebo_units += u
    out["placebo_a"] = bs.primary_test(placebo_units, hd)
    out["placebo_dates"] = bs.placebo_dates(units, hd, n=N_PLACEBO)
    return out


def plots(results: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = common.OUT / "plots"
    out.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 4))
    for season, color in (("2025", "#345"), ("2026", "#b63")):
        prof = {int(k): v for k, v in results["seasons"][season]["offsets"].items() if "coef" in v}
        ks = sorted(prof)
        ax.errorbar(np.array(ks) + (0.08 if season == "2026" else 0), [prof[k]["coef"] for k in ks],
                    yerr=[[prof[k]["coef"] - prof[k]["lo"] for k in ks],
                          [prof[k]["hi"] - prof[k]["coef"] for k in ks]],
                    fmt="o-", color=color, capsize=2, label=season)
    ax.axhline(0, color="#888", lw=1)
    ax.set_xlabel("offset k (nights): treatment = bottleneck sold out on day d - k")
    ax.set_ylabel("tour x sold-out effect on occupancy")
    ax.legend()
    fig.savefig(out / "bottleneck-offsets.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    pt = {t: r for t, r in results["seasons"]["2025"]["per_tour"].items() if "coef" in r}
    fig, ax = plt.subplots(figsize=(6, 0.35 * len(pt) + 1))
    for y, (t, r) in enumerate(sorted(pt.items())):
        ax.plot([r["lo"], r["hi"]], [y, y], color="#345")
        ax.plot(r["coef"], y, "o", color="#345")
    ax.axvline(0, color="#888", lw=1)
    ax.set_yticks(range(len(pt)), sorted(pt), fontsize=7)
    ax.set_xlabel("per-tour effect, 2025 (exploratory, cluster SE)")
    fig.savefig(out / "bottleneck-tours.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    huts, days, tours = load_inputs()
    validation = order_validation(tours)
    results: dict = {"order_validation": validation,
                     "order_agreeing": sum(r["verdict"] in ("same", "reversed") for r in validation),
                     "predefined_test": "seasons.2025.primary; everything else is exploratory"}
    if not bt.orders_validated(validation):
        common.write_json(common.OUT / "bottleneck-results.json", results)
        raise SystemExit(f"order validation failed, re-decide the order source: {validation}")
    table25 = tb.hut_table(huts, days, 2025)
    cand = tb.candidate_table(tours, table25)
    cand.to_csv(common.OUT / "bottleneck-candidates.csv", index=False)
    bottlenecks = tb.bottleneck_ids(cand)
    results.update(candidates=cand.to_dict("records"), n_tours=len(cand), n_with_bottleneck=len(bottlenecks))
    results["seasons"] = {str(s): season_results(s, tours, bottlenecks, huts, days) for s in (2025, 2026)}
    r25, r26 = (results["seasons"][s]["primary"] for s in ("2025", "2026"))
    if "bootstrap" in r25 and "bootstrap" in r26:
        as_ci = lambda r: {"coef": r["did"]["coef"], "lo": r["bootstrap"]["lo"], "hi": r["bootstrap"]["hi"]}
        results["replicated"] = stats.replicated(as_ci(r25), as_ci(r26))
    common.write_json(common.OUT / "bottleneck-results.json", results)
    plots(results)
    print("tours with bottleneck:", len(bottlenecks), "of", len(cand))
    print("2025 primary:", r25)
    print("2026 primary:", r26)
    print("replicated:", results.get("replicated"))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Check the order gate first**

Run: `cd analysis/tour-huts && pixi run python -c "import run_bottleneck as r; h,d,t=r.load_inputs(); import json; [print(x['pipeline'], x['verdict'], x.get('shared')) for x in r.order_validation(t)]"`
Expected: five rows, each `same` (or `reversed`). If any row says `disagree`, `no_api_match` or `too_few_shared`, stop and take it to the user: the order source must be re-decided.

- [ ] **Step 3: Run the study**

Run: `pixi run python run_bottleneck.py`
Expected: prints the number of tours with a bottleneck and both primary results, writes the four output files. The bootstrap runs 2 × 2000 refits; allow a few minutes. If it raises, read the traceback: a `KeyError` on a hut id means `hut_days` lacks a hut that `table` has, which cannot occur for a table built from the same `days`.

- [ ] **Step 4: Sanity-check the output before trusting it**

Run:
```bash
pixi run python - <<'E'
import json, common
r = json.load(open(common.OUT / "bottleneck-results.json"))
print(r["order_agreeing"], r["n_with_bottleneck"], "of", r["n_tours"])
for s in ("2025", "2026"):
    x = r["seasons"][s]
    print(s, "units", x["n_units"], "controls km", x["controls_km"], "no_control", x["no_control"],
          "skipped", x["skipped_tours"])
    print("  power", x["primary"]["power"]); print("  did", x["primary"]["did"])
    print("  placebo_a", x["placebo_a"]["did"]); print("  placebo_dates", x["placebo_dates"])
    print("  ceiling", x["ceiling"]["own_sold_out_share"])
E
```
Expected: `n_with_bottleneck` is at least 3, `treated_tour_rows` in the hundreds or more, the MDE is a plausible occupancy difference (below 0.3), and every `did` holds a `coef`. If the number of qualifying tours is below 3 or `treated_tour_rows` is tiny, report it to the user rather than tuning thresholds.

- [ ] **Step 5: Commit**

```bash
git add analysis/tour-huts/run_bottleneck.py
git commit -m "feat(analysis): run bottleneck study end to end" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: Documentation and status

**Files:**
- Modify: `analysis/tour-huts/README.md`
- Modify: `docs/tour-hut-booking-analysis.md` (new section at the end)
- Modify: `docs/superpowers/STATUS.md` (the bottleneck spec row)
- Delete: `docs/superpowers/plans/2026-09-23-tour-bottleneck.md`

- [ ] **Step 1: README**

In `README.md`, add after the `analyze.py` line of the code block:

```bash
pixi run python run_bottleneck.py      # bottleneck-results.json, bottleneck-candidates.csv, plots/ (no network)
```

and a sentence below the block: `The bottleneck study (docs/superpowers/specs/2026-09-23-tour-bottleneck-design.md) reads hut-days.csv, huts.json and raw/tours.json; it needs no new fetch.`

- [ ] **Step 2: Results section**

Append a section `## Bottleneck huts` to `docs/tour-hut-booking-analysis.md`, written from `bottleneck-results.json` in plain prose, with these parts in this order, each with the numbers from the file:

1. The pre-defined test result: coefficient, bootstrap 95% interval, cluster-SE interval, number of tours, units, treated tour hut-days, and the MDE next to it. State the direction against the thesis (a negative value supports it).
2. "Most tours have a bottleneck": `n_with_bottleneck` of `n_tours`, and the order validation (`order_agreeing` of 5; name the membership differences for Tauernhöhenweg and Welser Höhenweg).
3. Validity checks: placebo A, placebo dates (p), sold-out-near, ceiling (share and the refit), radius caps 15/25/40 km, control distances (median, max).
4. Exploratory results, labelled as such: offset profile (say whether an effect at every offset points to a regional confound), per-tour table, rank test (observed share against chance share), cuts (Fri–Sun, July–August).
5. Replication 2026: same sign and overlapping bootstrap intervals, yes or no (`replicated`).
6. Limits copied from the spec's "Limits of the data": final-state calendar, no booking timeline, cancellations in and offline bookings out, current capacity, 26 tours that share huts.

If the result is "no detectable effect", say that, and put the MDE beside it. Do not describe an exploratory row as evidence.

- [ ] **Step 3: STATUS and plan cleanup**

In `docs/superpowers/STATUS.md` change the bottleneck row status from `in progress` to `done`. Then:

```bash
git rm docs/superpowers/plans/2026-09-23-tour-bottleneck.md
```

- [ ] **Step 4: Full test run and commit**

Run: `cd analysis/tour-huts && pixi run pytest -q`
Expected: all pass.

```bash
git add analysis/tour-huts/README.md docs/tour-hut-booking-analysis.md docs/superpowers/STATUS.md
git commit -m "docs(analysis): bottleneck study results and status" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:** goal and thesis (Tasks 5–7); inputs (Task 7 `load_inputs`); stage order and validation (Tasks 0, 1, 7 gate); bottleneck per tour with 3-hut rule, 0.7 ratio, tie-break (Task 2); treatment with m ≤ 2, either direction, circular (Tasks 1, 3, 4); controls with tolerances, no cap, 15/25/40 km sensitivity, drop-and-count (Tasks 4, 7); model with hut/date FE, cluster SE, pairs bootstrap 2000 draws (Task 5); analysis steps 1–7: candidates (2), primary (6, 7), offsets (6), per-tour (6), rank test (6), cuts (7), replication (7); validity checks: placebo A (4, 7), placebo dates (3, 6), sold-out threshold (7), ceiling (7), power before coefficient (5, 6), one pre-defined test labelled (7); outputs and docs (7, 8); tests listed in the spec (Tasks 2–6: bottleneck choice, offset treatment, DiD known effect and zero, shared hut, shuffle counts).

**Interpretations to confirm (not spelled out in the spec):**
1. Order validation compares the relative order of shared huts (Task 0), because two of the five tours differ in membership.
2. "Offset 0" in the pre-defined test is read as the stage-aligned treatment (`aligned_treatment`, d ± m). The offset profile in step 3 shifts A_full by a signed k and applies it to every tour hut within m ≤ 2; its k = 0 is the same-day treatment. Because `offset_profile` takes any `Scheme`, a different reading is a one-line change.
3. "Similar size" = log-capacity difference within 1 standard deviation of the eligible huts' log capacity. Placebo A = nearest non-tour hut within 0.2 log-capacity units.
4. Ceiling check drops own-hut sold-out days for tour huts and controls alike, so the two groups are trimmed the same way.
5. Days where A is closed on d, d − m or d + m are dropped, not treated as 0.
6. Per-tour effects and the rank test cover the tours that qualify as bottleneck candidates.
7. The module is `tour_bottleneck.py`, not `bottleneck.py`, to avoid shadowing pandas' optional dependency.

**Type consistency:** unit keys (`tour, a, b, m, controls, a_series`), panel columns (`PANEL_COLUMNS`), and function names match between Tasks 2–7.
