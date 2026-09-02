# Backlog

Cross-cutting data/pipeline problems that don't belong to one spec. Short summaries only — full
explanation, evidence and pointers live in the dedicated file under `docs/backlog/`. Newest-highest-
priority first within each section. An item graduates out of here when it gets its own spec or plan
under `docs/superpowers/`.

## High

### [start_edges ignores the max-edge range cap](backlog/start-edges-range-cap-violation.md)

100,592 of 471,196 `start_edges` rows (21%) exceed `graph.maxEdgeKm`, up to 267,637 m with 12,903 m
of ascent — routed paths with real geometry, shipped into the approach table's reverse index.

### [Routed edge geometry drops trail detail](backlog/hut-edge-geometry-drops-trail-detail.md)

1,438 straight hops over 500 m (worst 3,929 m) across 700 of 8,238 `hut_edges` records, none of
them at an endpoint. Base graph, subgraph cache and mid-chain snaps are all ruled out.

### [Approach table drops a reserved source-type slot](backlog/approach-reserved-type-slot-overwrite.md)

`select_approaches` writes every reserved source-type slot into `selected[-1]`, so when two types
are missing from the top-k the second clobbers the first — 160 of 613 huts with candidates (26%)
lose an available source type on the 2026-09-02 run.

![alt text](image.png)
![alt text](image-4.png)
![alt text](image-3.png)
ui issue or pipeline bug?

![alt text](image-5.png)
![alt text](image-6.png)
unnecessary hut-to-hut edge retracing. Why doesnt alg find better non-overlapping solution?

## Medium

### [Degenerate zero-length start_edges rows](backlog/degenerate-zero-length-start-edges.md)

82,017 rows (17%) carry `max_ele_m == 0`; all are sub-166 m snap-coincident legs whose unset
maximum elevation is written as sea level into the column the client's altitude cap reads.

### [Base-graph time_s has a nonsense tail](backlog/base-graph-time-s-outliers.md)

1,011 edges imply under 0.05 m/s, 20 exceed a year, worst 2.95e12 s for a flat 118 m edge — silent
barriers that also poison the key `select_approach_pairs.py` ranks on.

### [Hut catalog gaps — privately-run mountain inns](backlog/hut-catalog-privately-run-inns.md)

Real overnight stops on tours (e.g. the Weinbergerhaus Berggasthof) are neither Alpine Club huts nor
Bergsteigerdörfer partner businesses, so they're absent from every hub layer.

### Extend overlap avoidance to approach/exit legs

The 2026-08-29 overlap-avoidance work (`docs/superpowers/specs/2026-08-29-avoid-overlapping-tracks-design.md`)
only covers hut-to-hut legs. Approach legs (start point → first hut) and exit legs (last hut →
start point) carry their own `base_edge_id`s but are never checked against `usedEdgeIds` in
`search.ts`, so a suggested tour can still walk in or out over a trail segment another leg in the
chain already used. Needs the same edge-id treatment threaded through the start-edges data (flagged
as a 147 MB-class sidecar problem to solve first in the original design's "Out of scope" section).

### Make legs of selected tour hoverable

Atm the legs of the selected tour in the frontend are displayed but are not hoverable. Height profile should be displayed somewhere, making it more interactive

### No point-by-point elevation profile for approach/exit legs

Hut-to-hut legs carry a point-by-point `elevation_profile` in `hut-edge-stats.json`, but
`start-edge-stats.json` (the equivalent for approach/exit legs) is deliberately excluded from
`PUBLIC_FILES` (654 MB, no consumer per `docs/superpowers/specs/2026-08-27-tour-geometry-design.md`),
and `start_edges/records.npy` doesn't carry the profile at all today. So a tour's first and last leg
can never get a height-profile chart, only aggregate `ascent_m`/`descent_m`. Needs a pipeline change
to compute/emit a simplified, byte-range-fetchable elevation profile for `start_edges` (mirroring the
`hut-edge-geometry.bin` approach for lon/lat, not a 654 MB inline JSON blob), before "make legs
hoverable" above can cover the whole tour instead of just the hut-to-hut middle.
In general we want to ensure hut-to-hut and access legs to be treated as similarly as possible and
to share as much code as possible.

### Stable hut ids

At the moment hut ids are sequential, not stable

### Strucute data/ folder

At the moment the data/ folder is quite a mess. Lets enforce more structure onto it.
resume data-orga

### Refactor frontend code

Atm code is quite unstructured not skill-checked with improve codebase architecture

## Low

### [Exact approach selection via a scalars-only path walk](backlog/exact-approach-selection-scalars-only-path-walk.md)

Drops `accumulate_path`'s coordinate accumulation to get true ascent/descent in the distance pass,
making approach selection exactly equal to today's instead of a top-20 over-selection. Only
actionable after the hub-edge scaling spec's §A+§B land.

### Include Aerial lift in access nodes?

Explore if it would make sense to include aerial lifts in access nodes or as routable way. Nice to have for a later point

### Settle invariant: official/third-party tours - dont ship gap legs

At the moment the third-party/official/folder-ingestion part of the pipeline emits a document that contains gap legs. Should be reported in the data quality layer, not shipped to frontend

### GPX Tool

A small webpage that helps bring GPX tours into a format the pipeline can ingest. Should support: Extending legs to a proper end (dont end on a mountain like Chiemgautour), slicing into legs, as some Tours are one big tour, not split into legs. So needs huts overlay, quality of life features.

### Idea: Introduce a pipeline explanation/visualization

Probably in form of a static web page, either as part of the existing frontend or a new one. May be combined with the data quality monitoring layer.

### Idea: Introduce a data quality monitoring layer

Simplest would be output files in a dedicated folder that collect monitoring data about our data. More sophisticated be something like a proper dashboard.

### Pipeline config file restructure

There are some hard to understand entries in the current config file. Maybe we can simplify it or also orga by phase.

### superpowers spec/ and plan/ history

I am losing oversight over which specs have plans and which plans were implemented. How do we tread historical docs?