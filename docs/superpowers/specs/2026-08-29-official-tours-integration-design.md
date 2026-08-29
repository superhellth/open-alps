# Official ÖAV/DAV Tours Integration — Design

**Problem:** The Alpenverein publishes 26 official multi-day trekking routes (Karnischer
Höhenweg, Peter-Habeler-Runde, Berliner Höhenweg, various Hüttenrunden, ...) via a separate ArcGIS
layer, `AVT_CAA_TOUR_View_L` (`docs/alpenverein-api.md` §3, `pipeline/CLAUDE.md`). Today the
hut-to-hut pipeline treats this layer as reference material only — its own graph
(`build_hub_edges.py`) finds *shortest* paths between huts, which is a deliberate design choice for
free-form trip planning but is the wrong answer for "show me the real Peter-Habeler-Runde": the
official route does not always coincide with our shortest path, and distorting it to match would
misrepresent a named, waymarked trail.

**Goal:** Ship the official tours with the same per-leg data our own hut-edges already carry —
distance, ascent/descent, elevation profile, difficulty facts (`sac_rank`/`via_ferrata`/
`ungraded_m`) — computed from the *same* DEM/elevation pipeline, without needing a second elevation
pass, and without distorting the tour's real route to a free shortest path.

**Core idea:** the AV tour layer's geometry is real-world polyline data (an `esriGeometryPolyline`,
confirmed by direct query), not just a hut list. Constrain a path to that geometry on our own base
graph (`pipeline/phases/graph_building/build_base_graph.py`'s `base_graph/`) instead of routing
freely. A resulting tour leg is then literally a sequence of existing base-graph edges, which
`elevation/compute_edge_profiles.py` has *already* stamped with `time_s`/`ascent_m`/`descent_m` —
hub-agnostically, before any hub-edge routing runs. So the geometry constraint gets "the same DEM
data" for free: no new elevation sampling, just summing already-computed per-edge values along the
resulting path.

**What "the same per-leg data" does not include:** duration. `RECORD_DTYPE` has no `time_s` column
and `hut-edge-payload.bin` ships no duration column — the client computes DIN itself from
`distance_m`/`ascent_m`/`descent_m` (`build_edge_payload.py`'s docstring, spec D3). Tour legs follow
that convention: `time_s` is summed only as a match-plausibility check (§2.5), never persisted.

## 0. Source data — `AVT_CAA_TOUR_View_L`

Every number below was measured against a live query of
`services1.arcgis.com/PHS4LHADrqt5glC9/.../AVT_CAA_TOUR_View_L/FeatureServer/0` on 2026-08-29
(same backend/auth as the hut layer, no auth, `outSR=4326` reprojects cleanly), joined against the
current `data/osm/huts.geojson` (846 huts) and `data/osm/unsnapped_huts.json`.

- **26 features total.** One is garbage: `Kurzbezeichnung="#DUMMY"`, `Bezeichnung=null`, geometry
  in Bolivia (2 points) — must be filtered by `Kurzbezeichnung == "#DUMMY"`, not by a fragile
  null-name check (one legitimate tour, "Karwendel Höhenweg", also lacks a distinct
  `Bezeichnung`/`Kurzbezeichnung` pair but is real, and `#DUMMY`'s own `Huettenliste` is non-empty
  and *does* resolve, so a hut-list check would not catch it either).
- Fields: `OBJECTID`, `GlobalID`, `Bezeichnung` (display name), `Kurzbezeichnung` (short code),
  `Rundtour` (0/1 loop flag), `Homepage`, `Download` (both external links, mostly to
  alpenvereinaktiv.com or regional tourism sites — not structured data, not needed since geometry
  ships in this layer directly), `Huettenliste` (comma-separated hut `GlobalID`s, **in tour
  order**), `Shape__Length`.
- **`Shape__Length` is Web Mercator metres, not ground metres.** Measured against a summed
  great-circle length of the same geometry, the ratio is a uniform 0.68 across all 25 real tours —
  i.e. `Shape__Length ≈ ground_length · sec(φ)` at φ ≈ 47°N. Anything comparing a routed length
  against "the AV's own length" (§2.5) must divide it out or, better, sum the geometry directly.
- **Two tours have no hut list, not one**: `Wiener Höhenweg` and `MontafonerSilvrettarunde` both
  have an empty/null `Huettenliste`. Both have geometry but no hut chain to split legs against —
  out of scope for leg-splitting (§2), tracked as a known gap. That leaves **23 tours with a hut
  chain**, not 25.
- `Huettenliste` ids are the ArcGIS `id`/`GlobalID` values from the *hut* layer
  (`AVT_GEO_CAA_HUETTEN_View_P`), **not** the positional index `RECORD_DTYPE.from_id`/`to_id` uses
  when `from_type/to_type == TYPE_HUT` (that index is `huts.geojson`'s feature array position,
  `lib/hubs.py:22`). Resolving a `Huettenliste` GUID to that index means joining against
  `huts.geojson`'s own `id` property, which `fetch_huts.py` already carries through from the same
  ArcGIS hut layer. **Verified: all 116 GUIDs across those 23 tours resolve today on exact raw
  string match** — both sides are `{UPPERCASE-BRACED}`, so no normalization is needed (do it
  anyway, defensively, but don't design around a mismatch that doesn't exist).

### 0.1 The geometry is fragmented and unordered

This is the finding that reshapes §2. `paths` is not one ordered polyline per tour — **21 of the 25
real tours are multi-part, and the parts are scrambled**: array order has no relationship to route
order. Summing the end-to-start gap between consecutive parts *in array order* gives 99 km of "gaps"
on Chiemgautour's 40 km route, and 139 km on SVR7T's 70 km route.

The parts do, however, chain: endpoint → nearest *other* part's endpoint has a median of 0–14 m
(CGT p90 = 45 m, TT4T p90 = 40 m). So each tour's geometry is a contiguous route shattered into an
unordered bag of fragments, not a set of disjoint pieces with real holes. Reassembly is possible but
is a real algorithm (§2.2), not a detail.

Point density spans two orders of magnitude — 3 m/point (KHW) to 102 m/point (SVR7T, 682 points over
70 km). No single set of matching parameters covers both ends of that range.

### 0.2 Per-tour reference numbers

Measured 2026-08-29. `legs` counts the closing leg for `Rundtour` (§2.1); `lost` counts legs whose
endpoint hut is already in `unsnapped_huts.json` (§0.3).

| tour | loop | huts | parts | pts | km | m/pt | max hut→trace | legs | lost |
|---|---|---|---|---|---|---|---|---|---|
| SVR7T |  | 6 | 51 | 682 | 70 | 102 | 32 m | 5 | 2 |
| TT4T | yes | 3 | 47 | 720 | 35 | 49 | 41 m | 3 | 2 |
| CGT | yes | 3 | 45 | 771 | 40 | 52 | 37 m | 3 | 0 |
| RFD4T |  | 3 | 39 | 7857 | 53 | 7 | 54 m | 2 | **2** |
| Wiener Höhenweg |  | 0 | 18 | 2593 | 51 | 20 | — | 0 | 0 |
| VR6T | yes | 5 | 17 | 1642 | 40 | 24 | 28 m | 5 | 2 |
| MontafonerHüttenrunde |  | 9 | 14 | 17826 | 132 | 7 | 39 m | 8 | 0 |
| PT4T |  | 3 | 13 | 1328 | 31 | 23 | 19 m | 2 | 0 |
| Karwendel Höhenweg |  | 5 | 12 | 609 | 61 | 99 | 28 m | 4 | 0 |
| THW |  | 8 | 8 | 2050 | 69 | 34 | 30 m | 7 | 1 |
| PHR | yes | 6 | 7 | 3020 | 52 | 17 | 38 m | 6 | 0 |
| KT01 |  | 3 | 7 | 2725 | 38 | 14 | 28 m | 2 | 0 |
| Achttälertour | yes | 5 | 7 | 3863 | 55 | 14 | 23 m | 5 | 0 |
| IHW |  | 5 | 5 | 3969 | 68 | 17 | 47 m | 4 | 0 |
| Dachsteinrunde | yes | 4 | 5 | 1109 | 39 | 35 | 44 m | 4 | 0 |
| HSHR | yes | 3 | 5 | 498 | 34 | 68 | 28 m | 3 | 0 |
| STHW |  | 6 | 5 | 3943 | 53 | 13 | 83 m | 5 | 0 |
| SHR | yes | 6 | 4 | 3001 | 84 | 28 | 41 m | 6 | 0 |
| VWR8 |  | 7 | 4 | 5319 | 70 | 13 | 100 m | 6 | 0 |
| VT4T |  | 3 | 2 | 1652 | 26 | 15 | 23 m | 2 | 0 |
| MontafonerSilvrettarunde | yes | 0 | 2 | 4639 | 32 | 7 | — | 0 | 0 |
| KHW |  | 7 | 1 | 22336 | 74 | 3 | **9178 m** | 6 | 0 |
| BHW | yes | 8 | 1 | 1133 | 66 | 59 | 29 m | 8 | 0 |
| LQR |  | 4 | 1 | 6206 | 45 | 7 | 19 m | 3 | 0 |
| WelserHöhenweg |  | 4 | 1 | 2769 | 54 | 19 | 95 m | 3 | 0 |

**102 legs total, 9 already lost to unsnapped huts, 1 more (KHW's last) lost to incomplete
geometry — so ~92 legs across 22 tours is the optimistic ceiling** before any match failure.
RFD4T loses *every* leg and will produce no `records.npy` rows at all. (TT4T loses 2 of 3; its
closing `Rundtour` leg survives precisely because §2.1 emits one.)

### 0.3 Two assumptions that do not hold

1. **"Huts sit right on the trail by construction" is false.** KHW's Zollnersee-Hütte is **9,178 m**
   from the nearest trace vertex — the AV geometry simply stops short of its own hut list. Elsewhere
   the max hut→trace offset reaches 83–100 m (STHW 83, WelserHöhenweg 95, VWR8 100). A threshold
   started at `--max-snap-m` (**100 m** in `pipeline.config.json`) would sit exactly on top of that
   distribution and drop real legs from VWR8 and WelserHöhenweg. Start at **250 m** and record the
   measured offset per leg in the gap file so the threshold can be retuned against real numbers
   rather than guessed twice.
2. **Not every tour hut has a snap.** 6 of those 116 tour hut references are already in
   `unsnapped_huts.json` — anchoring a leg to `hub_snaps.npy` (§2.3) is impossible for them, and
   both adjacent legs die:

   | tour | hut | reason |
   |---|---|---|
   | THW | Ali-Lanti-Biwak | `vertical_offset` |
   | TT4T | Heinrich-Schwaiger-Haus | `vertical_offset` |
   | SVR7T | Tuoi Chamonna CAS | `gap_too_far` |
   | VR6T | Brandenburger Haus | `vertical_offset` |
   | RFD4T | Rieserfernerhütte, Kasseler Hütte (Rif. Roma) | `gap_too_far` |

   "Tour hut has no persisted snap" is therefore a first-class gap case in §2.5, not an edge case.
   Note `Tuoi Chamonna CAS` is in **Switzerland** — the coverage limit is not only South Tyrol; the
   region list is `["austria", "bayern"]`.

## 1. New `downloads/` task: `fetch_tours.py`

Mirrors `fetch_huts.py`'s shape (plain `f=json&outSR=4326` GET, no auth, no pagination needed at
26 records). Params: none beyond the standard `--osm-dir`.

- Fetches all fields + geometry from `AVT_CAA_TOUR_View_L`.
- Drops the `#DUMMY` record.
- Resolves each `Huettenliste` GUID against `huts.geojson`'s `id` property to `RECORD_DTYPE`'s
  positional hut index. A GUID that doesn't resolve (hut outside `config["bbox"]` — `fetch_huts.py`
  bbox-filters; hut reclassified to `partner_betriebe.geojson`, which keys on `OBJECTID` and so
  cannot be joined on a GUID at all; or genuinely absent) is recorded in a `tour-fetch-gaps.json`
  sidecar. **It is not silently dropped from the ordered chain**: dropping hut B from A→B→C
  silently fuses two real stages into one leg A→C, which is exactly the "never faked" failure the
  rest of this spec avoids. Instead, the tour's hut chain is *split* at the unresolved entry and the
  two legs touching it are skipped, same as §2.5's other gap cases. (Verified empty today — all 116
  GUIDs resolve — so this path is defensive, not load-bearing.)

