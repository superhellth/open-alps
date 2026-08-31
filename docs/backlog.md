# Backlog

Cross-cutting data/pipeline problems that don't belong to one spec. Newest-highest-priority first
within each section. An item graduates out of here when it gets its own spec or plan under
`docs/superpowers/`.

## High

### Access-node coverage and quality (`stations.geojson` / `parking.geojson`)

**Problem, two halves:**

1. **Bus stops are missing entirely.** `stations.geojson` is railway-only — all 3,025 features carry
   ÖBB-shaped properties (`{"name": "Wien Ottakring", "operator": "ÖBB-Infrastruktur AG"}`) and not
   one has a `highway=bus_stop` / `public_transport` tag. Real hut tours overwhelmingly start and
   end at a *bus* stop, not a train station.

2. **Unusable nodes are not filtered.** Disused/abandoned/`railway=disused`-style stations, and
   parking that is private/gated (`access=private`, `barrier=*`), are currently kept as routable
   access points. `start_points_id_table.json` already carries `access`/`motor_vehicle`/`barrier`
   per point but they are `null` across the sample inspected — so either the tags aren't being
   exported or they aren't being used to filter.

**Measured impact** (2026-08-31, against the two tour folders in `pipeline/tours/`): 3 of 4 terminal
tour endpoints have no access node within 100 m.

| Endpoint | nearest hut | nearest station | nearest parking |
|---|---|---|---|
| Welser Höhenweg leg 1 start — Bushst. Schiederweiher, Hinterstoder | 4,500 m | 9,669 m | 2,165 m |
| Kaisertour leg 1 start — Ebbs | 2,542 m | 4,411 m | 2,286 m |
| Kaisertour leg 4 end — Hst. "Steinerne Stiege" | 4,717 m | 4,359 m | 3,836 m |
| Welser Höhenweg leg 5 end — Rettenbachalm (works) | 6,977 m | **43.8 m** | 51.7 m |

Every failing case is a bus stop. The one that succeeds is near a rail station.

**Why high priority:** this is the layer every point-to-point tour depends on to have a usable
start and end, and it blocks tour ingestion from resolving real trailheads. It is also a genuine
root-layer fix per `CLAUDE.md` — the tour pipeline must not work around it with a looser threshold
or a synthetic endpoint.

**Where:** `pipeline/phases/downloads/fetch_stations_parking.py` (osmium export — widen the tag
filter to bus stops), then `pipeline/phases/preprocessing/filter_start_points.py` (add the
usability filter). Both feed `start_points.npy`, so `TYPE_STATION`/`TYPE_PARKING` semantics and
`lib/hubs.py` are unaffected.

**Cost note:** re-running `fetch_stations_parking` + `filter_start_points` is cheap, but everything
downstream of the hub set (`snap_hubs`, `build_hub_edges`, `start_edges`) is not. Needs the usual
explicit go-ahead per `CLAUDE.md`.

### Hut catalog gaps — privately-run mountain inns

Tour stages legitimately overnight at Berggasthöfe that are neither Alpine Club huts
(`huts.geojson`) nor Bergsteigerdörfer partner businesses (`partner_betriebe.geojson`, only 110
features nationwide).

**Concrete case:** Kaisertour's leg 3→4 boundary is the **Weinbergerhaus (Berggasthof)** — named as
such in the GPX's own `<trkpt><name>`. Nearest `huts.geojson` entry is Kaindlhütte at **2,101 m**;
nearest partner business is 72 km away. So the stop exists, is a real overnight hut, and is in
neither catalog.

This is a **data-coverage problem, not an algorithmic one** — the fix is to get such places into a
hub layer, not to loosen snapping thresholds or invent per-tour endpoint types.

**Open question:** which layer they belong in — an extension of `partner_betriebe.geojson`, a new
`TYPE_*`, or a source other than the AV catalog entirely.

## Medium

_(none yet)_
