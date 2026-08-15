# data/ — hut-to-hut routing graph pipeline

A separate, not-yet-integrated effort to build a hut-to-hut trail graph (nodes = huts, edges =
real trail paths/distances) so route planning isn't limited to the Alpenverein's 26 predefined
tours (`toursearchApi` / `AVT_CAA_TOUR_View_L`, see `docs/alpenverein-api.md` §3). Edges are
derived from OSM hiking ways, not the Alpenverein data.

This is entirely an offline precompute pipeline living under `data/` — it does not touch `huts/`
yet and doesn't change the app's backend-free architecture; the eventual output ships as a static
GeoJSON asset for the app to fetch. Full reproduction steps and scripts: **`data/README.md`**.
Design rationale for the OSM extract/filter/merge steps: **`docs/osm-trail-pipeline.md`**.

Pipeline is plain Python, no bash/Node/Docker: config-driven — every hyperparameter (region list,
hut bbox, trail tag filter, max-edge-km / max-snap-m) lives in `data/pipeline.config.json` — and
`data/scripts/run_all.py` runs the whole thing end to end, idempotently, inside the `alpen-osm`
conda env (see `data/README.md` "Setup" for how that env was created — via `micromamba`, not
`conda create`, since this machine's `base` conda env hangs solving `-c conda-forge` specs).
Current status: `data/osm/hut-edges.geojson` (hut-to-hut edges, distance-capped shortest paths
over the full unclipped trail network via streamed pyosmium + igraph) is built and up to date for
Austria+Bavaria. Not done: wiring it into `huts/` as a fetched asset, and extending scope past
AT+Bayern.
