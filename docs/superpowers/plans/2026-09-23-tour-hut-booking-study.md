# Tour-hut booking study Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (this repo forbids subagent-driven development and worktrees, see root `CLAUDE.md`). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `analysis/tour-huts/` that fetches a full season of past OHRS availability for our 239 OHRS huts and tests whether huts on official tours are booked more than huts on no tour.

**Architecture:** Six small scripts (fetch tours, capacity, calendars → link → build hut-days → analyze) with pure, unit-tested logic in importable modules and thin `main()`s. Raw API responses are cached unmodified under gitignored `data/analysis/tour-huts/raw/`, so analysis changes never need a re-fetch. Nothing touches `pipeline/`, the doit DAG or `huts/`.

**Tech Stack:** Python 3.11, stdlib `urllib` for HTTP, pandas, numpy, scipy, statsmodels, matplotlib, pytest, run through a dedicated pixi env (`analysis/tour-huts/pixi.toml`).

**Spec:** `docs/superpowers/specs/2026-09-23-tour-hut-booking-study-design.md`

## Global Constraints

- Code tracked in `analysis/tour-huts/`; outputs in gitignored `data/analysis/tour-huts/` (root `.gitignore` already ignores `/data/`).
- Never run any `pipeline/` task or `doit`. Do not modify `pipeline/`, `huts/` or the existing `data/analysis/*.py` scripts.
- Work on a feature branch, never `main`. The current checkout has unrelated uncommitted UI changes: **always `git add` explicit paths**, never `git add -A` / `git commit -a`.
- Season 2025 = 01.05.–31.10.2025 (primary). Season 2026 = 01.05.–23.09.2026 (replication).
- Dates to OHRS are `DD.MM.YYYY`; `numberOfPeople: 1`.
- Requests spaced 0.3 s, one at a time, retried up to 3 times with backoff, explicit `User-Agent` (default Python UA gets HTTP 403). A failed request is stored as an error record, never skipped.
- Fetch scripts skip requests whose raw file already exists unless `--refresh`.
- Open day = `hutStatus == "SERVICED"`; closed days dropped. `occupancy = (capacity - clamp(freePlace, 0, capacity)) / capacity`. Sold out = `freePlace == 0`; sensitivity: `freePlace <= 5% of capacity`.
- A hut-season is eligible with ≥ 14 open days; eligibility never depends on bookings.
- Primary result = ONE pre-defined test: OLS tour coefficient, occupancy, season 2025, whole season. Everything else is labelled exploratory.
- Comments state what the code does now, no history. Docs live in `docs/`.

## Review Focus

- Hut whose `freePlace` is constantly `0` on every open day (always sold out): must NOT be marked "no activity" (Task 4).
- Calendar record that is an error record or has an empty body: hut is excluded with the error listed, not crashed on (Task 3).
- `ohrsHutId` shared by two GUIDs (id 73): one hut, on-tour if either GUID is on a tour, calendar fetched once (Task 3).
- `elevation == 0` in geojson means missing: hut stays in raw/matched comparisons but is dropped from the regression, not entered as 0 m (Tasks 3, 5).
- Tour GUIDs with no match in `huts.geojson`, and tours with empty/absent `Huettenliste` or no name: listed in output, no crash (Tasks 2, 3).

## File Structure

All under `analysis/tour-huts/` (flat; tests add this dir to `sys.path` via `conftest.py`):

| File | Responsibility |
| --- | --- |
| `pixi.toml`, `pixi.lock` | analysis env |
| `README.md` | run order, env, outputs |
| `common.py` | paths, seasons, HTTP helper, cache helper, hut scope |
| `fetch_tours.py` | `raw/tours.json` + `parse_tours` |
| `fetch_capacity.py` | `raw/hut-info/{id}.json` |
| `fetch_calendars.py` | `raw/calendar-{season}/{id}.json` |
| `approach_time.py` | min approach minutes per hut GUID from `approaches.*` |
| `link_huts.py` | `huts.json`: one entry per `ohrsHutId` |
| `hutdays.py` | pure metric code: hut-days, per-hut-season aggregation, season table |
| `build_hut_days.py` | `hut-days.csv` |
| `stats.py` | bootstrap, OLS, GLM, matching, power, replication |
| `analyze.py` | runs all specs, validity checks, `results.json`, plots |
| `tests/` | `conftest.py`, `test_*.py`, `fixtures/` |

Layout refinement vs spec: calendars are stored one file per hut (`raw/calendar-{season}/{id}.json`) so a re-run skips finished huts. The 2026 fetch window ends 10.10.2026 (analysis clips at 23.09.2026) so the past-data consistency check has overlapping days with `data/analysis/hut-availability-raw.json` (23.09.–09.10.2026).

Decisions for the spec's open items:

