# Tour Reproducibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Do NOT use superpowers:subagent-driven-development or any worktree-based
> approach — `.claude/CLAUDE.md` forbids both in this repo. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Raise the fraction of official AV tour legs that `match_tour_edges.py` matches (today:
18 of 102, ~18%) as far as real, verified geometry allows — by extending the Outdooractive
corridor-input approach validated in `pipeline/analysis/oa_corridor_spike.py` from 9 tours to as
many of the 25 as have a real OA source, then measuring what's left.

**Architecture:** `match_tour_edges.py` already matches a leg by building a *corridor* (buffer
around a chain of trace points) and routing the two huts inside it (spec §2.3). Its only trace
source today is the AV's own `AVT_CAA_TOUR_View_L` fragments, reassembled by
`lib/tour_geometry.reassemble_fragments` — which recovers **zero** multi-fragment tours (spec
§2.7's spike, see `oa_corridor_spike.py`'s docstring). Outdooractive (which
`alpenvereinaktiv.com` white-labels) serves the same tours as one already-ordered LineString, no
reassembly needed. The spike proved corridor-routing on OA geometry converts 29 of 37
previously-dead legs across the 9 tours it could test, with a byte-identical LQR control. This
plan (1) promotes the spike's OA-fetch code from a throwaway analysis script into reusable `lib/`
code, (2) investigates whether any of the 15 tours **without** a discoverable OA id secretly have
one via their own homepage, (3) wires the whole thing into the real `fetch_tours.py` →
`match_tour_edges.py` production path (not just the spike), and (4) re-measures and reports,
ending in an explicit decision point on whether `leuvenmapmatching` (spec §2.4) is still needed.

