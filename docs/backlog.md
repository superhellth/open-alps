# Backlog

Cross-cutting data/pipeline problems that don't belong to one spec. Short summaries only — full
explanation, evidence and pointers live in the dedicated file under `docs/backlog/`. Newest-highest-
priority first within each section. An item graduates out of here when it gets its own spec or plan
under `docs/superpowers/`.

## High

### Stable hut ids

Hut and edge ids are array positions in the emitted payloads, not stable identities — `hut_ids` is
indexed by array order and `edge_id` indexes the geometry payload the same way, so any pipeline
rerun that reorders either one silently remaps every reference to it.

This blocks trip persistence in the Trip Planner Reenvision design
(`docs/superpowers/specs/2026-09-04-trip-planner-reenvision-design.md`): a saved trip stored in
`localStorage` references huts and edges by those ids, so after a rerun it would render as a
*different but plausible-looking* trip with nothing visibly broken. The fix is emitting ids that are
stable across runs, not client-side staleness heuristics — the spec deliberately designs no UI
mitigation.

## Medium

### [Search-result tour legs render as straight lines (stale stations/parking data)](backlog/straight-line-legs-stale-start-points.md)

`stations.geojson`/`parking.geojson` in `huts/public/data/` were regenerated separately from and
older than `approaches.bin`/`hut-edge-payload.bin`, so ~1/3 of sampled start-point ids the routing
graph references don't resolve — silently degrading every leg of the affected chain to a straight
line. Also flags a related frontend robustness gap in `chainToRoute`.

### Diagnose and improve performance of slow phases

### Strucute data/ folder

At the moment the data/ folder is quite a mess. Lets enforce more structure onto it.
resume data-orga

### Does AV/sonstige split make sense?

Albert Appel Haus classified as sonstige

### Surface data-quality signals to the frontend

Trip Planner Reenvision design (`docs/superpowers/specs/2026-09-04-trip-planner-reenvision-design.md`)
raised low trust in route suggestions as a driver, but that's a pipeline-layer concern, not a UI
feature — the real fix is in the pipeline/data-quality-monitoring work. Once that work produces
per-leg/per-route quality signals, revisit whether/how the frontend should surface them.

## Low

### How to avoid road in hut-to-hut and access legs in a consistent and solid way

### [Hut catalog gaps — privately-run mountain inns](backlog/hut-catalog-privately-run-inns.md)

Real overnight stops on tours (e.g. the Weinbergerhaus Berggasthof) are neither Alpine Club huts nor
Bergsteigerdörfer partner businesses, so they're absent from every hub layer.

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

### Check: Does check_graph_building always run?

### Claude skill to auto link huts with their website / find booking times

### doit dag visualization in official repo