- **hut-days format:** CSV (`pyarrow` not needed; ~90k rows).
- **region:** three longitude bands: `west` (< 10.5°E), `central` (10.5–12.5°E), `east` (≥ 12.5°E). Task 9 checks each band has ≥ 15 analysed huts and re-bins if not.
- **approach_time:** minimum DIN 33466 duration (minutes) over all `approaches.bin` rows of the hut (`hut_id` indexes `hut-edge-payload.json`'s `hut_ids`; `approaches.json` has no `hut_ids`). Columns are little-endian, per-column layout, offsets from the manifest.

---

### Task 1: Branch, env, scaffolding, `common.py`

**Files:**
- Create: `analysis/tour-huts/pixi.toml`, `analysis/tour-huts/common.py`, `analysis/tour-huts/tests/conftest.py`, `analysis/tour-huts/tests/test_common.py`

**Interfaces:**
- Produces (`common.py`):
  - `ROOT, OUT: Path`, `HUTS_GEOJSON: Path`, `OHRS: str`, `TOURS_URL: str`, `SEASONS: dict[int, Season]`
  - `Season = NamedTuple(start: date, end: date, fetch_end: date)`
  - `request_json(url, body=None, *, method=None, retries=3, sleep=time.sleep, urlopen=urllib.request.urlopen) -> dict` returns `{"ok": True, "body": ...}` or `{"ok": False, "error": str}`
  - `fetch_cached(path: Path, fetch: Callable[[], dict], refresh=False, gap=0.3, sleep=time.sleep) -> str` returns `"cached" | "ok" | "error"`
  - `read_json(path)`, `write_json(path, obj)`
  - `hut_scope(features: list[dict]) -> list[int]` sorted unique `int(ohrsHutId)` of features with a non-null `ohrsHutId`
  - `fmt_date(d: date) -> str` (`DD.MM.YYYY`)

- [ ] **Step 1: Create branch**

```bash
cd /home/superhellth/open-alps && git checkout -b analysis/tour-huts-booking
```

- [ ] **Step 2: Create env**

`analysis/tour-huts/pixi.toml`:

```toml
[workspace]
name = "tour-huts-analysis"
version = "0.1.0"
description = "Tour-hut booking study (docs/superpowers/specs/2026-09-23-tour-hut-booking-study-design.md)"
channels = ["conda-forge"]
platforms = ["linux-64", "osx-64", "osx-arm64"]

[dependencies]
python = "3.11.*"
pandas = "*"
numpy = "*"
scipy = "*"
statsmodels = "*"
matplotlib = "*"
pytest = "*"

[tasks]
test = "pytest"
```

Run: `cd analysis/tour-huts && pixi install`
Expected: creates `pixi.lock` and `.pixi/` (`.pixi/` is already gitignored). Ask the user first if the install needs approval.

- [ ] **Step 3: Write failing tests**

`analysis/tour-huts/tests/conftest.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

`analysis/tour-huts/tests/test_common.py`:

```python
import json
from datetime import date

import common


class FakeResp:
    def __init__(self, obj):
        self._raw = json.dumps(obj).encode()

    def read(self, *a):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_request_json_ok_sets_user_agent():
    seen = {}

    def fake(req, timeout):
        seen["ua"] = req.get_header("User-agent")
        return FakeResp([1, 2])

    out = common.request_json("http://x", urlopen=fake, sleep=lambda s: None)
    assert out == {"ok": True, "body": [1, 2]}
    assert seen["ua"] == common.USER_AGENT


def test_request_json_retries_then_returns_error_record():
    calls = []

    def fake(req, timeout):
        calls.append(1)
        raise OSError("boom")

    out = common.request_json("http://x", urlopen=fake, sleep=lambda s: None)
    assert len(calls) == 3
    assert out["ok"] is False and "boom" in out["error"]


def test_fetch_cached_skips_ok_retries_error_and_refresh(tmp_path):
    p = tmp_path / "a.json"
    n = []

    def ok():
        n.append(1)
        return {"ok": True, "body": 1}

    assert common.fetch_cached(p, ok, sleep=lambda s: None) == "ok"
    assert common.fetch_cached(p, ok, sleep=lambda s: None) == "cached"
    assert common.fetch_cached(p, ok, refresh=True, sleep=lambda s: None) == "ok"
    assert len(n) == 2
    common.write_json(p, {"ok": False, "error": "x"})
    assert common.fetch_cached(p, ok, sleep=lambda s: None) == "ok"


def test_hut_scope_dedups_and_skips_null():
    feats = [
        {"properties": {"ohrsHutId": "73"}},
        {"properties": {"ohrsHutId": "73"}},
        {"properties": {"ohrsHutId": None}},
        {"properties": {"ohrsHutId": "5"}},
    ]
    assert common.hut_scope(feats) == [5, 73]


def test_fmt_date():
    assert common.fmt_date(date(2025, 5, 1)) == "01.05.2025"


def test_seasons():
    assert common.SEASONS[2025].end == date(2025, 10, 31)
    assert common.SEASONS[2026].end == date(2026, 9, 23)
    assert common.SEASONS[2026].fetch_end == date(2026, 10, 10)
```

- [ ] **Step 4: Run, expect fail**

Run: `cd analysis/tour-huts && pixi run pytest tests/test_common.py -q`
Expected: FAIL `ModuleNotFoundError: No module named 'common'` (or collection error).

- [ ] **Step 5: Implement `common.py`**

```python
"""Paths, seasons, HTTP and caching helpers shared by the tour-huts study scripts."""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import date
from pathlib import Path
from typing import Callable, NamedTuple

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "analysis" / "tour-huts"
HUTS_GEOJSON = ROOT / "huts" / "public" / "data" / "huts.geojson"
OHRS = "https://www.hut-reservation.org"
TOURS_URL = "https://caa.alpenverein.at/service/server/tourSelection.php"
USER_AGENT = "open-alps-analysis/1.0"
REQUEST_GAP_S = 0.3


class Season(NamedTuple):
    start: date
    end: date
    fetch_end: date


SEASONS: dict[int, Season] = {
    2025: Season(date(2025, 5, 1), date(2025, 10, 31), date(2025, 10, 31)),
    2026: Season(date(2026, 5, 1), date(2026, 9, 23), date(2026, 10, 10)),
}


def fmt_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def read_json(path: Path):
    return json.loads(path.read_text())


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False))


def request_json(url, body=None, *, method=None, retries=3, sleep=time.sleep,
                 urlopen=urllib.request.urlopen) -> dict:
    """One JSON request with retries and backoff; returns an ok record or an error record."""
    method = method or ("GET" if body is None else "POST")
    data = None if body is None else json.dumps(body).encode()
    if method == "POST" and data is None:
        data = b""
    headers = {"User-Agent": USER_AGENT}
    if body is not None:
        headers["Content-Type"] = "application/json"
    error = ""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data, headers, method=method)
            with urlopen(req, timeout=30) as resp:
                return {"ok": True, "body": json.load(resp)}
        except Exception as e:  # noqa: BLE001 - any failure becomes a stored error record
            error = f"{type(e).__name__}: {e}"[:200]
            sleep(1 + attempt * 2)
    return {"ok": False, "error": error}


def fetch_cached(path: Path, fetch: Callable[[], dict], refresh=False,
                 gap=REQUEST_GAP_S, sleep=time.sleep) -> str:
    """Runs `fetch` and stores its record unless an ok record is already on disk."""
    if path.exists() and not refresh and read_json(path).get("ok"):
        return "cached"
    rec = fetch()
    write_json(path, rec)
    sleep(gap)
    return "ok" if rec["ok"] else "error"


def hut_scope(features: list[dict]) -> list[int]:
    """Sorted unique OHRS ids of every hut feature that has one."""
    return sorted({int(f["properties"]["ohrsHutId"]) for f in features
                   if f["properties"].get("ohrsHutId")})
```

- [ ] **Step 6: Run, expect pass**

Run: `cd analysis/tour-huts && pixi run pytest tests/test_common.py -q`
Expected: 6 passed.

- [ ] **Step 7: Commit**

```bash
cd /home/superhellth/open-alps
git add analysis/tour-huts/pixi.toml analysis/tour-huts/pixi.lock analysis/tour-huts/common.py analysis/tour-huts/tests docs/superpowers/specs/2026-09-23-tour-hut-booking-study-design.md docs/superpowers/plans/2026-09-23-tour-hut-booking-study.md
git commit -m "feat(analysis): scaffold tour-hut booking study

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Fetch scripts (tours, capacity, calendars)

**Files:**
- Create: `analysis/tour-huts/fetch_tours.py`, `fetch_capacity.py`, `fetch_calendars.py`
- Test: `analysis/tour-huts/tests/test_fetch.py`

**Interfaces:**
- Consumes: `common.request_json`, `fetch_cached`, `hut_scope`, `OUT`, `OHRS`, `TOURS_URL`, `SEASONS`, `fmt_date`, `HUTS_GEOJSON`, `read_json`.
- Produces:
  - `fetch_tours.parse_tours(payload: dict) -> list[dict]` → `[{"name": str|None, "guids": list[str]}]`, GUIDs upper-cased with braces, e.g. `"{593D0233-...}"`.
  - `fetch_calendars.calendar_body(start: date, end: date) -> dict`
  - `fetch_calendars.calendar_url(ohrs_id: int) -> str`, `fetch_capacity.info_url(ohrs_id: int) -> str`
  - Files: `OUT/raw/tours.json`, `OUT/raw/hut-info/{id}.json`, `OUT/raw/calendar-{season}/{id}.json` (all `{"ok", "body"|"error"}` records; body unmodified).
  - Each script: `main(argv=None)` with `--refresh`; calendars also `--season 2025|2026` (default: both).

- [ ] **Step 1: Write failing tests**

`analysis/tour-huts/tests/test_fetch.py`:

```python
from datetime import date

import fetch_calendars
import fetch_capacity
import fetch_tours


def test_parse_tours_handles_empty_list_missing_name_and_case():
    payload = {"features": [
        {"attributes": {"Bezeichnung": "A", "Huettenliste": "{abc-1},{DEF-2}"}},
        {"attributes": {"Bezeichnung": "B", "Huettenliste": ""}},
        {"attributes": {"Bezeichnung": None, "Huettenliste": None}},
    ]}
    tours = fetch_tours.parse_tours(payload)
    assert tours[0] == {"name": "A", "guids": ["{ABC-1}", "{DEF-2}"]}
    assert tours[1]["guids"] == []
    assert tours[2] == {"name": None, "guids": []}


def test_calendar_body_and_urls():
    body = fetch_calendars.calendar_body(date(2025, 5, 1), date(2025, 10, 31))
    assert body == {"arrivalDate": "01.05.2025", "departureDate": "31.10.2025",
                    "nextPossibleReservations": False, "numberOfPeople": 1}
    assert fetch_calendars.calendar_url(179).endswith("/api/v1/reservation/availabilityCalendar/179")
    assert fetch_capacity.info_url(179).endswith("/api/v1/reservation/hutInfo/179")
```