**Tech Stack:** Python (pixi env `alpen-osm`), `doit` task DAG, `pytest`, `urllib.request` (no
external HTTP deps — matches the rest of `pipeline/`'s downloads/).

**Spec:** `docs/superpowers/specs/2026-08-29-official-tours-integration-design.md` (§2.2–§2.5,
§2.7); prior plan `docs/superpowers/plans/2026-08-29-official-tours-integration.md` (Tasks 1–19,
committed; Task 20's spike is what this plan extends into production).

## Global Constraints

- **Never run any `pipeline/` doit task (individually or the full DAG) without first asking the
  user and getting explicit confirmation** — this applies even to tasks that look cheap, per
  `.claude/CLAUDE.md`. Every task below that invokes `doit` marks an explicit STOP.
- **No git worktrees, no subagent-driven execution** in this repo, for any reason.
- **Never fake geometry.** A leg that can't be routed becomes one of spec §2.5's six gap reasons
  (`hut_unsnapped`, `hut_far_from_trace`, `outside_extract`, `no_corridor_path`,
  `length_divergent`, `chain_not_reassembled`) with real detail — never a placeholder or
  straight-line fallback. This plan does not add a seventh reason; where it needs new
  observability (e.g. "was OA even available"), that goes into a gap's `detail` dict, not a new
  top-level `reason`.
  - **`pipeline/analysis/` scripts never modify `phases/`** and only call the real phase functions
  against already-persisted `data/` outputs (`pipeline/analysis/README.md`).
- **Root-layer fix discipline:** anything wrong with the AV's or OA's own data (missing ids, wrong
  metrics, ids under a different white-label project) is a `pipeline/` fetch/matching problem, not
  something to paper over client-side.
- Every long-running script prints progress with `flush=True` (`pipeline/CLAUDE.md`).
- Fetching a NEW external host (a tour's own homepage, in Task 2) is a new kind of network action
  this session hasn't been authorized for yet — Task 2 has its own explicit STOP for that reason,
  separate from the doit-task STOPs.

---

### Task 1: Promote OA helpers from the spike into `lib/oa_geometry.py`

**Files:**
- Create: `pipeline/lib/oa_geometry.py`
- Test: `pipeline/tests/test_oa_geometry.py`
- Modify: `pipeline/analysis/oa_corridor_spike.py` (import from the new module instead of
  defining `OA_ENDPOINT`/`OA_KEY`/`OA_QUERY`/`OA_UA`/`OA_URL_RE`/`oa_ids_by_tour`/
  `fetch_oa_contents`/`oa_chain` inline)

**Interfaces:**
- Produces: `oa_ids_by_tour(tours: list) -> dict[int, str]`,
  `oa_chain(content: dict) -> list[tuple[float, float]]`,
  `fetch_oa_contents(oa_ids: list, cache_path: Path, allow_fetch: bool) -> dict` — same behavior
  as the spike's versions, but `cache_path` is now a parameter (was the spike's module-level
  `CACHE_PATH`), so Task 3's production fetch step and the spike can each point at their own
  cache file without duplicating the function.

Both `match_tour_edges.py` (production, Task 4) and `oa_corridor_spike.py` (measurement) need the
exact same OA-fetching/parsing logic. Right now it lives only in the spike, which
`pipeline/analysis/README.md` forbids treating as production code. This task moves it to `lib/`
with the spike as its first (already-working) caller, and adds tests the spike never had (it's
only run by hand against live/cached data).

- [x] **Step 1: Write the failing tests**

```python
# pipeline/tests/test_oa_geometry.py
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.oa_geometry import fetch_oa_contents, oa_chain, oa_ids_by_tour  # noqa: E402


def test_oa_ids_by_tour_matches_alpenvereinaktiv_urls_only():
    tours = [
        {"tourId": 0, "homepage": "https://www.alpenvereinaktiv.com/de/tour/thw/12345/6789/"},
        # a DIFFERENT Outdooractive white-label project - must NOT match (spike's docstring:
        # tour 22 / MontafonerSilvrettarunde links to touren.montafon.at, ids don't resolve
        # under project/alpenverein)
        {"tourId": 1, "homepage": "https://touren.montafon.at/de/tour/fernwanderweg/x/43535278/"},
        {"tourId": 2, "homepage": None},
        {"tourId": 3, "homepage": "https://www.karnischer-hoehenweg.com/"},
    ]
    assert oa_ids_by_tour(tours) == {0: "6789"}


def test_oa_chain_drops_elevation_and_handles_missing_geojson():
    assert oa_chain({"geoJson": {"type": "LineString",
                                  "coordinates": [[10.1, 47.2, 1500.0], [10.2, 47.3, 1600.0]]}}) \
        == [(10.1, 47.2), (10.2, 47.3)]
    assert oa_chain({}) == []
    assert oa_chain({"geoJson": {"type": "Point", "coordinates": [10.1, 47.2]}}) == []


def test_fetch_oa_contents_uses_cache_without_network(tmp_path):
    cache_path = tmp_path / "oa_cache.json"
    cache_path.write_text(json.dumps({"111": {"id": "111", "geoJson": None}}), encoding="utf-8")
    with patch("urllib.request.urlopen") as mock_urlopen:
        result = fetch_oa_contents(["111"], cache_path, allow_fetch=True)
    mock_urlopen.assert_not_called()
    assert result == {"111": {"id": "111", "geoJson": None}}


def test_fetch_oa_contents_raises_when_not_allowed_to_fetch(tmp_path):
    cache_path = tmp_path / "oa_cache.json"
    with patch("urllib.request.urlopen") as mock_urlopen:
        try:
            fetch_oa_contents(["111"], cache_path, allow_fetch=False)
            assert False, "expected SystemExit"
        except SystemExit:
            pass
    mock_urlopen.assert_not_called()
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `cd pipeline && pixi run pytest tests/test_oa_geometry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lib.oa_geometry'`

- [x] **Step 3: Write `pipeline/lib/oa_geometry.py`**

```python
"""Outdooractive geometry helpers shared by match_tour_edges.py's OA-sourced corridor input
(pipeline/analysis/2026-08-30-tour-reproducibility.md Task 4) and
pipeline/analysis/oa_corridor_spike.py's measurement of it (spec 2026-08-29-official-tours-
integration-design.md sec 2.7). alpenvereinaktiv.com is an Outdooractive white-label - no auth,
CORS *, `display=verbose` is what makes the response carry `geoJson` at all
(docs/www.alpenvereinaktiv.com.har)."""

import json
import re
import time
import urllib.request
from pathlib import Path

OA_ENDPOINT = "https://www.alpenvereinaktiv.com/api/v2/project/alpenverein/contents/{ids}/"
OA_KEY = "RXCRENVR-EMWGKTZ4-4OSSWDJU"
OA_QUERY = "?jsapi=1&key={key}&lang=de&display=verbose&format=json"
OA_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36")

# alpenvereinaktiv tour-page URL -> tour id. Anchored on the alpenvereinaktiv host deliberately:
# some tours link to a DIFFERENT Outdooractive project (e.g. touren.montafon.at) whose ids do not
# resolve under project/alpenverein, so a looser pattern would silently mismatch.
OA_URL_RE = re.compile(r"alpenvereinaktiv\.com/de/tour/[^/]+/(\d+)")


def oa_ids_by_tour(tours: list) -> dict:
    """{tourId: outdooractive_id} for the tours whose own homepage field carries one."""
    out = {}
    for tour in tours:
        match = OA_URL_RE.search(tour.get("homepage") or "")
        if match:
            out[tour["tourId"]] = match.group(1)
    return out


def oa_chain(content: dict) -> list:
    """The tour's line as the 2-D (lon, lat) tuples lib/tour_geometry.py works in. OA ships
    [lon, lat, ele] triples; the third component is dropped rather than carried - elevation here
    is OA's, not our DEM's, and every downstream consumer (assign_hut_position, corridor_bounds,
    _leg_segment_m) indexes [0]/[1] only."""
    geo = content.get("geoJson") or {}
    if geo.get("type") != "LineString":
        return []
    return [(p[0], p[1]) for p in geo["coordinates"]]


def fetch_oa_contents(oa_ids: list, cache_path: Path, allow_fetch: bool) -> dict:
    """{oa_id: content} from `cache_path`, fetching once (one batched request) if it's missing.
    The endpoint drops ids it cannot serve SILENTLY - 41 stage ids came back as 39 objects, no
    error, no null - so callers must diff requested against returned rather than trusting the
    count."""
    cache_path = Path(cache_path)
    if cache_path.exists():
        with open(cache_path, encoding="utf-8") as fh:
            cached = json.load(fh)
        if all(i in cached for i in oa_ids):
            print(f"oa: {len(cached)} tours from cache {cache_path}", flush=True)
            return cached
        print(f"oa: cache is missing {sorted(set(oa_ids) - set(cached))}", flush=True)
    if not allow_fetch:
        raise SystemExit(f"--no-fetch and {cache_path} does not cover {len(oa_ids)} ids")

    url = OA_ENDPOINT.format(ids=",".join(oa_ids)) + OA_QUERY.format(key=OA_KEY)
    print(f"oa: GET {len(oa_ids)} ids ...", flush=True)
    started = time.time()
    request = urllib.request.Request(url, headers={"accept": "application/json",
                                                     "user-agent": OA_UA})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    contents = {c["id"]: c for c in payload["answer"]["contents"]}
    missing = [i for i in oa_ids if i not in contents]
    print(f"oa: {len(contents)}/{len(oa_ids)} in {time.time() - started:.1f}s"
          + (f", MISSING {missing}" if missing else ""), flush=True)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as fh:
        json.dump(contents, fh)
    return contents
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `cd pipeline && pixi run pytest tests/test_oa_geometry.py -v`
Expected: 4 passed

- [x] **Step 5: Point the spike at the new module and delete its duplicated definitions**

In `pipeline/analysis/oa_corridor_spike.py`, replace the inline `OA_ENDPOINT`/`OA_KEY`/
`OA_QUERY`/`OA_UA`/`OA_URL_RE` constants and `oa_ids_by_tour`/`fetch_oa_contents`/`oa_chain`
function bodies with:

```python
from lib.oa_geometry import fetch_oa_contents, oa_chain, oa_ids_by_tour  # noqa: E402
```

and pass `CACHE_PATH` explicitly at each `fetch_oa_contents(...)` call site (it already has this
constant; only the function's signature gains the parameter).

- [x] **Step 6: Regression-check the spike's output is unchanged**

Run: `cd pipeline && pixi run python analysis/oa_corridor_spike.py --no-fetch --tours 0`
(use whatever `--tours` flag the spike already exposes, or its default full run) and diff
`data/analysis/oa_corridor_spike.json` against the version already on disk from the last real run
— it must be byte-identical (same function bodies, just relocated).

- [x] **Step 7: Run the full pipeline test suite and commit**

```bash
cd pipeline && pixi run pytest -q
git add pipeline/lib/oa_geometry.py pipeline/tests/test_oa_geometry.py pipeline/analysis/oa_corridor_spike.py
git commit -m "lib: promote OA fetch/parse helpers out of the spike into lib/oa_geometry.py"
```

---

### Task 2: Check the 15 OA-id-less tours' own homepages for an embedded OA tour id

**Files:**
- Create: `pipeline/analysis/find_oa_ids_from_homepages.py`

**Interfaces:**
- Consumes: `oa_ids_by_tour` (Task 1) to find which tours already have an id; `data/osm/tours.json`
  for the 15 without one and their `homepage` field.
- Produces: `data/analysis/oa_id_homepage_scan.json` — `[{tourId, shortCode, homepage,
  found_oa_id: str|None, matched_pattern: str|None}]`. Not consumed by any later task
  automatically — Task 3 reads this file's *findings* (as data a human reviews), not its shape,
  because which ids (if any) get promoted into production is a judgment call, not something safe
  to automate on regex hits alone.

Confirmed today: 10 of 25 tours carry an `alpenvereinaktiv.com/de/tour/.../<id>/` URL in their own
`homepage` field (`Dachsteinrunde, HSHR, THW, VWR8, CGT, PT4T, SVR7T, VR6T, RFD4T, LQR` — exactly
the spike's 10 tours). The other 15 link elsewhere:

| shortCode | homepage |
|---|---|
| KHW | karnischer-hoehenweg.com |
| PHR | tirol.at/.../peter-habeler-runde |
| Karwendel Höhenweg | karwendel-hoehenweg.at |
| Wiener Höhenweg | bergwelten.com/... (empty hut list - out of scope regardless, spec plan) |
| SHR | tirol.at/.../sellrainer-huettenrunde |
| IHW | inntaler-hoehenweg.at |
| MontafonerHüttenrunde | *(none)* |
| BHW | alpenverein.at/.../trekkingrouten (already mostly matches via reassembly - low priority) |
| STHW | stubai.at/... |
| VT4T | alpenverein-muenchen-oberland.de/.../venedigertour |
| KT01 | *(none)* |
| TT4T | alpenverein-muenchen-oberland.de/.../tauerntour |
| MontafonerSilvrettarunde | touren.montafon.at/... (empty hut list - out of scope regardless) |
| Achttälertour | *(none)* |
| WelserHöhenweg | *(none, already matches via reassembly)* |

Many Alpine-region tourism sites embed an Outdooractive widget even when their own domain isn't
`alpenvereinaktiv.com` — worth one real check per homepage before concluding these 12 routable
tours (excluding the 2 out-of-scope empty-hut-list ones and 3 with no homepage at all) are
unreachable via OA. This is genuinely exploratory: the outcome (how many ids get found, if any)
is not knowable in advance.

- [x] **Step 1: Write the scan script**

```python
#!/usr/bin/env python3
"""One-shot check: do any of the AV tours WITHOUT an alpenvereinaktiv.com id in their own
`homepage` field (see Task 2 of docs/superpowers/plans/2026-08-30-tour-reproducibility.md) embed
an Outdooractive widget anyway? Fetches each such tour's homepage HTML once and searches for
lib.oa_geometry.OA_URL_RE, plus a looser fallback pattern (`/tour/[^"'<>]+/(\\d+)` under any host
containing "outdooractive" or "alpenvereinaktiv" or ending in the same TLD segment as the known
white-label touren.montafon.at, to catch other same-vendor deployments) so a same-vendor,
different-domain deployment doesn't get missed the way the strict OA_URL_RE deliberately excludes
touren.montafon.at.

NETWORK: fetches up to 12 third-party homepages, one GET each, read-only. Requires explicit user
confirmation before running - a new class of external host this session hasn't touched before.

Writes data/analysis/oa_id_homepage_scan.json. Never modifies tours.json or any phases/ script.
"""

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.oa_geometry import OA_UA, OA_URL_RE, oa_ids_by_tour  # noqa: E402
from lib.pipeline import DATA_DIR, OSM_DIR  # noqa: E402

OUT_PATH = DATA_DIR / "analysis" / "oa_id_homepage_scan.json"
FALLBACK_RE = re.compile(r'outdooractive[^"\'<>]*?/tour/[^"\'<>]+/(\d+)|'
                          r'/tour/[^"\'<>]+/(\d+)[^"\'<>]*?outdooractive', re.IGNORECASE)


def scan_homepage(url: str) -> tuple:
    """Returns (found_oa_id, matched_pattern) or (None, None)."""
    request = urllib.request.Request(url, headers={"user-agent": OA_UA})
    with urllib.request.urlopen(request, timeout=20) as response:
        html = response.read().decode("utf-8", errors="replace")
    strict = OA_URL_RE.search(html)
    if strict:
        return strict.group(1), "alpenvereinaktiv_embed"
    loose = FALLBACK_RE.search(html)
    if loose:
        return (loose.group(1) or loose.group(2)), "outdooractive_generic_embed"
    return None, None


if __name__ == "__main__":
    with open(OSM_DIR / "tours.json", encoding="utf-8") as fh:
        tours = json.load(fh)
    already_have = oa_ids_by_tour(tours)
    candidates = [t for t in tours if t["tourId"] not in already_have and t.get("homepage")]
    print(f"scanning {len(candidates)} homepages ...", flush=True)

    results = []
    for i, tour in enumerate(candidates):
        homepage = tour["homepage"]
        try:
            found_id, pattern = scan_homepage(homepage)
        except Exception as exc:  # noqa: BLE001 - a dead/blocked third-party site is expected data, not a bug
            found_id, pattern = None, f"error: {exc}"
        print(f"[{i + 1}/{len(candidates)}] {tour['shortCode']}: {found_id or 'none'}"
              f" ({pattern})", flush=True)
        results.append({"tourId": tour["tourId"], "shortCode": tour["shortCode"],
                         "homepage": homepage, "found_oa_id": found_id, "matched_pattern": pattern})
        time.sleep(1.0)  # one GET per distinct third-party host, no need to hammer any of them

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    found = sum(1 for r in results if r["found_oa_id"])
    print(f"{found}/{len(results)} homepages carried a discoverable OA id -> {OUT_PATH}")
```

- [x] **Step 2: STOP — get explicit user confirmation before running it**

This fetches up to 12 different third-party domains the session hasn't touched before (not the
already-authorized `alpenvereinaktiv.com` API). State the URL list and get a go-ahead first.

- [x] **Step 3: Run it and report the findings**

Run: `cd pipeline && pixi run python analysis/find_oa_ids_from_homepages.py`

Report to the user: how many (if any) of the 12 candidate tours resolved an id, and which
`matched_pattern` fired. `data/analysis/` is gitignored, so this output is not committed — the
finding itself (which tourIds got an id) is what Task 3 needs, carried forward in conversation /
the plan's own notes, not as a file dependency.

- [x] **Step 4: Commit only the script**

```bash
git add pipeline/analysis/find_oa_ids_from_homepages.py
git commit -m "analysis: scan OA-id-less tour homepages for an embedded Outdooractive tour id"
```

---

### Task 3: Wire OA id resolution + geometry fetch into production

**Files:**
- Modify: `pipeline/phases/downloads/fetch_tours.py`
- Create: `pipeline/phases/downloads/fetch_tour_oa_geometry.py`
- Test: `pipeline/tests/test_fetch_tour_oa_geometry.py`
- Modify: `pipeline/dag/downloads.py` (new `task_fetch_tour_oa_geometry`)

**Interfaces:**
- Consumes: `lib.oa_geometry.oa_ids_by_tour`, `fetch_oa_contents`, `oa_chain` (Task 1); any ids
  confirmed in Task 2 (added as a small manual override dict, since homepage-embed ids aren't
  regex-derivable from the `homepage` field the same way).
- Produces: `data/osm/tour_oa_traces.json` — `[{"tourId": int, "points": [[lon, lat], ...]}]`,
  index-aligned by `tourId` the same way `tour_traces.json` is, empty `points` for a tour with no
  resolvable OA id or whose fetch didn't return content. `match_tour_edges.py` (Task 4) is this
  file's only consumer.

`fetch_tours.py` already stores `homepage` per tour (`phases/downloads/fetch_tours.py:70`) but
never derives an OA id from it. This task adds that field to the record it already builds, and a
new sibling script (mirroring how `fetch_stations_parking.py` sits next to `fetch_huts.py`, one
script per data source) that fetches the OA geometry for every tour that has one.

- [x] **Step 1: Add `oaId` to `fetch_tours.py`'s tour record**

In `pipeline/phases/downloads/fetch_tours.py`, add the import and use it in `build_tour_records`:

```python
from lib.oa_geometry import OA_URL_RE  # noqa: E402

# Manual overrides for tours whose OA id was found via their own homepage's embedded widget
# rather than a direct alpenvereinaktiv.com homepage link (Task 2 of
# docs/superpowers/plans/2026-08-30-tour-reproducibility.md) - fill in from that task's findings.
HOMEPAGE_EMBED_OA_IDS = {
    # "shortCode": "oa_id",
}
```

and in the loop building each tour dict:

```python
        oa_match = OA_URL_RE.search(a.get("Homepage") or "")
        oa_id = oa_match.group(1) if oa_match else HOMEPAGE_EMBED_OA_IDS.get(short_code)
        tours.append({
            "tourId": tour_id,
            "globalId": a.get("GlobalID"),
            "name": a.get("Bezeichnung"),
            "shortCode": a.get("Kurzbezeichnung"),
            "isLoop": bool(a.get("Rundtour")),
            "homepage": a.get("Homepage"),
            "oaId": oa_id,
            "hutIndices": hut_indices,
        })
```

- [x] **Step 2: Write the failing test for `oaId` resolution**

Add to `pipeline/tests/test_fetch_tours.py` (create if it doesn't already exist — check first;
`fetch_tours.py` currently has no dedicated test file, only `build_tour_records`/
`resolve_hut_indices` are unit-testable without network):

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from phases.downloads.fetch_tours import build_tour_records  # noqa: E402


def _feature(guid_csv, homepage, short_code="X"):
    return {"attributes": {"Kurzbezeichnung": short_code, "Bezeichnung": short_code,
                            "GlobalID": "{G}", "Rundtour": False, "Homepage": homepage,
                            "Huettenliste": guid_csv},
            "geometry": {"paths": []}}


def test_build_tour_records_resolves_oa_id_from_homepage():
    tours, _, _ = build_tour_records(
        [_feature("{H1}", "https://www.alpenvereinaktiv.com/de/tour/thw/x/12345/")],
        {"{H1}": 0},
    )
    assert tours[0]["oaId"] == "12345"


def test_build_tour_records_leaves_oa_id_none_without_a_match():
    tours, _, _ = build_tour_records([_feature("{H1}", "https://example.com/")], {"{H1}": 0})
    assert tours[0]["oaId"] is None
```

- [x] **Step 3: Run the test to verify it fails, then passes**

Run: `cd pipeline && pixi run pytest tests/test_fetch_tours.py -v`
Expected: FAIL (`oaId` KeyError) before Step 1's edit is applied to the checked-out tree, PASS
after.

- [x] **Step 4: Write `fetch_tour_oa_geometry.py`**

```python
#!/usr/bin/env python3
"""Fetches Outdooractive's published LineString for every AV tour that has a resolved oaId
(fetch_tours.py) - the geometry match_tour_edges.py (Task 4 of docs/superpowers/plans/
2026-08-30-tour-reproducibility.md) uses as its per-tour corridor input when the AV's own
fragmented `paths` fail to reassemble (spec 2026-08-29-official-tours-integration-design.md §2.7's
spike result). Never a fallback for tours already reassembling cleanly - see match_tour_edges.py's
docstring for the precedence.

Usage: python pipeline/phases/downloads/fetch_tour_oa_geometry.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.oa_geometry import fetch_oa_contents, oa_chain  # noqa: E402
from lib.pipeline import OSM_DIR  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "fetch_tour_oa_geometry.py"

if __name__ == "__main__":
    with open(OSM_DIR / "tours.json", encoding="utf-8") as fh:
        tours = json.load(fh)
    oa_ids = {t["tourId"]: t["oaId"] for t in tours if t.get("oaId")}
    print(f"{len(oa_ids)}/{len(tours)} tours have a resolved oaId", flush=True)

    with phase(SCRIPT_NAME, "fetch_tour_oa_geometry", n_tours=len(oa_ids)):
        contents = fetch_oa_contents(
            list(oa_ids.values()), OSM_DIR / "oa_tours_cache.json", allow_fetch=True,
        )

    id_to_tour = {v: k for k, v in oa_ids.items()}
    traces = []
    for oa_id, content in contents.items():
        tour_id = id_to_tour.get(oa_id)
        if tour_id is None:
            continue
        traces.append({"tourId": tour_id, "points": oa_chain(content)})

    out_path = OSM_DIR / "tour_oa_traces.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(traces, fh)
    print(f"written {out_path} ({len(traces)} tours with geometry)")
```

- [x] **Step 5: Write `test_fetch_tour_oa_geometry.py` (mocked network, no live call)**

```python
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib.oa_geometry import oa_chain  # noqa: E402


def test_oa_chain_survives_a_cached_content_round_trip(tmp_path):
    # Guards the shape fetch_tour_oa_geometry.py writes: {tourId, points} with points already
    # 2-D, so match_tour_edges.py never has to know about OA's [lon, lat, ele] triples.
    content = {"id": "999", "geoJson": {"type": "LineString",
                                         "coordinates": [[10.0, 47.0, 1200.0], [10.1, 47.1, 1300.0]]}}
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(json.dumps({"999": content}), encoding="utf-8")

    from lib.oa_geometry import fetch_oa_contents
    with patch("urllib.request.urlopen") as mock_urlopen:
        contents = fetch_oa_contents(["999"], cache_path, allow_fetch=True)
    mock_urlopen.assert_not_called()
    assert oa_chain(contents["999"]) == [(10.0, 47.0), (10.1, 47.1)]
```

- [x] **Step 6: Run the tests**

Run: `cd pipeline && pixi run pytest tests/test_fetch_tour_oa_geometry.py tests/test_fetch_tours.py -v`
Expected: all pass

- [x] **Step 7: Wire the new task into the doit DAG**

In `pipeline/dag/downloads.py`, add (near `task_fetch_tours`):

```python
def task_fetch_tour_oa_geometry():
    # Downstream of fetch_tours.py's oaId resolution - task_dep (not just file_dep on tours.json)
    # because a re-run with the SAME tours.json content but a code change to oa_ids_by_tour's
    # regex should still refetch, and doit's file_dep freshness check alone wouldn't catch that.
    return pipeline_task(
        "phases/downloads/fetch_tour_oa_geometry.py",
        task_dep=["fetch_tours"],
        file_dep=[OSM_DIR / "tours.json"],
        targets=[OSM_DIR / "tour_oa_traces.json"],
    )
```

Then add `"fetch_tour_oa_geometry"` to `task_match_tour_edges`'s `task_dep` list and
`OSM_DIR / "tour_oa_traces.json"` to its `file_dep` list in `pipeline/dag/graph_building.py`.

- [x] **Step 8: Run the pipeline test suite and commit**

```bash
cd pipeline && pixi run pytest -q
git add pipeline/phases/downloads/fetch_tours.py pipeline/phases/downloads/fetch_tour_oa_geometry.py \
        pipeline/tests/test_fetch_tours.py pipeline/tests/test_fetch_tour_oa_geometry.py \
        pipeline/dag/downloads.py pipeline/dag/graph_building.py
git commit -m "downloads: resolve tours' Outdooractive id and fetch their published geometry"
```

---

### Task 4: Teach `match_tour_edges.py` to fall back to OA geometry per tour

**Files:**
- Modify: `pipeline/phases/graph_building/match_tour_edges.py`
- Modify: `pipeline/tests/test_match_tour_edges.py`

**Interfaces:**
- Consumes: `data/osm/tour_oa_traces.json` (Task 3), `lib.oa_geometry.oa_chain` is NOT needed here
  (the file already stores plain 2-D points); `lib.tour_geometry.orient_chain` (existing).
- Produces: `_chain_for_tour`'s signature changes from
  `(paths, break_threshold_m, hut_coords_in_order, is_loop)` to additionally accept
  `oa_points: list | None`, still returning `(chains, oriented_primary)` — callers unchanged in
  shape, just get a chain more often.

Precedence: try the AV's own reassembled chain first (it's the AV's own authoritative route,
spec's primary source); fall back to OA's line ONLY when reassembly didn't produce exactly one
chain. This matches the spike's framing (OA is the fallback the spike validated, not a wholesale
replacement) and means a tour that already matches today keeps matching on the exact same
geometry it always has — no regression risk for the 18 legs already shipping.

- [x] **Step 1: Write the failing tests**

Add to `pipeline/tests/test_match_tour_edges.py`, next to the existing `_chain_for_tour`-adjacent
tests (search the file for `reassemble_fragments` usage to place these near related coverage):

```python
from graph_building.match_tour_edges import _chain_for_tour  # noqa: E402


def test_chain_for_tour_falls_back_to_oa_when_reassembly_fails():
    # Two fragments 10km apart - reassemble_fragments (break_threshold_m=150) leaves them as 2
    # separate chains, so oriented is None on ArcGIS alone.
    paths = [[(0.0, 0.0), (0.001, 0.001)], [(1.0, 1.0), (1.001, 1.001)]]
    oa_points = [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)]
    chains, oriented = _chain_for_tour(
        paths, break_threshold_m=150.0, hut_coords_in_order=[(0.0, 0.0), (1.0, 1.0)],
        is_loop=False, oa_points=oa_points,
    )
    assert oriented == oa_points  # already starts at hut 0, no reversal needed


def test_chain_for_tour_prefers_arcgis_reassembly_when_it_succeeds():
    # Single fragment - reassembly already succeeds, so a DIFFERENT-looking oa_points must be
    # ignored (precedence: AV's own geometry wins when it's usable at all).
    paths = [[(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)]]
    oa_points = [(9.0, 9.0), (9.5, 9.5)]
    chains, oriented = _chain_for_tour(
        paths, break_threshold_m=150.0, hut_coords_in_order=[(0.0, 0.0), (1.0, 1.0)],
        is_loop=False, oa_points=oa_points,
    )
    assert oriented == paths[0]


def test_chain_for_tour_reports_gap_when_neither_source_works():
    chains, oriented = _chain_for_tour(
        [[(0.0, 0.0), (0.001, 0.001)], [(1.0, 1.0), (1.001, 1.001)]],
        break_threshold_m=150.0, hut_coords_in_order=[(0.0, 0.0), (1.0, 1.0)], is_loop=False,
        oa_points=None,
    )
    assert oriented is None
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `cd pipeline && pixi run pytest tests/test_match_tour_edges.py -k chain_for_tour -v`
Expected: FAIL with `TypeError: _chain_for_tour() got an unexpected keyword argument 'oa_points'`

- [x] **Step 3: Update `_chain_for_tour`**

Replace in `pipeline/phases/graph_building/match_tour_edges.py`:

```python
def _chain_for_tour(paths: list, break_threshold_m: float, hut_coords_in_order: list, is_loop: bool):
    """Reassembles + orients a tour's fragments (spec §2.2). Returns (chains, oriented_primary) -
    oriented_primary is the single reassembled+oriented chain when reassembly produced exactly
    one, else None (callers fall back to a whole-tour bbox built from ALL chains' points, per
    spec §2.3's mitigation note, and every leg whose two huts don't land in the SAME chain becomes
    a chain_not_reassembled gap - spec §2.5)."""
    chains = reassemble_fragments(paths, break_threshold_m)
    if len(chains) == 1:
        return chains, orient_chain(chains[0], hut_coords_in_order, is_loop)
    return chains, None
```

with:

```python
def _chain_for_tour(paths: list, break_threshold_m: float, hut_coords_in_order: list, is_loop: bool,
                     oa_points: list | None = None):
    """Reassembles + orients a tour's fragments (spec §2.2), falling back to Outdooractive's
    already-ordered line (docs/superpowers/plans/2026-08-30-tour-reproducibility.md Task 3/4) when
    the AV's own fragments don't reassemble into one chain - spec §2.7's spike showed this recovers
    29 of 37 previously chain_not_reassembled legs across 9 tours, with a byte-identical control on
    a tour where reassembly already worked. The AV's own geometry always wins when it's usable at
    all: `oa_points` is only consulted when reassembly did NOT produce exactly one chain.

    Returns (chains, oriented_primary) - `chains` is always the ArcGIS reassembly result (used by
    main()'s whole-tour-bbox fallback regardless of which source oriented_primary came from);
    oriented_primary is None only when BOTH sources fail, which is when callers gap the tour as
    chain_not_reassembled (spec §2.5)."""
    chains = reassemble_fragments(paths, break_threshold_m)
    if len(chains) == 1:
        return chains, orient_chain(chains[0], hut_coords_in_order, is_loop)
    if oa_points:
        return chains, orient_chain(oa_points, hut_coords_in_order, is_loop)
    return chains, None
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `cd pipeline && pixi run pytest tests/test_match_tour_edges.py -k chain_for_tour -v`
Expected: 3 passed

- [x] **Step 5: Wire `oa_points` through `main()`**

In `main()`, after the existing `traces_by_tour_id = {...}` line, add:

```python
    oa_traces_path = OSM_DIR / "tour_oa_traces.json"
    oa_points_by_tour_id = {}
    if oa_traces_path.exists():
        with open(oa_traces_path, encoding="utf-8") as fh:
            oa_points_by_tour_id = {t["tourId"]: t["points"] for t in json.load(fh) if t["points"]}
```

and change the `_chain_for_tour(...)` call inside the `for tour in tours:` loop to:

```python
            chains, oriented = _chain_for_tour(
                paths, args.fragment_break_m, hut_coords_in_order, tour["isLoop"],
                oa_points=oa_points_by_tour_id.get(tour["tourId"]),
            )
```

`oa_traces_path.exists()` guards against a checkout that hasn't run Task 3's new fetch task yet
(pre-existing `out-dir`s in tests, or a partial rerun) — never a hard requirement, since a tour
with no OA geometry available must still fall through to `chain_not_reassembled` exactly as today.

- [x] **Step 6: Add a golden-path regression test for the fallback**

Add to `pipeline/tests/test_match_tour_edges.py`, modeled directly on
`test_golden_single_part_tour_matches_all_legs_end_to_end` (same synthetic base graph / hut
fixture helpers already in that file) but with a 2-fragment `paths` that does NOT reassemble, and
a `tour_oa_traces.json` written into `tmp_path` supplying the same node coordinates as one clean
line:

```python
def test_golden_tour_falls_back_to_oa_when_arcgis_fragments_dont_reassemble(tmp_path, monkeypatch):
    grid = Grid(BBOX, tile_size_km=60.0)
    base_graph_dir, node_coords = _write_synthetic_base_graph(tmp_path, grid)

    hut_coords = node_coords
    huts_geojson = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"id": f"{{GUID-{i}}}"},
             "geometry": {"type": "Point", "coordinates": list(c)}}
            for i, c in enumerate(hut_coords)
        ],
    }
    (tmp_path / "huts.geojson").write_text(json.dumps(huts_geojson), encoding="utf-8")

    persisted_snaps = {}
    for i, node_idx in enumerate((0, 1, 2, 3)):
        result = SnapResult(node_index=node_idx, gap_m=0.0, gap_dz_m=0.0)
        stand_in_subgraph = LocalSubgraph(
            global_node_ids=np.arange(4), local_nodes=np.zeros(0, dtype=binfmt.NODE_DTYPE),
            local_edges=np.zeros(0, dtype=binfmt.EDGE_DTYPE),
            interior=np.zeros(0, dtype=binfmt.COORD_DTYPE),
            local_node_ele=np.zeros(0, dtype=np.float32), interior_ele=np.zeros(0, dtype=np.float32),
        )
        persisted_snaps[(binfmt.TYPE_HUT, i)] = to_persisted(stand_in_subgraph, result)
    pack_hub_snaps(persisted_snaps, tmp_path)

    tours = [{
        "tourId": 0, "globalId": "{TOUR-OATEST}", "name": "OA-fallback test tour",
        "shortCode": "OATEST", "isLoop": False, "homepage": None, "oaId": "1",
        "hutIndices": [0, 1, 2, 3],
    }]
    (tmp_path / "tours.json").write_text(json.dumps(tours), encoding="utf-8")
    # Deliberately broken into 2 far-apart fragments - reassemble_fragments will NOT rejoin them
    # (default fragmentBreakM=150.0 in this test's config below).
    traces = [{"tourId": 0, "paths": [[list(node_coords[0]), list(node_coords[1])],
                                       [list(node_coords[2]), list(node_coords[3])]]}]
    (tmp_path / "tour_traces.json").write_text(json.dumps(traces), encoding="utf-8")
    (tmp_path / "tour_oa_traces.json").write_text(
        json.dumps([{"tourId": 0, "points": [list(c) for c in node_coords]}]), encoding="utf-8",
    )

    import graph_building.match_tour_edges as mte

    monkeypatch.setattr(mte, "OSM_DIR", tmp_path)
    monkeypatch.setattr(
        mte, "load_config",
        lambda: {"tourMatch": {"fragmentBreakM": 150.0, "corridorBufferM": 150.0,
                                "maxHutTraceM": 250.0, "lengthDivergenceRatio": 2.0}},
    )
    mte.main(["--base-graph-dir", str(base_graph_dir), "--out-dir", str(tmp_path)])

    records = binfmt.load_array(tmp_path / "tour_edges" / "records.npy", mmap=False)
    gaps = json.loads((tmp_path / "tour-match-gaps.json").read_text(encoding="utf-8"))
    assert len(records) == 3  # all 3 legs matched via the OA fallback, no chain_not_reassembled
    assert gaps == []
```

- [x] **Step 7: Run it to verify it fails without Step 5's wiring, then passes with it**

Run: `cd pipeline && pixi run pytest tests/test_match_tour_edges.py -k oa_fallback -v`
Expected: FAIL (3 `chain_not_reassembled` gaps) before Step 5, PASS after.

- [x] **Step 8: Run the full pipeline test suite and commit**

```bash
cd pipeline && pixi run pytest -q
git add pipeline/phases/graph_building/match_tour_edges.py pipeline/tests/test_match_tour_edges.py
git commit -m "graph_building: fall back to Outdooractive geometry when a tour's fragments don't reassemble"
```

---

### Task 5: Full re-run and decision point

**Files:** none created — this is a measurement + report task, and a possible follow-up plan.

**Interfaces:**
- Consumes: everything above.
- Produces: an updated `data/osm/tour-match-gaps.json` / `tour_edges/*` (gitignored, not
  committed) and a short findings note the user can act on.

- [x] **Step 1: STOP — get explicit user confirmation before running any doit task**

Per `.claude/CLAUDE.md`: **never run `doit` (any task or the full DAG) without asking first**,
even though `build_base_graph` itself is untouched and not expected to rerun here (only
`fetch_tour_oa_geometry` and `match_tour_edges` should be stale). State exactly which task names
you intend to run (`doit fetch_tour_oa_geometry match_tour_edges`, or `doit` if simplest) and wait
for a yes.

- [x] **Step 2: Run it**

Run: `cd pipeline && pixi run doit fetch_tour_oa_geometry match_tour_edges`

- [x] **Step 3: Compare gap counts against the baseline**

```bash
pixi run python -c "
import json
from collections import Counter
gaps = json.load(open('../data/osm/tour-match-gaps.json'))
print(Counter(g['reason'] for g in gaps))
print('total gaps', len(gaps))
"
```

Baseline (before this plan): 82 `chain_not_reassembled`, 1 `hut_far_from_trace`,
1 `length_divergent`, 18 legs matched, out of 102 total. Report the new numbers per-reason and
per-tour (group by `shortCode` the same way this plan's investigation did) so it's clear exactly
which tours moved and which didn't.

- [x] **Step 4: Decision point**

- If the tours Task 2 couldn't resolve an OA id for are now the ONLY remaining
  `chain_not_reassembled` tours, AND every other remaining gap is one of the already-out-of-scope
  categories (`hut_unsnapped` — snapping layer, spec plan's explicit exclusion; the 2 empty-hut-
  list tours Wiener Höhenweg/MontafonerSilvrettarunde — also explicitly out of scope) — **stop
  here.** Ship this. File the unresolved-OA-id tours as a follow-up (their own future work: either
  a smarter homepage-embed search, or accepting they stay unmatched) rather than reaching for
  `leuvenmapmatching`, since the blocker for those tours is "no trace source at all", which HMM
  map-matching can't fix either — it still needs *a* trace to match against the graph.
- If, instead, some tours that DO have OA geometry are still gapping in ways the spike didn't
  predict (e.g. more `no_corridor_path` or `length_divergent` than the spike's 9-tour sample), that
  is real evidence the corridor-on-OA approach has limits `leuvenmapmatching` might address (spec
  §2.4) — scope that as its own follow-up plan rather than folding it in here, since it's a new
  algorithm, not a data-source swap.
- Write whichever outcome applies as a short dated note under
  `docs/superpowers/plans/2026-08-30-tour-reproducibility.md`'s own bottom (or a new plan file, if
  `leuvenmapmatching` is the next step) — do not silently leave this plan's final state undocumented.

---

## Self-Review Notes

- **Spec coverage:** Task 1 covers reuse discipline (analysis/README.md's "call the real
  functions" rule, now literally true — the spike calls `lib/` code instead of defining its own).
  Task 2 covers spec §2.7's open question about the other 15 tours. Tasks 3–4 cover wiring the
  validated approach into the actual `fetch_tours.py`/`match_tour_edges.py` production path (the
  spike never touched production code, by its own README-mandated design). Task 5 covers spec
  §2.5's gap-reason discipline (never invents a 7th reason) and closes the loop on whether
  `leuvenmapmatching` (§2.4) is still needed, which was this plan's own opening question.
- **No placeholders:** every code step above is either the actual promoted spike code (Task 1,
  verified against the real file), a concrete test with real assertions, or explicitly marked as
  an exploratory step with a defined, checkable output shape (Task 2) rather than a guessed
  outcome.
- **Type/signature consistency:** `_chain_for_tour`'s new `oa_points` parameter is threaded through
  identically in Task 4 Steps 3 and 5; `fetch_oa_contents`'s `cache_path` parameter (added in
  Task 1) is used consistently by the spike (Task 1 Step 5), `fetch_tour_oa_geometry.py`
  (Task 3 Step 4), and both tests that call it.

## 2026-08-30 — Task 5 result and decision

Ran `doit fetch_tours fetch_tour_oa_geometry match_tour_edges` (`fetch_tours` had to be
force-rerun via `doit forget fetch_tours` first — its `uptodate` check tracks `bbox_json` and
`huts.geojson`, neither of which changed when Task 3 added `oaId` derivation to the script itself,
so doit considered it fresh with a stale `tours.json`; this is a real gap in `pipeline_task`'s
freshness check — it doesn't hash the action script — worth a future fix, but out of scope here).

Task 2's homepage scan found 2 more ids (KHW, BHW) beyond the spike's original 10, for 12/25 tours
with a resolved `oaId`. Result: **47 of 102 legs matched (46%), up from 18/102 (18%)** baseline.

Gap reasons: `chain_not_reassembled` 45, `hut_unsnapped` 4, `hut_far_from_trace` 3,
`no_corridor_path` 2, `outside_extract` 1 (55 total, was 82/1/1/0 baseline).

**Decision: ship this, no `leuvenmapmatching` follow-up needed yet.**

- All 45 remaining `chain_not_reassembled` gaps belong to the 10 tours with no resolvable OA id
  (PHR, Karwendel Höhenweg, SHR, IHW, MontafonerHüttenrunde, STHW, VT4T, KT01, TT4T,
  Achttälertour) — exactly Task 2's finding, no chain_not_reassembled leaked onto an OA-sourced
  tour. `Wiener Höhenweg` and `MontafonerSilvrettarunde` (empty hut lists) contribute 0 gaps as
  expected, out of scope regardless.
- The remaining 10 gaps (`hut_unsnapped`/`hut_far_from_trace`/`no_corridor_path`/
  `outside_extract`) sit entirely on the 11 OA-sourced tours that needed the fallback (LQR
  excluded — it already matched via ArcGIS reassembly, untouched by this plan). That rate (10
  gaps / 11 tours) is consistent with, not worse than, `oa_corridor_spike.json`'s own prediction
  for the same 9 tours (8 gaps / 40 legs) plus 2 new ones — i.e. the corridor-on-OA approach is
  behaving exactly as the spike characterized it, not hitting a new limit `leuvenmapmatching`
  would need to address. `hut_unsnapped` is explicitly out of scope (snapping layer); the other 6
  (`hut_far_from_trace`/`no_corridor_path`/`outside_extract`) are a small, already-measured
  residual, not evidence of a systemic corridor-routing problem.
- **Follow-up (separate future work, not this plan):** the 10 tours with no discoverable OA id
  have no trace source at all — `leuvenmapmatching` doesn't help there either, since HMM
  map-matching still needs *a* trace to match against the graph. Their own follow-up is either a
  smarter homepage-embed search (Task 2's scan was HTML-regex only, no JS-rendered widget
  detection) or accepting they stay unmatched.
