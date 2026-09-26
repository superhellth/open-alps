# Backlog

Cross-cutting data/pipeline/ui problems that don't belong to one spec. Short summaries only — full
explanation, evidence and pointers live in the dedicated file under `docs/backlog/`. Newest-highest-
priority first within each section. An item graduates out of here when it is resolved.

## High

### How to handle alpenvereinaktiv tours

### Broken tour geometry in tour detail view

## Medium

### Close tours that start / end in nearby locations

### Avoid overlaps in displayed tours

### Surface data-quality signals to the frontend

Trip Planner Reenvision design (`docs/superpowers/specs/2026-09-04-trip-planner-reenvision-design.md`)
raised low trust in route suggestions as a driver, but that's a pipeline-layer concern, not a UI
feature — the real fix is in the pipeline/data-quality-monitoring work. Once that work produces
per-leg/per-route quality signals, revisit whether/how the frontend should surface them.

## Low

### Cluttered place names in huts, stations and parking

Raw source names reach the UI: parking names that are whole signs, `;`-joined station variants,
hut names with parenthesised alternates. Clean display names belong in the pipeline. Details:
`docs/backlog/cluttered-place-names.md`.

### Same hut booking analysis for Die 7 schönsten AV-Hüttentouren

### Try to reintroduce a signpost feel to resultslist cards

### GPX export and print view for trips

The named follow-ons of "Take along" in the Trip Planner Reenvision spec; the share link shipped,
GPX export and a print view did not.

### Contact info for direct-booking-only huts

The trip panel says "die Hütte selbst kontaktieren" because `huts.geojson` carries no phone/e-mail;
a data (pipeline) addition would let the UI show contact info instead.

### Phone view for shared trips

Trip Planner Reenvision (`docs/superpowers/specs/2026-09-04-trip-planner-reenvision-design.md`) is
desktop-only, but trips are used on a phone in the mountains. A read-only single-column trip view
(stages, huts, dates, booking/contact, status) as the share-link landing — possibly doubling as
the print view.

### How to avoid road in hut-to-hut and access legs in a consistent and solid way

### Colocate tests in phases/

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

### Idea: Introduce a pipeline explanation/visualization

Probably in form of a static web page, either as part of the existing frontend or a new one. May be combined with the data quality monitoring layer.

### Claude skill to auto link huts with their website / find booking times

### Check DIN walking time handling