**Two output files, not one** — the raw traces are ~3.5 MB and must not reach the client:

- `tours.json` — **shipped**. One record per tour: `{tourId, globalId, name, shortCode, isLoop,
  homepage, hutIndices: [int, ...]}`. `tourId` is the array index into this file (same convention
  as hut indices, stable for the life of one pipeline run); `globalId` is the AV's own `GlobalID`,
  kept as the stable cross-run identity so two runs can be diffed and a client can hold a durable
  reference to a tour. Client-shaped, no postprocessing.
- `tour_traces.json` — **internal**, not in `PUBLIC_FILES`. The raw per-tour `paths` (lon/lat pairs,
  `outSR=4326`) consumed by `match_tour_edges.py` (§2). The matched geometry is what ships, via
  `tour-edges.pmtiles`/`tour-edge-geometry.bin` — shipping the source traces as well would be
  3.5 MB of redundant download.

**doit wiring**: `file_dep=[huts.geojson]` — **not** `file_dep=[]`. Unlike `fetch_huts.py` this is
not a pure network fetch: it reads `huts.geojson` to turn GUIDs into *positional indices*, so a
refetch that reorders or re-filters huts silently invalidates every `hutIndices` entry. Also carry
`fetch_huts`' `bbox_json` tracking param for the same reason. `targets=[tours.json,
tour_traces.json, tour-fetch-gaps.json]`.

## 2. New `graph_building/` task: `match_tour_edges.py`

Runs after `compute_edge_profiles.py` (needs `base_graph/edges.npy`'s `time_s`/`ascent_m`/
`descent_m` filled — UNSET before that) and `snap_hubs.py` (needs every tour hut's persisted snap,
`hub_snaps.npy`). Independent of `gather_route_subgraphs.py`/`build_hub_edges.py` — it never
consults `graph.variants`.

### 2.1 Legs

A tour's legs are `hutIndices[i] → hutIndices[i+1]`, **plus a closing leg
`hutIndices[-1] → hutIndices[0]` when `Rundtour == 1`** (10 of the 25 real tours are loops; without
the closing leg a client rendering a Hüttenrunde gets an open chain that doesn't match the published
route). That is what the 102-leg count in §0.2 reflects.

A hut may legitimately appear twice in one chain; legs are identified by `(tour_id, leg_index)`
(§2.6's `tour_meta.npy`), never by `(from_id, to_id)`, so a revisit is not a duplicate.

### 2.2 Fragment reassembly (required by both approaches below)

Because `paths` is an unordered bag of fragments (§0.1), any per-leg reasoning needs the tour's
geometry as an ordered chain first:

1. Collect every fragment's two endpoints. Greedily join fragments by nearest endpoint (reversing a
   fragment when it joins tail-to-tail), stopping when the nearest remaining join exceeds a break
   threshold — start from **150 m**, above the measured p90 of 45 m and well below the real breaks.
2. The result is one chain per tour in the good case, or a small number of chain segments where the
   geometry genuinely has holes. Record the number of chains and each break's length in
   `tour-match-gaps.json` — a tour that does not reassemble into one chain is a data fact worth
   surfacing, not a silent partial.
3. Orient the chain against `hutIndices`: the end nearer `hutIndices[0]` is the start. For a
   `Rundtour` the chain closes on itself and orientation is decided by which direction visits the
   hut list in order.

This step is independently testable against the real layer and should land (and be validated on all
25 tours, including the two with no hut chain) before either matcher below is written.

### 2.3 Primary approach — corridor-constrained routing

Take the tour's fragments, buffer them (start from **150 m**), gather that corridor from the base
graph with the existing `lib/subgraph.py`, and route each leg's hut snap → hut snap **inside the
corridor** using the existing `build_base_igraph_arrays`/`build_igraph_from_base`/`accumulate_path`
path. The corridor is what stops it degenerating into `build_hub_edges.py`'s free shortest path.

Why this is the primary path:

- **No new dependency and no `pixi.toml` change** — it is the machinery the pipeline already runs.
- **The reuse §2.6 needs actually works.** `accumulate_path` returns exactly the `PathResult` the
  record packer wants, and it is igraph-bound by signature (`graph, vertex_coords, src_v, tgt_v,
  epath`) — a matcher that produces a bare list of base-graph edge rows *cannot* call it without
  building an igraph anyway.
- **It needs no fragment ordering for the corridor itself** (§2.2 is still needed for leg
  assignment, but a mis-ordered chain degrades leg boundaries, not the corridor).
- **Per-tour scope by construction**: no tour exceeds ~200 km, so the corridor subgraph is small.

Its known weakness: on a `Rundtour` the corridor contains the whole loop, so an A→B path can take
the short way round even when the official leg goes the long way. Mitigation is to cut the corridor
per leg from the §2.2 chain (only the fragments between the two huts' chain positions), falling back
to the whole-tour corridor only when the chain didn't reassemble.

### 2.4 Documented fallback — `leuvenmapmatching`, scoped

If the spike (§2.7) shows corridor routing systematically departing from the published route, fall
back to HMM map matching with `leuvenmapmatching` (PyPI, pure Python, `numpy`/`scipy` at its core —
far lighter to add to the `alpen-osm` pixi env, which already has a `[pypi-dependencies]` section,
than `fmm`'s C++/GDAL/Boost stack). Three constraints the original draft of this spec got wrong and
that any implementation must respect:

- **Never build the matcher's graph from the whole base graph.** `base_graph/manifest.json` is
  **3,931,404 nodes / 4,730,712 edges**; `InMemMap` is Python dicts of tuples and sets, so that is
  multiple GB before matching starts. `lib/subgraph.py`'s tiling exists because of *graph size*, not
  pair count — "26 tours is a small workload" is an argument about pairs and does not apply. Build
  one `InMemMap` **per tour**, from the same §2.3 corridor.
- **Expand interiors.** Base-graph edges are *contracted chains* whose real shape lives in
  `base_graph/interior.npy` (376 MB, ~23.5 M points). Matching against straight u→v segments
  discards exactly the curvature the match is meant to discriminate on. Expand each corridor edge's
  interior into the matching graph and map matched segments back to their parent edge id.
- **Resample the trace per tour.** Density ranges 3–102 m/point (§0.1); a fixed `obs_noise`/
  `max_dist` cannot serve both. Resample to a uniform spacing (~25 m) before matching.

### 2.5 Gap cases — never faked

A leg is **not emitted** and is recorded to `tour-match-gaps.json` with tour/leg identity and reason
when any of these holds. No straight-line or partial-distance placeholder is ever written.

| reason | detail |
|---|---|
| `hut_unsnapped` | either endpoint hut is absent from `hub_snaps.npy` (§0.3 — 9 legs today) |
| `hut_far_from_trace` | endpoint hut > **250 m** from the nearest trace vertex (KHW's last leg — record the measured metres so the threshold is retunable) |
| `outside_extract` | sub-trace leaves the AT+Bayern OSM extract (SVR7T's Swiss leg, RFD4T's South Tyrol legs) |
| `no_corridor_path` | no connected path exists inside the corridor |
| `length_divergent` | routed length vs. the leg's own trace length outside a **2×** ratio (matching `--max-edge-km`'s own headroom). Compare against the *summed geometry*, not `Shape__Length` — that field is Web Mercator metres (§0) |
| `chain_not_reassembled` | §2.2 produced more than one chain and the leg spans a break |

The summed `time_s` along the routed path is checked for plausibility here (a leg whose implied pace
is absurd is suspect) but is not persisted — see the Goal's note.

### 2.6 Per-leg accumulation and output

Walk the resulting path's edges via `accumulate_path` to collect `dist`, `road_m`, `ungraded_m`,
`inferred_m`, `ascent_m`, `descent_m`, **`max_ele_m`**, max `sac_rank`, `via_ferrata` (OR across
edges), the full-resolution geometry, and the base edge ids. Then apply the **same endpoint
treatment `build_hub_edges.py` applies**, or tour legs will read systematically shorter than the
equivalent hut edge and their polylines won't start at the hut marker:

- `snap_m = src_snap.gap_m + tgt_snap.gap_m`, folded into `distance_m` and stored in its own column.
- `gap_dz_m` folded into `ascent_m`/`descent_m` by direction, exactly as
  `compute_hub_edges_for_cell` does.
- Geometry is `[(hut_lon, hut_lat), *path.coords, (hut_lon, hut_lat)]`.
- A snap of kind `SNAP_KIND_EDGE` (mid-chain, `lib/edge_split.py`) is not a graph node — it must be
  inserted as a virtual vertex the way `build_base_igraph_arrays` already does. "The same node
  `hub_snaps.npy` recorded" is only true for `SNAP_KIND_NODE`.

**Refactor this needs:** the record packing (`RECORD_DTYPE` fill, geometry content-hash dedup,
`edge_ids`/`prefix_ids`/`suffix_ids` population) currently lives inline in
`build_hub_edges.py:_write_edge_output`. Factor *that* out into `lib/` and call it from both.
`accumulate_path` is already standalone in `lib/cell_igraph.py` and needs no extraction.

**Output** (`data/osm/tour_edges/`, same directory shape as `hut_edges/`/`start_edges/`):

- `records.npy` — `RECORD_DTYPE`, unchanged (no new columns on the shared dtype, so this doesn't
  force a schema-version bump or rerun on `hut_edges`/`start_edges` consumers). `from_type`/
  `to_type` are always `TYPE_HUT`. `variant` is a new sentinel, `VARIANT_OFFICIAL` (add to
  `binfmt.py` alongside `VARIANT_FAST_ANY`/etc. — a tour leg is not a member of the
  `graph.variants` search grid, so it must not collide with an existing variant id). Note this also
  adds a key to `binfmt.VARIANT_NAMES`, which `build_edge_payload.py` embeds in every payload
  manifest — `hut-edge-payload.json` changes by one key as a result (the `.bin` does not).
  `geom_offset`/`geom_count` and `profile_offset`/`profile_count` populate exactly as `hut_edges`
  does today. `edge_id_offset`/`edge_id_count`/`prefix_ids`/`suffix_ids` (the overlap-check columns
  from `docs/superpowers/specs/2026-08-29-avoid-overlapping-tracks-design.md`) are populated the
  same way `hut_edges` populates them (`write_edge_ids=True`).
- `geometry.npy` — `COORD_DTYPE`, full-resolution routed geometry, same as `hut_edges`.
- `edge_ids.npy` — same shape as `hut_edges/edge_ids.npy`. **Not shipped**: `build_edge_ids.py` gets
  no third invocation here, so the overlap columns stop at the pipeline boundary. That is
  deliberate — no search-side feature consumes them for tours yet — but it means "free correctness
  if official tours are ever mixed into overlap-aware search" costs one extra dag task at that time,
  not zero.
- `tour_meta.npy` — **new, tour-specific sidecar**, row-aligned 1:1 with `records.npy` (not folded
  into `RECORD_DTYPE` itself, to avoid touching the shared dtype other consumers depend on):
  `TOUR_META_DTYPE = [("tour_id", "u1"), ("leg_index", "u1")]`. 25 tours × ≤9 legs each fits `u1`
  comfortably.
- Legs that hit a gap (§2.5) are simply absent from `records.npy` — `tour-match-gaps.json` is the
  record of what's missing and why, same pattern as `unsnapped_huts.json`.

**doit wiring**: `task_dep=["compute_edge_profiles", "snap_hubs"]` — **not** a `file_dep` on
`base_graph/edges.npy`. `compute_edge_profiles` rewrites `edges.npy` in place without owning it as a
target (`build_base_graph` does), and signals completion through `base_graph/edge_profiles.stamp`;
`file_dep` on `edges.npy` alone cannot express "post-profiles". This is the same wiring
`task_snap_hubs`/`task_gather_route_subgraphs` already use, with the same reasoning in their
comments. Plus `file_dep=[hub_snaps.npy, hub_snap_interior.npy, tours.json, tour_traces.json]`,
`targets=[tour_edges/records.npy, tour_edges/geometry.npy, tour_edges/edge_ids.npy,
tour_edges/tour_meta.npy, tour-match-gaps.json]`. No `tourEdgeSchemaVersion` param is needed — this
task doesn't own `RECORD_DTYPE`, so it never moves `record_schema_version` and never forces a
`build_hub_edges` rerun.

### 2.7 Spike before committing

Implement §2.2 (reassembly) and §2.3 (corridor routing) far enough to run **CGT (45 fragments, 771
points) and SVR7T (51 fragments, 682 points, 102 m/point)** end to end, and compare the routed legs
against the AV geometry. Those two are the worst inputs in the dataset; if corridor routing holds
there, §2.4 is not needed. Decide on measured match quality, not on preference.

## 3. Postprocessing — the "third invocation" is not free

**Correcting an assumption in this spec's first draft:** the three postprocessing scripts are *not*
uniformly parametrized over `--edges-dir`/`--layer-name`, and `dodo.py` does *not* invoke each
twice. Actual state:

| script | `--edges-dir`? | invocations today | work needed |
|---|---|---|---|
| `build_edge_tiles.py` | yes | 2 (`hut_edges`, `start_edges`) | none — add a third task |
| `build_edge_payload.py` | yes | **1** (`hut_edges` only) | add a second task + the `tour_meta` extension |
| `build_profiles.py` | **no** | **1**, looping internally | parametrize it |

- **`build_profiles.py` needs real changes.** It takes no `--edges-dir` and hardcodes
  `for name in ("hut_edges", "start_edges")` (`phases/elevation/build_profiles.py:173`). Either add
  `--edges-dir` (repeatable) or extend that tuple; either way `dag/elevation.py:task_build_profiles`
  gains `tour_edges/records.npy` in `file_dep`, `tour_edges/profiles.npy` in `targets`, and a
  `task_dep` on `match_tour_edges`. Note it rewrites `records.npy` in place without owning it as a
  target — which is precisely why every downstream tile/payload task uses
  `task_dep=["build_profiles"]` rather than a file_dep link. `tour_edges` follows the same pattern.
- `build_edge_tiles.py --edges-dir tour_edges --layer-name tour_edges` → `tour-edges.pmtiles`,
  `tour-edge-stats.json`, `tour-edge-geometry.bin`/`.json`. `--id-table` is `required=True` and must
  still be passed (`start_points_id_table.json`) even though tour records are hut-only.
- `build_edge_payload.py --edges-dir tour_edges` → `tour-edge-payload.bin`/`.json`, plus a small
  addition: payload rows must carry `tour_id`/`leg_index` for the client to reconstruct "which tour
  is this leg part of". Extend `build_edge_payload.py` to optionally fold in a sidecar array
  (`tour_meta.npy`) as two extra payload columns when present — additive;
  `hut_edges`/`start_edges` payloads are unaffected since neither directory has a `tour_meta.npy`.
- Ship `tours.json` (§1, the metadata half only) as the small file the client fetches directly for
  the tour list/detail UI. `tour_traces.json` stays internal.
- Add `tour-edges.pmtiles`, `tour-edge-stats.json`, `tour-edge-geometry.bin`/`.json`,
  `tour-edge-payload.bin`/`.json`, `tours.json`, `tour-fetch-gaps.json` and `tour-match-gaps.json`
  to `dodo.py`'s `PUBLIC_FILES` and the new tasks to `DOIT_CONFIG["default_tasks"]`.

## 4. Access edges — no new pipeline work

A tour's start/end are existing hub huts (drawn from the same hut set `start_edges`/
`approaches.bin` already cover). The client answers "how do I reach this tour" by looking up the
existing approach table (`approaches.bin`/`.json`, `build_approach_table.py`) keyed by the tour's
first/last hut index (either endpoint, for a `Rundtour`) — no tour-specific access-edge computation
is needed, and none is proposed here.

## 5. Filtering — scoped to this dataset only

This section applies **only** to `tour_edges/`, not to `hut_edges/`. Free-form hut-to-hut browsing
keeps its full `graph.variants` grid (`FAST_ANY`/`FAST_T2`/`FAST_T3`/`FAST_T3_UNGRADED`) exactly as
it works today — unaffected by anything in this spec.

For official tours specifically: since a leg's geometry is constrained to the one route the AV
publishes, there is nothing to search among — `graph.variants` does not apply as a *routing* choice,
hence `VARIANT_OFFICIAL` rather than reusing one of the search variant ids. The per-leg facts that
do carry over (`sac_rank`, `via_ferrata`, `ungraded_m`, `max_ele_m`, all populated on `records.npy`
exactly as for `hut_edges`) let the client filter/display *which tours* to show by difficulty tier,
but not offer alternate physical routes for a given tour.

## Out of scope (explicitly deferred)

- Client-side rendering/UI for tours (tour list, detail panel, hover profile) — this spec covers
  only the pipeline's data contract; consuming it in `huts/` is separate follow-up work.
- `Wiener Höhenweg` and `MontafonerSilvrettarunde` (both `Huettenliste` empty) — geometry exists but
  there is no hut chain to split legs against; left out of matched-leg output until a hut list is
  available, tracked as a known gap rather than guessed at.
- Legs outside the AT+Bayern OSM extract — **Switzerland** (SVR7T's `Tuoi Chamonna CAS`) as well as
  South Tyrol (RFD4T). A real coverage limit of `pipeline.config.json`'s region list
  (`["austria", "bayern"]`), not something this feature works around; surfaced via
  `tour-match-gaps.json`, fixed only by extending pipeline region scope (out of scope here).
- The 9 legs lost to unsnapped tour huts (§0.3) — the root cause is `snap_hubs.py`'s
  `vertical_offset`/`gap_too_far` rejection for those specific huts, which belongs to the snapping
  layer, not here. Recorded, not worked around.
- `tourSelection.php` (mentioned in `docs/alpenverein-api.md` §3) — never observed in the HAR
  capture, response shape unconfirmed; not needed since `AVT_CAA_TOUR_View_L` already supplies
  geometry + hut list directly.
- Mixing official tours into the "avoid overlapping tracks" search (`docs/superpowers/specs/
  2026-08-29-avoid-overlapping-tracks-design.md`) — `tour_edges/` populates the same overlap-check
  columns (§2.6), but they are not shipped and no search-side feature consumes them yet.

## Testing

- **`fetch_tours.py`**: unit test the `#DUMMY` filter (it has a *non-empty, resolvable*
  `Huettenliste`, so the test must confirm filtering is by `Kurzbezeichnung`), the empty-hut-list
  case (two tours), and the `Huettenliste` GUID → hut-index join including the unresolvable case —
  asserting it lands in `tour-fetch-gaps.json` **and splits the chain**, rather than being dropped
  from the middle of an ordered list.
