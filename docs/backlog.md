# Backlog

Cross-cutting data/pipeline problems that don't belong to one spec. Short summaries only — full
explanation, evidence and pointers live in the dedicated file under `docs/backlog/`. Newest-highest-
priority first within each section. An item graduates out of here when it gets its own spec or plan
under `docs/superpowers/`.

## High

## Medium

### [Hut catalog uses a rectangular bbox, pulling in huts outside AT+Bavaria trail coverage](backlog/hut-catalog-bbox-includes-foreign-huts.md)

`fetch_huts.py` filters to a rectangular bbox, not real borders — 205 South Tyrol/Slovenia/Swiss
huts land in `huts.geojson` with zero trail data anywhere near them, showing up as unexplained
`snap_health` `gap_too_far` failures (205 of the 725 flagged in the 2026-09-03 rebuild).

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

### Stable hut ids

At the moment hut ids are sequential, not stable

### Strucute data/ folder

At the moment the data/ folder is quite a mess. Lets enforce more structure onto it.
resume data-orga

## Low

### [Frontend disclaimer for via_ferrata / high-SAC-grade legs](backlog/steep-terrain-time-disclaimer.md)

Once the steep-terrain time model spec lands, legs touching via_ferrata/T5-T6 terrain should warn
that the time estimate is approximate — no pipeline change needed, `sac_rank`/`via_ferrata` are
already in the edge payload.

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

### Pipeline config file restructure

There are some hard to understand entries in the current config file. Maybe we can simplify it or also orga by phase.