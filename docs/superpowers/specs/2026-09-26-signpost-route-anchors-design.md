# Discover map: signposts stand on their tour

## Problem

From `ROUTE_REVEAL_ZOOM` on, a Discover signpost (single board or stack) sits at its tour's **start
point** and points away from it (`headingOf` in `DiscoverLayer.tsx`: east/west by the first leg).

- **Redundant.** The start point is already drawn and hoverable as a waypoint symbol
  (`WaypointLayer`); hovering it highlights every tour from there. The board adds a second marker to
  the same spot.
- **Cluttered.** Every tour from one start stacks its board onto that one point, the densest spot on
  the map (stations and car parks serve many tours), and far from where most of each tour runs.
- **Weak link to the line.** The board says nothing about where the tour's route runs. With several
  tours leaving one station, nothing on the map ties a board to its line until it is hovered.

The anchor can't be computed well from what the client holds at search time: it has the waypoint
coordinates (start, huts, exit) and each leg's `distance_m`, but the real leg polylines load lazily
from pmtiles (`loadLegGeometry`). A point on the straight chord between two huts can lie a kilometre
or more off the trail, which is plainly visible from zoom 11 on.

## Goals

1. From `ROUTE_REVEAL_ZOOM` on, each tour's board stands **on its own route**, near the middle of the
   tour, not at the start point.
2. The board does not cover its own route line.
3. The anchor is known synchronously at search time: no geometry fetch per tour, no boards popping
   in or jumping once tiles arrive.
4. The zoom levels below `ROUTE_REVEAL_ZOOM` behave as today (count bubbles grouped by start point).

Out of scope: collision-aware placement across boards (greedy candidate selection against other
boards and waypoint symbols). It's a later stage that reuses the candidates this spec ships.
Also out of scope: choosing the anchor on a leg that is unique to the tour (fewest shared tours).
It can be added on top of the same candidates once the midpoint rule is in use.

## Design

### 1. Data contract: anchor points per edge (pipeline)

Every shipped edge row carries **three anchor points** on its real path, at 25 %, 50 % and 75 % of
its arc length, measured on the full-resolution `geometry.npy` polyline (not the simplified tile
geometry). The quantity is a generic geometric fact about the edge, like `distance_m` or `max_ele_m`,
so it belongs in the payload and is not a UI-specific reshaping.

**Encoding** (both binary payloads, per-column like every other column, see
`docs/tour-suggestion-payload.md` §1):

| column | dtype | meaning |
|---|---|---|
| `a25_dlat`, `a25_dlng` | i2 | anchor at 25 % of arc length, stored direction |
| `a50_dlat`, `a50_dlng` | i2 | anchor at 50 % |
| `a75_dlat`, `a75_dlng` | i2 | anchor at 75 % |

- Values are offsets from a **reference coordinate** in units of 1e-4° (≈ 11 m north–south, ≈ 7.6 m
  east–west at 47° N; about 1.5 px at zoom 14). The i2 range (±3.27°) is far beyond any edge's extent.
  The build asserts that no offset overflows.
- Reference coordinate: the **hut's coordinate as shipped in `huts.geojson`**, which is the same
  coordinate the client puts into `RouteContext.hutCoordsById`.
  - `hut-edge-payload`: the `from_id` hut.
  - `approaches`: the row's hut (every approach row is `access point → hut`).
  - The reference is arithmetic only; the geometry's own endpoints (snapped trail points) may differ
    from it by `snap_m`. The anchors are exact trail points regardless.
- **Direction.** "25 %" is measured in the row's stored direction (`from → to`, `access point → hut`).
  A leg walked reversed swaps the 25 % and 75 % anchors; 50 % stays. This is the same trap as §3 of
  the payload doc and is documented there.

**Official tours.** `tours.json` legs get the same three anchors as absolute `[lat, lng]` pairs
(`anchors: [[lat, lng], [lat, lng], [lat, lng]]`), in leg walking order, from the raw GPX trace.
Official tours are few and the file is JSON, so no quantisation is needed.

**Where it is computed.**