- [ ] **Step 2: Run, expect fail**

Run: `cd analysis/tour-huts && pixi run pytest tests/test_fetch.py -q`
Expected: FAIL `ModuleNotFoundError: fetch_tours`.

- [ ] **Step 3: Implement**

`fetch_tours.py`:

```python
"""Fetches the Alpenverein tour catalogue (26 tours) into raw/tours.json."""
from __future__ import annotations

import argparse
import re

import common


def parse_tours(payload: dict) -> list[dict]:
    """Tours as {name, guids}; GUIDs keep their braces and are upper-cased."""
    tours = []
    for feat in payload.get("features", []):
        a = feat["attributes"]
        guids = [g.upper() for g in re.findall(r"\{[^}]+\}", a.get("Huettenliste") or "")]
        tours.append({"name": a.get("Bezeichnung") or None, "guids": guids})
    return tours


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args(argv)
    path = common.OUT / "raw" / "tours.json"
    status = common.fetch_cached(
        path, lambda: common.request_json(common.TOURS_URL, method="POST"), args.refresh)
    print(f"tours: {status}")
    if status == "error":
        raise SystemExit(common.read_json(path)["error"])


if __name__ == "__main__":
    main()
```

`fetch_capacity.py`:

```python
"""Fetches hutInfo (capacity, coordinates) for every hut in scope."""
from __future__ import annotations

import argparse
from collections import Counter

import common


def info_url(ohrs_id: int) -> str:
    return f"{common.OHRS}/api/v1/reservation/hutInfo/{ohrs_id}"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args(argv)
    feats = common.read_json(common.HUTS_GEOJSON)["features"]
    ids = common.hut_scope(feats)
    counts: Counter = Counter()
    for i in ids:
        path = common.OUT / "raw" / "hut-info" / f"{i}.json"
        counts[common.fetch_cached(path, lambda i=i: common.request_json(info_url(i)), args.refresh)] += 1
    print(f"hut-info for {len(ids)} huts: {dict(counts)}")


if __name__ == "__main__":
    main()
```

`fetch_calendars.py`:

```python
"""Fetches the per-day availability calendar of every hut in scope, one file per hut and season."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date

import common


def calendar_url(ohrs_id: int) -> str:
    return f"{common.OHRS}/api/v1/reservation/availabilityCalendar/{ohrs_id}"


def calendar_body(start: date, end: date) -> dict:
    return {"arrivalDate": common.fmt_date(start), "departureDate": common.fmt_date(end),
            "nextPossibleReservations": False, "numberOfPeople": 1}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--season", type=int, choices=sorted(common.SEASONS))
    args = ap.parse_args(argv)
    ids = common.hut_scope(common.read_json(common.HUTS_GEOJSON)["features"])
    for season in ([args.season] if args.season else sorted(common.SEASONS)):
        s = common.SEASONS[season]
        counts: Counter = Counter()
        for i in ids:
            path = common.OUT / "raw" / f"calendar-{season}" / f"{i}.json"
            fetch = lambda i=i: common.request_json(
                calendar_url(i), calendar_body(s.start, s.fetch_end))
            counts[common.fetch_cached(path, fetch, args.refresh)] += 1
        print(f"calendar {season} for {len(ids)} huts: {dict(counts)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run, expect pass**

Run: `cd analysis/tour-huts && pixi run pytest tests/test_fetch.py -q`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add analysis/tour-huts/fetch_tours.py analysis/tour-huts/fetch_capacity.py analysis/tour-huts/fetch_calendars.py analysis/tour-huts/tests/test_fetch.py
git commit -m "feat(analysis): fetch scripts for tours, capacity and calendars

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: `approach_time.py` and `link_huts.py`

**Files:**
- Create: `analysis/tour-huts/approach_time.py`, `link_huts.py`
- Test: `analysis/tour-huts/tests/test_approach_time.py`, `test_link_huts.py`

**Interfaces:**
- Consumes: `common.*`, `fetch_tours.parse_tours`.
- Produces:
  - `approach_time.din_minutes(distance_m, ascent_m, descent_m) -> float`
  - `approach_time.approach_minutes(manifest: dict, blob: bytes, hut_ids: list[str]) -> dict[str, float]` (upper-case GUID → min minutes)
  - `link_huts.operator_of(tenant_code) -> "DAV" | "OEAV" | "other"` (5→DAV, 8→OEAV)
  - `link_huts.region_of(lon: float) -> "west" | "central" | "east"`
  - `link_huts.haversine_km(lat1, lon1, lat2, lon2) -> float`
  - `link_huts.parse_hut_info(rec: dict) -> dict` → `{"capacity": int|None, "capacity_sum": int|None, "lat": float|None, "lon": float|None}` from a stored record (`None`s when `ok` is false or fields missing)
  - `link_huts.link(features, tours, info, calendars, approach) -> dict` where `info: dict[int, dict]` and `calendars: dict[int, dict[int, dict]]` (`calendars[season][ohrs_id]` = stored record, absent if never fetched), `approach: dict[str, float]`. Returns `{"huts": [...], "unmatched_tour_guids": [...]}`. Hut entry keys: `ohrs_id, guids, names, on_tour, elevation (int|None), operator, serviced, lon, lat, capacity, capacity_sum, coord_km, coord_flag, region, approach_time_min (float|None), error (str|None)`.
  - Output file `OUT/huts.json`; `main()` reads raw files + `huts/public/data/{approaches.bin,approaches.json,hut-edge-payload.json}`.

`error` values: `"self_service"`, `"no_capacity: <msg>"`, `"calendar_error <season>: <msg>"`, `"calendar_missing <season>"`, `"calendar_empty <season>"`; first applicable wins in that order; else `None`.

- [ ] **Step 1: Write failing tests**

`tests/test_approach_time.py`:

```python
import json

import numpy as np

import approach_time


def test_din_minutes_matches_din_33466():
    # 4 km flat: t_h = 1 h, t_v = 0 -> 1 h
    assert approach_time.din_minutes(4000, 0, 0) == 60
    # 4 km, +300 m: t_h = 1, t_v = 1 -> 1 + 0.5 = 1.5 h
    assert approach_time.din_minutes(4000, 300, 0) == 90


def test_approach_minutes_takes_min_per_hut():
    hut_id = np.array([0, 0, 1], dtype="<u2")
    dist = np.array([4000, 2000, 8000], dtype="<f4")
    asc = np.zeros(3, dtype="<f4")
    desc = np.zeros(3, dtype="<f4")
    blob = b""
    cols = {}
    for name, arr in [("hut_id", hut_id), ("distance_m", dist), ("ascent_m", asc), ("descent_m", desc)]:
        cols[name] = {"dtype": arr.dtype.str.lstrip("<|"), "offset": len(blob)}
        blob += arr.tobytes()
    manifest = {"rows": 3, "columns": cols}
    out = approach_time.approach_minutes(manifest, blob, ["{aaa}", "{bbb}"])
    assert out == {"{AAA}": 30.0, "{BBB}": 120.0}
```

`tests/test_link_huts.py`:

```python
import link_huts


