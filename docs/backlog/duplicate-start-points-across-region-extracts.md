# Duplicate start points where the region extracts overlap

**Priority:** Medium

`start_points.npy` holds 236 redundant rows: the same `(type, osm_id)` entered twice as two
separate hubs, always at byte-identical coordinates and never more than twice.

| layer | rows | distinct `osm_id` | redundant |
| --- | --- | --- | --- |
| station | 74,411 | 74,211 | **200** |
| parking | 12,225 | 12,189 | **36** |
| partner_betrieb | 110 | 110 | 0 |

`start_points_id_table.json` is keyed by `osm_id`, so it holds exactly one entry per distinct id
and the duplicates are invisible from that side — id-table coverage is 100% for all three layers.

## Cause

The 472 rows involved in a duplication sit in a narrow band: latitude 47.379–48.698 (p5 47.461,
p95 48.021), longitude 9.734–13.831, with 442 of 472 between 47.4 and 48.2 N. That is the
Austria/Bavaria border. `pipeline.config.json` lists two overlapping region extracts
(`austria-latest.osm.pbf`, `bayern-latest.osm.pbf`), `fetch_stations_parking.py` runs its tag
filter and export **per region** (its `StepTimer` steps are literally `<layer>_tag_filter` /
`<layer>_export` per layer × region), and a node near the border is present in both. Nothing
deduplicates on the merged result — contrast `merge_trails.py`, which exists precisely to handle
the overlap for the trail extracts.

`partner_betrieb` having zero duplicates fits: it comes from the ArcGIS layer, not from the OSM
extracts.

## Why it matters

Each duplicate is a second hub at the same coordinates, so it snaps separately, routes separately,
and produces its own full set of `access_distances` and `start_edges` rows. Concretely:

- `select_approach_pairs.py` takes the top-k per `(hut_id, start_type)`, so a duplicated station
  can occupy two of a hut's 20 selected slots with the same physical place.
- `build_approach_table.py` can then hand the client two identical approaches, and the loop-closure
  reverse index ships both.
- It also wastes two routing passes per duplicate across four variants.

This is small in absolute terms (236 of 86,746 hubs, 0.3%) but it is exactly the kind of thing that
degrades a *result list* rather than an aggregate: the affected huts are near the border, and a
user searching there sees the same trailhead twice.

Fix is a dedupe on `(type, osm_id)` at the end of `filter_start_points.py`, which is already the
script that merges the per-region layers into `start_points.npy`. Worth checking at the same time
whether the same overlap duplicates anything in `stations.geojson`/`parking.geojson`, which are
shipped to the client directly.

Found while measuring baselines for the data-quality monitoring layer
(`docs/superpowers/specs/2026-09-02-data-quality-monitoring-design.md` §4.1.1, which turns this
into a standing check).