- **Fragment reassembly (§2.2)**: unit test the greedy endpoint-join against a synthetic scrambled
  multi-part polyline (including a reversed fragment and one real break), plus an integration check
  that all 25 real tours reassemble into the expected number of chains.
- **Leg boundaries**: unit test hut→chain-position assignment against a synthetic chain and known
  hut coordinates, including the "hut too far from the chain" gap case at the 250 m threshold.
- **Corridor gather (§2.3)**: unit test that a corridor built from a tiny synthetic `base_graph/`
  fixture contains the expected edges and excludes edges just outside the buffer.
- **Golden end-to-end**: use a **single-part** tour, not Chiemgautour — CGT is 45 fragments over 771
  points and is one of the two hardest inputs in the set (it belongs in the §2.7 spike, not in a
  golden test). `LQR` (1 part, 6206 points, 4 huts, 3 legs, no unsnapped huts) or `WelserHöhenweg`
  (1 part, 4 huts) are the right shape. Assert the routed edge sequence is connected end to end,
  touches both huts' known snap points, and sums to sane distance/ascent (order-of-magnitude check
  against the tour's known real-world stats, not exact equality).
- **`Rundtour` closing leg**: a loop tour yields N legs, not N−1, and `leg_index` is contiguous.
- **Gap handling**: each §2.5 reason produces a `tour-match-gaps.json` entry with tour/leg identity
  and **does not** produce a `records.npy` row. Cover `hut_unsnapped` explicitly with RFD4T, which
  must yield zero rows, and TT4T, which must yield exactly its closing `Rundtour` leg.
- **Endpoint treatment (§2.6)**: a leg's `distance_m` includes `snap_m` and its geometry's first and
  last points are the huts' own coordinates — the same invariants `hut_edges` rows satisfy.
- **`build_edge_payload.py` tour-meta extension**: round-trip test — with a `tour_meta.npy` present,
  payload output gains the two extra columns; without it (the `hut_edges`/`start_edges` case), the
  **`.bin` is byte-identical** to today's. Scope the assertion to the binary: the manifest gains a
  `VARIANT_OFFICIAL` key from `binfmt.VARIANT_NAMES` regardless.