def feat(guid, name, ohrs, tenant=8, elev=2000, serviced=True, lon=11.0, lat=47.0):
    return {"properties": {"id": guid, "name": name, "ohrsHutId": ohrs, "tenantCode": tenant,
                           "elevation": elev, "serviced": serviced},
            "geometry": {"coordinates": [lon, lat]}}


def cal(n=20):
    return {"ok": True, "body": [{"date": "01.07.2025", "dayOfWeek": "TUESDAY",
                                   "freePlace": 3, "hutStatus": "SERVICED"}] * n}


INFO_OK = {"ok": True, "body": {"totalBedsInfo": "60", "coordinates": "47.0, 11.0",
                                "hutBedCategories": [{"totalSleepingPlaces": 37}, {"totalSleepingPlaces": 23}]}}


def run(features, tours=None, info=None, calendars=None, approach=None):
    tours = tours if tours is not None else []
    return link_huts.link(features, tours, info or {}, calendars or {2025: {}, 2026: {}}, approach or {})


def test_shared_ohrs_id_is_one_hut_and_tour_if_either_guid_on_tour():
    feats = [feat("{A}", "Eingang", "73"), feat("{B}", "Anger", "73")]
    out = run(feats, tours=[{"name": "T", "guids": ["{B}"]}],
              info={73: link_huts.parse_hut_info(INFO_OK)},
              calendars={2025: {73: cal()}, 2026: {73: cal()}})
    assert len(out["huts"]) == 1
    h = out["huts"][0]
    assert h["guids"] == ["{A}", "{B}"] and h["on_tour"] is True and h["error"] is None
    assert h["capacity"] == 60 and h["capacity_sum"] == 60


def test_unmatched_tour_guids_are_listed_and_tour_matching_is_case_insensitive():
    feats = [feat("{a1}", "X", "1")]
    out = run(feats, tours=[{"name": "T", "guids": ["{A1}", "{ZZ}"]}])
    assert out["unmatched_tour_guids"] == ["{ZZ}"]
    assert out["huts"][0]["on_tour"] is True


def test_errors_exclude_hut_with_reason():
    feats = [feat("{A}", "self", "1", serviced=False), feat("{B}", "nocap", "2"),
             feat("{C}", "calerr", "3"), feat("{D}", "calmissing", "4"), feat("{E}", "empty", "5")]
    info = {i: link_huts.parse_hut_info(INFO_OK) for i in (1, 3, 4, 5)}
    info[2] = link_huts.parse_hut_info({"ok": False, "error": "HTTP 404"})
    cals = {2025: {1: cal(), 3: {"ok": False, "error": "HTTP 500"}, 5: {"ok": True, "body": []}},
            2026: {1: cal(), 3: cal(), 4: cal(), 5: cal()}}
    err = {h["ohrs_id"]: h["error"] for h in run(feats, info=info, calendars=cals)["huts"]}
    assert err[1] == "self_service"
    assert err[2].startswith("no_capacity")
    assert err[3].startswith("calendar_error 2025")
    assert err[4] == "calendar_missing 2025"
    assert err[5] == "calendar_empty 2025"


def test_elevation_zero_is_missing_operator_and_region():
    feats = [feat("{A}", "a", "1", tenant=5, elev=0, lon=9.0), feat("{B}", "b", "2", tenant=3, lon=13.0)]
    hs = {h["ohrs_id"]: h for h in run(feats)["huts"]}
    assert hs[1]["elevation"] is None and hs[1]["operator"] == "DAV" and hs[1]["region"] == "west"
    assert hs[2]["operator"] == "other" and hs[2]["region"] == "east"
    assert link_huts.operator_of(8) == "OEAV"
    assert link_huts.region_of(11.0) == "central"


def test_coord_check_flags_over_1km():
    far = {"ok": True, "body": {"totalBedsInfo": "10", "coordinates": "47.1, 11.0", "hutBedCategories": []}}
    h = run([feat("{A}", "a", "1")], info={1: link_huts.parse_hut_info(far)})["huts"][0]
    assert h["coord_flag"] is True and h["coord_km"] > 10
    near = link_huts.parse_hut_info(INFO_OK)
    h = run([feat("{A}", "a", "1")], info={1: near})["huts"][0]
    assert h["coord_flag"] is False


def test_approach_time_is_min_over_guids():
    feats = [feat("{a}", "a", "73"), feat("{b}", "b", "73")]
    h = run(feats, approach={"{A}": 90.0, "{B}": 45.0})["huts"][0]
    assert h["approach_time_min"] == 45.0


def test_parse_hut_info_error_record():
    assert link_huts.parse_hut_info({"ok": False, "error": "x"})["capacity"] is None
```

- [ ] **Step 2: Run, expect fail**

Run: `cd analysis/tour-huts && pixi run pytest tests/test_approach_time.py tests/test_link_huts.py -q`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `approach_time.py`**

```python
"""Shortest approach duration per hut from the app's approaches.bin/.json outputs."""
from __future__ import annotations

import numpy as np


def din_minutes(distance_m: float, ascent_m: float, descent_m: float) -> float:
    """DIN 33466 duration in minutes (same formula as pipeline/lib/speed.py din_duration_h)."""
    t_h = distance_m / 4000.0
    t_v = ascent_m / 300.0 + descent_m / 500.0
    return (max(t_h, t_v) + min(t_h, t_v) / 2.0) * 60.0


def _col(manifest: dict, blob: bytes, name: str) -> np.ndarray:
    c = manifest["columns"][name]
    return np.frombuffer(blob, dtype="<" + c["dtype"], count=manifest["rows"], offset=c["offset"])


def approach_minutes(manifest: dict, blob: bytes, hut_ids: list[str]) -> dict[str, float]:
    """Upper-case hut GUID -> minimum approach minutes over all its approach rows."""
    hut = _col(manifest, blob, "hut_id")
    dist = _col(manifest, blob, "distance_m").astype(float)
    asc = _col(manifest, blob, "ascent_m").astype(float)
    desc = _col(manifest, blob, "descent_m").astype(float)
    t_h = dist / 4000.0
    t_v = asc / 300.0 + desc / 500.0
    minutes = (np.maximum(t_h, t_v) + np.minimum(t_h, t_v) / 2.0) * 60.0
    out: dict[str, float] = {}
    for idx, m in zip(hut.tolist(), minutes.tolist()):
        g = hut_ids[idx].upper()
        out[g] = min(m, out.get(g, m))
    return out
```

- [ ] **Step 4: Implement `link_huts.py`**

```python
"""Joins geojson huts, tours, hutInfo, calendars and approach times into huts.json (one entry per ohrsHutId)."""
from __future__ import annotations

import math
import re

import common
import fetch_tours
from approach_time import approach_minutes

COORD_FLAG_KM = 1.0
OPERATORS = {5: "DAV", 8: "OEAV"}


def operator_of(tenant_code) -> str:
    return OPERATORS.get(tenant_code, "other")


def region_of(lon: float) -> str:
    if lon < 10.5:
        return "west"
    return "central" if lon < 12.5 else "east"


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def parse_hut_info(rec: dict) -> dict:
    """Capacity, category-sum capacity and coordinates from a stored hutInfo record."""
    empty = {"capacity": None, "capacity_sum": None, "lat": None, "lon": None, "error": rec.get("error")}
    if not rec.get("ok"):
        return empty
    b = rec["body"]
    out = dict(empty, error=None)
    try:
        out["capacity"] = int(b["totalBedsInfo"])
    except (KeyError, TypeError, ValueError):
        out["error"] = "totalBedsInfo missing"
    cats = b.get("hutBedCategories") or []
    if cats:
        out["capacity_sum"] = sum(int(c.get("totalSleepingPlaces") or 0) for c in cats)
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", b.get("coordinates") or "")
    if m:
        out["lat"], out["lon"] = float(m.group(1)), float(m.group(2))
    return out