| Output | Script | New input |
|---|---|---|
| `hut-edge-payload.*` | `phases/postprocessing/build_edge_payload.py` | `hut-edges/geometry.npy` (add to `task_build_edge_payload`'s `file_dep`) |
| `approaches.*` | `phases/postprocessing/build_approach_table.py` | `start-edges/geometry.npy` (add to `task_build_approach_table`'s `file_dep`) |
| `tours.json` | `phases/graph_building/match_tour_edges.py` | its own matched leg geometry |

One shared helper in `pipeline/lib/` computes arc-length-interpolated points (haversine segment
lengths, linear interpolation inside the segment that crosses the target fraction). The payload
builders and tour matching both call it.

**Size.** Currently ~10.7 k rows (7,306 hut-edge + 3,389 approach), ~214 KB gzipped together. The
anchors add 12 B/row, ≈ 128 KB raw. The plan's pipeline step measures the gzipped delta and writes
it to `data/analysis/payload_sizing.json`. If the gzipped growth exceeds **+60 KB**, ship only the
50 % anchor (`a50_*`, 4 B/row) and treat the viewport fallback in §2 as leg-midpoints only. The
choice is recorded in the payload doc.

**Checks.** `phases/quality/check_postprocessing.py` asserts, for a sample of rows, that each decoded
anchor lies within 25 m of the edge's full-resolution polyline.

### 2. Anchor choice (client)

The loaders (`loadHutEdges.ts`, `loadApproaches.ts`, `loadOfficialTours.ts`) decode anchors to
absolute `{ lat, lng }` per edge, in stored direction. `tourSearch/` gets a pure function:

```
tourAnchor(tour, ctx, viewBbox) -> { lat, lng, heading: 'east' | 'west' } | null
```

- **Candidates.** Every anchor of every leg, oriented to walking order (reversed legs swap 25/75),
  each with its arc-length position along the whole tour: the cumulative `distance_m` of the
  preceding legs plus 0.25/0.5/0.75 of the leg's own distance.
- **Rule.** Take the candidate closest to half the tour's total distance. For a loop tour that is
  roughly the far end of the loop; for a traverse it is the middle.
- **Viewport clip.** If that candidate lies outside the current viewport bbox, take the in-bbox
  candidate closest to the tour's half-distance instead. With none in the bbox (the route merely
  crosses the view between candidates), the tour shows no board. It can still be reached from its
  route, its start point and the list.
- **Heading.** Travel direction at the anchor, from its neighbours in walking order: the previous
  candidate (or the leg's start waypoint) to the next candidate (or the leg's end waypoint).
  `west` if that runs westward, else `east`. This replaces `headingOf`.
- A tour whose legs lack anchors (a leg with `edgeId < 0`, drawn straight) falls back to the chord
  point at the same arc-length fraction.

The function is pure and memoised per tour key and bbox in `DiscoverLayer`. It runs only for
`routedTours` (tours already known to touch the viewport).

### 3. The board on a mast

The board no longer points at the ground; it stands on the route like a real waymark.

```
        ┌──────────────────────▶
        │ Kaunertal  42.3 km    ▶   ← board, arrow = travel direction
        └──────────────────────▶
        │
        │                            ← mast, 1.5 px, ~24 px tall
  ──────●───────────────────────     ← foot dot on the route (the anchor)
```

- **Foot.** A dot of about 5 px in ink at the anchor, which is the Leaflet `iconAnchor`. It is the
  only part that overlaps the route.
- **Mast.** Vertical, thin, fixed height.
- **Board.** Hangs at the top of the mast by its **tail end**, extending in the heading direction
  (east: to the right of the mast; west: to the left). The arrow tip is the board's leading end.
- **Why this clears the route.** When the route runs east–west at the anchor, the board sits a mast
  height above it. When the route runs north–south, the board extends sideways off the line. Only
  the diagonal cases clip the line a little, which is accepted in this stage.
- **Edge of the viewport.** If the board would leave the viewport horizontally, it flips to the
  other side of the mast. The arrow still points in the travel direction, so for a flipped board the
  mast attaches at the arrow end.
- **Hit area.** Board only; the mast and foot are `pointer-events: none`, so the route line under
  them stays hoverable and clickable.
- Stacks and spreads (§4) use the same mast; a spread fans the boards out at the top of one mast.

### 4. Grouping from `ROUTE_REVEAL_ZOOM` on

- **Below `ROUTE_REVEAL_ZOOM`:** unchanged. Count bubbles clustered by start point, click focuses
  and zooms in.
- **From `ROUTE_REVEAL_ZOOM` on:** the clusterer is fed **tour anchors** instead of start points
  (`createStartClusterer` is generalised to take points with a payload of tour keys). A second
  instance of it is built per anchor set.
  - One tour at a point: a single board on a mast.
  - Several tours whose anchors cluster together: one mast with a stack of boards and the count. It
    stands on the anchor of the best-ranked tour in the cluster, so the foot is always on a real
    route, never at a cluster centroid. It spreads on hover as today.
  - The two-arm cluster signpost stays for the bubble zoom levels only.
- Start points keep their waypoint symbol and its hover (all tours from that start) and click
  behaviour; nothing about them depends on boards any more.
- Focus, hover-to-highlight and click-to-pick on a board keep their current meaning. `focusTours`
  and `hoveredTourKeys` are unchanged.

### 5. Fading while the route is the subject

- While a tour is hovered from its **route line** or from the **results list**, its board drops to
  35 % opacity, so the highlighted geometry under and beside it reads clearly. Hovering the board
  itself keeps it opaque.
- Boards of tours outside `focusTours` fade as they do today.

## Layer routing

| Change | Layer |
|---|---|
| Anchor columns, tour anchors, quality check, payload doc | `pipeline/` + `docs/tour-suggestion-payload.md` |
| Decoding anchors | `huts/src/tourSearch/` loaders |
| `tourAnchor` choice | `huts/src/tourSearch/` (pure, no map types) |
| Mast rendering, grouping, fade | `huts/src/features/map/` |

## Running the pipeline

The change reruns `build_edge_payload`, `build_approach_table`, `match_tour_edges` (and what depends
on its outputs: `build_tour_edge_tiles` and the quality checks) and `copy_public_data`. None of the
multi-hour tasks (`hub_snap`, `build_base_graph`, ...) are affected, but no task runs without the
user's explicit go-ahead. The plan lists the exact tasks and asks before running them.

## Testing

- **Pipeline:** the arc-length helper on a straight line, on an L-shape (point on the corner) and on
  a polyline with zero-length segments. Offset quantisation round-trips within 1e-4°; overflow
  asserts. `test_dodo_wiring.py` covers the new `file_dep`s.
- **Client:** loaders decode anchors to the hut-relative absolute coordinates. `tourAnchor` swaps
  25/75 for reversed legs, picks the half-distance candidate, falls back inside the bbox, returns
  null with no candidate in view, and derives the heading from neighbours. The clusterer groups by
  anchor with the best-ranked foot.
- **Map:** the board attaches by its tail on the heading side, flips at the viewport edge, and mast
  and foot don't take pointer events.
