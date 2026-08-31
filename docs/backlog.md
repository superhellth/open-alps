# Backlog

Cross-cutting data/pipeline problems that don't belong to one spec. Short summaries only — full
explanation, evidence and pointers live in the dedicated file under `docs/backlog/`. Newest-highest-
priority first within each section. An item graduates out of here when it gets its own spec or plan
under `docs/superpowers/`.

## High

### [Access-node coverage and quality (`stations.geojson` / `parking.geojson`)](backlog/access-node-coverage.md)

`stations.geojson` is railway-only (no bus stops), and unusable nodes (disused stations, private/
gated parking) aren't filtered out. Measured: 3 of 4 terminal tour endpoints have no access node
within 100 m, and every failing case is a bus stop.

### [Hut catalog gaps — privately-run mountain inns](backlog/hut-catalog-privately-run-inns.md)

Real overnight stops on tours (e.g. the Weinbergerhaus Berggasthof) are neither Alpine Club huts nor
Bergsteigerdörfer partner businesses, so they're absent from every hub layer.

## Medium

_(none yet)_