def _calendar_error(ohrs_id: int, calendars: dict) -> str | None:
    for season in sorted(calendars):
        rec = calendars[season].get(ohrs_id)
        if rec is None:
            return f"calendar_missing {season}"
        if not rec.get("ok"):
            return f"calendar_error {season}: {rec.get('error')}"
        if not rec["body"]:
            return f"calendar_empty {season}"
    return None


def link(features, tours, info, calendars, approach) -> dict:
    tour_guids = {g for t in tours for g in t["guids"]}
    geojson_guids = {f["properties"]["id"].upper() for f in features}
    by_id: dict[int, list[dict]] = {}
    for f in features:
        if f["properties"].get("ohrsHutId"):
            by_id.setdefault(int(f["properties"]["ohrsHutId"]), []).append(f)
    huts = []
    for ohrs_id in sorted(by_id):
        fs = by_id[ohrs_id]
        props = [f["properties"] for f in fs]
        guids = [p["id"] for p in props]
        lons = [f["geometry"]["coordinates"][0] for f in fs]
        lats = [f["geometry"]["coordinates"][1] for f in fs]
        lon, lat = sum(lons) / len(lons), sum(lats) / len(lats)
        i = info.get(ohrs_id) or parse_hut_info({"ok": False, "error": "hut-info missing"})
        coord_km = (haversine_km(lat, lon, i["lat"], i["lon"])
                    if i["lat"] is not None else None)
        serviced = any(p.get("serviced") for p in props)
        if not serviced:
            error = "self_service"
        elif i["capacity"] is None or i["capacity"] <= 0:
            error = f"no_capacity: {i['error']}"
        else:
            error = _calendar_error(ohrs_id, calendars)
        times = [approach[g.upper()] for g in guids if g.upper() in approach]
        elev = props[0].get("elevation") or None
        huts.append({
            "ohrs_id": ohrs_id, "guids": guids, "names": [p["name"] for p in props],
            "on_tour": any(g.upper() in tour_guids for g in guids),
            "elevation": elev, "operator": operator_of(props[0].get("tenantCode")),
            "serviced": serviced, "lon": lon, "lat": lat,
            "capacity": i["capacity"], "capacity_sum": i["capacity_sum"],
            "coord_km": coord_km, "coord_flag": coord_km is not None and coord_km > COORD_FLAG_KM,
            "region": region_of(lon), "approach_time_min": min(times) if times else None,
            "error": error,
        })
    return {"huts": huts, "unmatched_tour_guids": sorted(tour_guids - geojson_guids)}


def main(argv=None) -> None:
    raw = common.OUT / "raw"
    feats = common.read_json(common.HUTS_GEOJSON)["features"]
    tours_rec = common.read_json(raw / "tours.json")
    tours = fetch_tours.parse_tours(tours_rec["body"])
    info = {}
    for p in (raw / "hut-info").glob("*.json"):
        info[int(p.stem)] = parse_hut_info(common.read_json(p))
    calendars = {}
    for season in common.SEASONS:
        calendars[season] = {int(p.stem): common.read_json(p)
                             for p in (raw / f"calendar-{season}").glob("*.json")}
    data = common.ROOT / "huts" / "public" / "data"
    manifest = common.read_json(data / "approaches.json")
    hut_ids = common.read_json(data / "hut-edge-payload.json")["hut_ids"]
    approach = approach_minutes(manifest, (data / "approaches.bin").read_bytes(), hut_ids)
    out = link(feats, tours, info, calendars, approach)
    common.write_json(common.OUT / "huts.json", out)
    excluded = [h for h in out["huts"] if h["error"]]
    print(f"{len(out['huts'])} huts, {len(excluded)} excluded, "
          f"{len(out['unmatched_tour_guids'])} unmatched tour GUIDs, "
          f"{sum(h['coord_flag'] for h in out['huts'])} coordinate flags")


if __name__ == "__main__":
    main()
```

Note: `main()` in `link_huts.py` filters `calendars` by files present, so a hut whose fetch was never attempted shows `calendar_missing`.

- [ ] **Step 5: Run, expect pass**

Run: `cd analysis/tour-huts && pixi run pytest tests -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add analysis/tour-huts/approach_time.py analysis/tour-huts/link_huts.py analysis/tour-huts/tests/test_approach_time.py analysis/tour-huts/tests/test_link_huts.py
git commit -m "feat(analysis): link huts, tours, capacity and approach times

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: `hutdays.py` and `build_hut_days.py`

**Files:**
- Create: `analysis/tour-huts/hutdays.py`, `build_hut_days.py`
- Test: `analysis/tour-huts/tests/test_hutdays.py`

**Interfaces:**
- Consumes: `common.*`
- Produces (`hutdays.py`):
  - `MIN_OPEN_DAYS = 14`, `SOLD_OUT_NEAR = 0.05`
  - `hut_days(rows: list[dict], capacity: int, ohrs_id: int, start: date, end: date) -> pd.DataFrame` — columns `ohrs_id, date, status, open, free_place, capacity, free_above_capacity, occupancy, sold_out, sold_out_near` (`occupancy` is NaN on closed days; always filter on `open`).
  - `CUTS: dict[str, Callable[[pd.Series], pd.Series] | None]` keys `season`, `jul_aug`, `fri_sun` (mask over a `date` column of Python dates).
  - `hut_season(days: pd.DataFrame, cut: str = "season") -> dict` keys: `open_days, eligible, no_activity, capacity_mismatch, cut_open_days, occupancy, sold_out_days, sold_out_share, sold_out_near_days, sold_out_near_share`. `open_days`, `eligible`, `no_activity`, `capacity_mismatch` always from the full season; the outcome columns only from the cut's days (NaN shares when the cut has no open days).
  - `season_table(huts: list[dict], days: pd.DataFrame, season: int, cut: str = "season") -> pd.DataFrame` one row per non-excluded hut (`error is None`): hut attributes `ohrs_id, on_tour (0/1 int as "tour"), elevation, capacity, operator, region, approach_time_min` + `season` + `hut_season` columns. Column for the tour flag is named `tour` (int 0/1).
- `build_hut_days.py` writes `OUT/hut-days.csv` (all seasons, columns above + `season`) and prints status counts.

- [ ] **Step 1: Write failing tests**

`tests/test_hutdays.py`:

```python
from datetime import date

import pandas as pd

import hutdays

D0 = date(2025, 7, 1)


def rows(frees, status="SERVICED", start_day=1):
    return [{"date": f"{start_day + i:02d}.07.2025", "dayOfWeek": "X", "freePlace": f, "hutStatus": status}
            for i, f in enumerate(frees)]


def days_of(frees, cap=10, status="SERVICED"):
    return hutdays.hut_days(rows(frees, status), cap, 1, date(2025, 5, 1), date(2025, 10, 31))


def test_fully_booked_day_is_occupancy_one_and_sold_out():
    d = days_of([0, 10, 5])
    assert list(d.occupancy) == [1.0, 0.0, 0.5]
    assert list(d.sold_out) == [True, False, False]


def test_closed_day_is_not_open_and_has_no_occupancy():
    d = days_of([10, 3], status="CLOSED")
    assert not d.open.any() and d.occupancy.isna().all()


def test_free_above_capacity_flagged_and_clamped():
    d = days_of([12, 5])
    assert list(d.free_above_capacity) == [True, False]
    assert d.occupancy.iloc[0] == 0.0


def test_sold_out_near_uses_five_percent():
    d = hutdays.hut_days(rows([5, 6]), 100, 1, date(2025, 5, 1), date(2025, 10, 31))
    assert list(d.sold_out_near) == [True, False]


def test_days_outside_season_are_clipped():
    d = hutdays.hut_days(rows([1, 1, 1]), 10, 1, date(2025, 7, 2), date(2025, 7, 2))
    assert len(d) == 1


def test_eligibility_uses_open_day_count_only():
    few = hutdays.hut_season(days_of([0] * 13), "season")
    many = hutdays.hut_season(days_of([0] * 14), "season")
    assert few["eligible"] is False and many["eligible"] is True
    # bookings identical, eligibility differs only by open days
    assert few["occupancy"] == many["occupancy"] == 1.0


def test_no_activity_when_constant_free_place():
    assert hutdays.hut_season(days_of([10] * 20), "season")["no_activity"] is True
    assert hutdays.hut_season(days_of([10] * 19 + [9]), "season")["no_activity"] is False


def test_always_sold_out_hut_is_not_no_activity():
    assert hutdays.hut_season(days_of([0] * 20), "season")["no_activity"] is False


def test_capacity_mismatch_flag():
    assert hutdays.hut_season(days_of([11] + [5] * 19), "season")["capacity_mismatch"] is True


def test_cuts_filter_outcome_but_not_eligibility():
    d = days_of([0] * 31 + [10] * 0)  # 1..31 July, all sold out
    s = hutdays.hut_season(d, "fri_sun")
    assert s["open_days"] == 31 and s["eligible"]
    assert 0 < s["cut_open_days"] < 31
    assert s["sold_out_share"] == 1.0
    aug = hutdays.hut_season(d, "jul_aug")
    assert aug["cut_open_days"] == 31


def test_season_table_excludes_errors_and_shapes_columns():
    huts = [
        {"ohrs_id": 1, "on_tour": True, "elevation": 2000, "capacity": 10, "operator": "DAV",
         "region": "west", "approach_time_min": 30.0, "error": None},
        {"ohrs_id": 2, "on_tour": False, "elevation": None, "capacity": 10, "operator": "OEAV",
         "region": "east", "approach_time_min": None, "error": "self_service"},
    ]
    days = days_of([5] * 20)
    t = hutdays.season_table(huts, days, 2025)
    assert list(t.ohrs_id) == [1] and t.tour.iloc[0] == 1 and t.season.iloc[0] == 2025
    assert t.occupancy.iloc[0] == 0.5
```

- [ ] **Step 2: Run, expect fail**

Run: `cd analysis/tour-huts && pixi run pytest tests/test_hutdays.py -q`
Expected: FAIL `ModuleNotFoundError: hutdays`.

- [ ] **Step 3: Implement `hutdays.py`**

```python
"""Per-day and per-hut-season booking metrics from OHRS availability calendars."""
from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd

MIN_OPEN_DAYS = 14
SOLD_OUT_NEAR = 0.05

CUTS = {
    "season": None,
    "jul_aug": lambda d: d.map(lambda x: x.month in (7, 8)),
    "fri_sun": lambda d: d.map(lambda x: x.weekday() >= 4),
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
```

- [ ] **Step 4: Implement `build_hut_days.py`**

```python
"""Builds hut-days.csv (one row per hut and calendar day, all seasons) from raw calendars."""
from __future__ import annotations

from collections import Counter

import pandas as pd

import common
import hutdays


def main(argv=None) -> None:
    huts = common.read_json(common.OUT / "huts.json")["huts"]
    frames = []
    statuses: Counter = Counter()
    for season, s in common.SEASONS.items():
        for h in huts:
            if h["error"]:
                continue
            rec = common.read_json(common.OUT / "raw" / f"calendar-{season}" / f"{h['ohrs_id']}.json")
            statuses.update(r["hutStatus"] for r in rec["body"])
            df = hutdays.hut_days(rec["body"], h["capacity"], h["ohrs_id"], s.start, s.end)
            df.insert(1, "season", season)
            frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(common.OUT / "hut-days.csv", index=False)
    print(f"{len(out)} hut-days; hutStatus values: {dict(statuses)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run, expect pass**

Run: `cd analysis/tour-huts && pixi run pytest tests -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add analysis/tour-huts/hutdays.py analysis/tour-huts/build_hut_days.py analysis/tour-huts/tests/test_hutdays.py
git commit -m "feat(analysis): hut-day and hut-season booking metrics

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: `stats.py`

**Files:**
- Create: `analysis/tour-huts/stats.py`
- Test: `analysis/tour-huts/tests/test_stats.py`

**Interfaces:**
- Consumes: season-table DataFrames from `hutdays.season_table` (columns `tour, elevation, capacity, operator, region, approach_time_min, open_days, cut_open_days, occupancy, sold_out_share, sold_out_near_share, sold_out_days, sold_out_near_days`).
- Produces:
  - `bootstrap_diff(a, b, n=5000, seed=0) -> dict` `{"diff","lo","hi"}` (percentile 95% CI on mean(a) − mean(b))
  - `bootstrap_mean(x, n=5000, seed=0) -> dict` `{"mean","lo","hi"}`
  - `min_detectable_diff(n1, n2, sd, alpha=0.05, power=0.8) -> float`
  - `fit_ols(df, outcome) -> dict` `{"coef","lo","hi","p","n","n_dropped"}`; formula `{outcome} ~ tour + elevation + np.log(capacity) + C(operator) + C(region) + approach_time_min + open_days`, HC3 robust errors
  - `fit_glm(df, success_col, trials_col="cut_open_days") -> dict` `{"coef","lo","hi","p","odds_ratio","n","n_dropped"}` binomial logit, HC1 robust errors, same covariates
  - `match_pairs(df, outcome, k=3) -> dict` `{"n_tour","n_unmatched","paired": DataFrame(ohrs_id, diff, n_matches)}`; distance = Euclidean over z-scored `elevation`, `log(capacity)`, `open_days` (z-scored over all rows), candidates = non-tour rows with the same `operator`; tour huts with NaN in any matching variable or no candidate count as unmatched
  - `replicated(r1: dict, r2: dict) -> bool` for dicts with `coef, lo, hi`: same sign of coef and intervals overlap

- [ ] **Step 1: Write failing tests**

`tests/test_stats.py`:

```python
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
```

- [ ] **Step 2: Run, expect fail**

Run: `cd analysis/tour-huts && pixi run pytest tests/test_stats.py -q`
Expected: FAIL `ModuleNotFoundError: stats`.

- [ ] **Step 3: Implement `stats.py`**

```python
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
    z = (d[vars_] - d[vars_].mean()) / d[vars_].std(ddof=0)
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
    return (np.sign(r1["coef"]) == np.sign(r2["coef"])
            and max(r1["lo"], r2["lo"]) <= min(r1["hi"], r2["hi"]))
```

- [ ] **Step 4: Run, expect pass**

Run: `cd analysis/tour-huts && pixi run pytest tests -q`
Expected: all pass. If `test_ols_drops_rows_with_missing_covariates` fails on `n_dropped` because patsy drops differently, fix `_complete` (it drops before fit so this should hold).

- [ ] **Step 5: Commit**

```bash
git add analysis/tour-huts/stats.py analysis/tour-huts/tests/test_stats.py
git commit -m "feat(analysis): bootstrap, OLS, GLM, matching and power routines

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: `analyze.py` specs and results

**Files:**
- Create: `analysis/tour-huts/analyze.py`
- Test: `analysis/tour-huts/tests/test_analyze.py`

**Interfaces:**
- Consumes: `hutdays.season_table`, `hutdays.CUTS`, `stats.*`, `common.*`
- Produces:
  - `OUTCOMES = {"occupancy": ("ols", None), "sold_out": ("glm", "sold_out_days"), "sold_out_near": ("glm", "sold_out_near_days")}`; share column of an outcome: `occupancy` → `occupancy`, `sold_out` → `sold_out_share`, `sold_out_near` → `sold_out_near_share` (`share_col(outcome)`).
  - `select(table, variant) -> DataFrame`; variants: `"primary"` (eligible, not no_activity, not capacity_mismatch), `"incl_no_activity"` (eligible, not mismatch), `"incl_mismatch"` (eligible, not no_activity). Rows with NaN outcome are dropped by `run_spec`.
  - `run_spec(table, outcome) -> dict` keys: `n_tour, n_other, mean_tour, mean_other, sd, mde` (computed first, before any tour-effect model), `raw` (`bootstrap_diff`), `model` (`fit_ols`/`fit_glm`), `matched` `{n_tour, n_unmatched, mean, lo, hi}` (`bootstrap_mean` of paired diffs; `None` values if no pairs). Returns `{"skipped": reason}` if either group has < 5 huts.
  - `consistency(new_days: pd.DataFrame, old: dict, ids_by_guid: dict) -> dict` compares `free_place` with old proxy totals; returns `{"days_compared", "days_off_by_more_than_1", "huts"}`.
  - `main()` writes `OUT/results.json` and `OUT/plots/*.png`.
- `results.json` layout: `{"primary": {...run_spec season 2025 whole occupancy...}, "specs": {"<season>|<cut>|<outcome>|<variant>": {...}}, "replication": {"occupancy": bool, ...}, "coverage": [...], "no_activity_share": [...], "excluded": {"tour": n, "other": n, "reasons": {...}}, "unmatched_tour_guids": [...], "coord_flags": [...], "consistency": {...}, "approach_missing": n, "regions": {...}}`.
- Spec grid: seasons {2025, 2026} × cuts {season, jul_aug, fri_sun} × outcomes {occupancy, sold_out, sold_out_near} × variant `primary`; plus, for season 2025 / cut `season` only, variants `incl_no_activity` and `incl_mismatch` for `occupancy` and `sold_out`.
- Old proxy file format (`data/analysis/hut-availability-raw.json`): `huts[guid] = {"ohrsHutId", "responses": [{"ok", "body": [{"hutsAvailability": [{"calendarDays": [{"day": "DD.MM.YYYY", "status", "bedCategoriesData": [{"totalFreePlaces"}]}]}]}]}]}`.

- [ ] **Step 1: Write failing tests**

`tests/test_analyze.py`:

```python
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
```

Note: the consistency test uses days beyond 23.09.2026, so `hut-days.csv` (clipped to the season end) cannot supply them. `consistency` therefore receives raw-calendar-derived days: `main()` builds `new_days` from `raw/calendar-2026/{id}.json` with `hutdays.hut_days(rows, cap, id, date(2026,9,23), date(2026,10,10))` (a separate window), not from `hut-days.csv`.

- [ ] **Step 2: Run, expect fail**

Run: `cd analysis/tour-huts && pixi run pytest tests/test_analyze.py -q`
Expected: FAIL `ModuleNotFoundError: analyze`.

- [ ] **Step 3: Implement `analyze.py`**

```python
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
        mine = new_days[new_days.ohrs_id == int(h["ohrs_id"] if "ohrs_id" in h else h["ohrsHutId"])]
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
```

Fix in `consistency`: the old file key is `ohrsHutId`. Simplify the line to `int(h["ohrsHutId"])` after writing (the ternary above is unnecessary) — do this edit in Step 4.

- [ ] **Step 4: Simplify the id lookup**

In `consistency`, replace
`mine = new_days[new_days.ohrs_id == int(h["ohrs_id"] if "ohrs_id" in h else h["ohrsHutId"])]`
with
`mine = new_days[new_days.ohrs_id == int(h["ohrsHutId"])]`.

The test fixture (`old_file`) uses `"ohrsHutId": 7`, matching.

- [ ] **Step 5: Run, expect pass**

Run: `cd analysis/tour-huts && pixi run pytest tests -q`
Expected: all pass. `matplotlib`'s `boxplot(tick_labels=...)` needs matplotlib ≥ 3.9; if the env's is older, use `labels=` instead (verified in Task 8).

- [ ] **Step 6: Commit**

```bash
git add analysis/tour-huts/analyze.py analysis/tour-huts/tests/test_analyze.py
git commit -m "feat(analysis): run study specs, validity checks and plots

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: README and API docs

**Files:**
- Create: `analysis/tour-huts/README.md`
- Modify: `docs/alpenverein-api.md` (append sections before "## 3. Other endpoints seen in the capture" or as a new section 2c; keep numbering consistent), `docs/superpowers/STATUS.md` (add row), `CLAUDE.md` (root; one paragraph)

- [ ] **Step 1: README**

`analysis/tour-huts/README.md`:

````markdown
# Tour-hut booking study

Are huts on official Alpenverein tours booked more than other huts? Design:
`docs/superpowers/specs/2026-09-23-tour-hut-booking-study-design.md`. Results: `docs/tour-hut-booking-analysis.md`.

Outputs go to `data/analysis/tour-huts/` (gitignored). This code is independent of `pipeline/` and doit.

```bash
cd analysis/tour-huts
pixi install
pixi run pytest                        # no network needed
pixi run python fetch_tours.py         # ~1 request
pixi run python fetch_capacity.py      # ~239 requests, 0.3 s apart
pixi run python fetch_calendars.py     # ~480 requests; --season 2025|2026, --refresh
pixi run python link_huts.py           # huts.json
pixi run python build_hut_days.py      # hut-days.csv
pixi run python analyze.py             # results.json, plots/
```

Fetch scripts skip files that already hold an ok record and retry error records. `--refresh` refetches all.
Requests need an explicit `User-Agent`: Python's default one gets HTTP 403.
````

- [ ] **Step 2: API docs**

Read `docs/alpenverein-api.md` lines 1–17 and 143–175 first, then insert, before `## 3.`, a new section:

````markdown
## 2c. OHRS direct API — availability calendar and hut info

Host `https://www.hut-reservation.org`, no auth, OpenAPI at `/v3/api-docs`. Python's default
`User-Agent` gets HTTP 403 (`curl` does not) — send an explicit one.

```
POST /api/v1/reservation/availabilityCalendar/{ohrsHutId}
{"arrivalDate":"DD.MM.YYYY","departureDate":"DD.MM.YYYY","nextPossibleReservations":false,"numberOfPeople":1}
```

Returns one row per day: `{"date","dayOfWeek","freePlace","hutStatus"}`; `hutStatus` is `SERVICED` or
`CLOSED`. Unlike the proxy in §2, it accepts past dates and a whole year in one request. History
shows the state now for a past date: cancellations are included, bookings made outside OHRS are not.
Summers before 2025 show maximum free places on every day (no bookings recorded).

```
GET /api/v1/reservation/hutInfo/{ohrsHutId}
```

Returns `totalBedsInfo` (string, current total beds), `hutBedCategories[].totalSleepingPlaces`,
`altitude`, `coordinates` (`"lat, lon"`), `tenantCode` (a string such as `OEAV`, not the numeric
`verein_nr`). Capacity is current only.
````

- [ ] **Step 3: STATUS and CLAUDE.md**

Append to the STATUS.md table (after the last row) a row:
`| 2026-09-23 | [Tour-hut booking study](specs/2026-09-23-tour-hut-booking-study-design.md) | in progress |`

In root `CLAUDE.md`, after the `pipeline/tours/` paragraph, add:

```markdown
`analysis/tour-huts/` (tracked, own pixi env, not part of the doit DAG) holds the tour-hut booking study
(`docs/superpowers/specs/2026-09-23-tour-hut-booking-study-design.md`); outputs go to gitignored
`data/analysis/tour-huts/`. Its fetch scripts call the public OHRS API (~700 requests), so run them only
with the user's go-ahead.
```

- [ ] **Step 4: Commit**

```bash
git add analysis/tour-huts/README.md docs/alpenverein-api.md docs/superpowers/STATUS.md CLAUDE.md
git commit -m "docs(analysis): document tour-hut study and OHRS calendar endpoints

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

Note: `docs/superpowers/STATUS.md` already has unrelated uncommitted changes in the working tree. Before `git add`, run `git diff docs/superpowers/STATUS.md`; if it holds edits that are not yours, use `git add -p` to stage only your row.

---

### Task 8: Run the fetch and the pipeline for real

**Files:** none tracked (writes `data/analysis/tour-huts/`).

**This task sends about 720 requests to a public third-party API. Ask the user for a go-ahead first.** Do not touch `pipeline/` or run `doit`.

- [ ] **Step 1: Fetch**

```bash
cd /home/superhellth/open-alps/analysis/tour-huts
pixi run python fetch_tours.py
pixi run python fetch_capacity.py
pixi run python fetch_calendars.py
```
Expected: `tours: ok`; `hut-info ... {'ok': N, ...}`; two calendar lines. A rerun must print only `cached` (plus retried errors). Error counts above ~20 per script: stop and inspect `raw/*/*.json` error strings (rate limit → raise `REQUEST_GAP_S`).

- [ ] **Step 2: Link and build**

```bash
pixi run python link_huts.py
pixi run python build_hut_days.py
```
Expected: about 239 huts (fewer if `ohrsHutId` is shared, e.g. 73), 5 unmatched tour GUIDs, only `SERVICED`/`CLOSED` statuses. If another status appears, decide whether it counts as open and update `hutdays.hut_days` plus a test.

- [ ] **Step 3: Sanity checks**

```bash
pixi run python - <<'E'
import json, common
d = common.read_json(common.OUT/"huts.json")
h = d["huts"]; ok = [x for x in h if not x["error"]]
print(len(h), len(ok), sum(x["on_tour"] for x in ok))
import collections
print(collections.Counter(x["region"] for x in ok))
print([x for x in h if x["capacity"] and x["capacity_sum"] and x["capacity"]!=x["capacity_sum"]][:5])
print([ (x["names"],x["coord_km"]) for x in h if x["coord_flag"]])
print(sum(x["approach_time_min"] is None for x in ok), "without approach")
E
```
Expected: each region ≥ 15 analysed huts. If a region has fewer, change `region_of` thresholds in `link_huts.py`, update `test_elevation_zero_is_missing_operator_and_region`, re-run Step 2.

- [ ] **Step 4: Analyze**

Run: `pixi run python analyze.py`
Expected: prints the primary result; `results.json` and two PNGs exist under `data/analysis/tour-huts/`. Fix any matplotlib API error (`tick_labels` vs `labels`). Look at both PNGs with the Read tool.

- [ ] **Step 5: Commit any fixes**

```bash
git add analysis/tour-huts
git commit -m "fix(analysis): adjust study code after first full run

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
Skip if nothing changed.

---

### Task 9: Write up results, close out

**Files:**
- Modify: `docs/tour-hut-booking-analysis.md` (rewrite), `docs/superpowers/STATUS.md`, `docs/superpowers/specs/2026-09-23-tour-hut-booking-study-design.md` (layout table row for calendars), `docs/backlog.md` if an item for this study exists
- Delete: `docs/superpowers/plans/2026-09-23-tour-hut-booking-study.md`

- [ ] **Step 1: Rewrite `docs/tour-hut-booking-analysis.md`**

Read `data/analysis/tour-huts/results.json` and the two plots. Write, in this order: conclusion (primary result with tour effect in percentage points, its 95% CI and the minimum detectable difference, phrased "no difference larger than X points" if the CI includes 0); replication verdict (2026 sign/overlap); data and coverage table (huts and open hut-days per group and season, share of no-activity huts, exclusions with reasons); results table over specs (raw diff, regression, matched, sold-out, cuts, sensitivity runs), each non-primary result labelled exploratory; validity checks (capacity mismatch, coordinate flags, past-data consistency count, booking-channel limit, missing approach times); limits; link to the spec and to `analysis/tour-huts/README.md`. Copy plots to nowhere (they stay in `data/`); describe them in text. Every number comes from `results.json`, never from memory. Drop the first analysis' obsolete conclusion; keep one line noting it was a 17-day pilot.

- [ ] **Step 2: Spec table row**

In the spec's Layout table change the `fetch_calendars.py` row's write column to `raw/calendar-{season}/{ohrsHutId}.json`, and add to the "Calendars" bullet under Data acquisition: "The 2026 request runs to 10.10.2026; the analysis clips at 23.09.2026, and the extra days feed the past-data consistency check."

- [ ] **Step 3: STATUS, plan, backlog**

- STATUS.md: flip the study's row to `done`.
- Delete this plan file (`git rm docs/superpowers/plans/2026-09-23-tour-hut-booking-study.md`).
- `grep -n -i "booking\|tour hut" docs/backlog.md`; remove the matching backlog item (and its `.md` file) if one exists.

- [ ] **Step 4: Full test run and commit**

```bash
cd analysis/tour-huts && pixi run pytest -q && cd ../..
git add docs/tour-hut-booking-analysis.md docs/superpowers/specs/2026-09-23-tour-hut-booking-study-design.md docs/superpowers/STATUS.md docs/backlog.md
git rm -q docs/superpowers/plans/2026-09-23-tour-hut-booking-study.md
git commit -m "docs(analysis): tour-hut booking study results

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
(`docs/backlog.md` and `STATUS.md` carry unrelated uncommitted edits: use `git add -p` for them.)

---

## Self-review

- **Spec coverage:** data acquisition (tours, capacity, calendars, load rules, error records) → Tasks 1–2. Linking (shared id, coordinate check, API errors, self-service, eligibility, no-activity) → Tasks 3–4. Metric (open/closed, clamp, sold-out, mismatch, 14-day rule) → Task 4. Analysis 1–6 (raw, OLS with controls, matched, sold-out GLM, cuts, replication) → Tasks 5–6. Validity checks (capacity drift, coverage, no-activity share, past-data consistency, multiple comparisons via single labelled primary, power/MDE computed before the tour model) → Task 6. Sensitivity runs (no-activity as 0, mismatch included, 5% sold-out) → Task 6 spec grid. Outputs, docs, STATUS → Tasks 7, 9. Tests listed in spec (full day, closed day, mismatch, shared id, eligibility, no activity, operator "other") → Tasks 3–4. Open items resolved in "File Structure".
- **Booking-channel "share of huts with booking activity per group"** is the `no_activity_share` output of Task 6.
- **Type consistency:** `season_table` column `tour` (int) is what `stats` uses; `hut_season` keys match `analyze.share_col`/`OUTCOMES`; `calendars[season][ohrs_id]` shape matches between `link_huts.main` and tests.
- **Deviations from spec, flagged:** per-hut calendar files; 2026 fetch runs to 10.10.2026; `no_activity` excludes a constant `freePlace == 0` (an always-sold-out hut is not an empty one); error records are retried on re-run rather than skipped.
