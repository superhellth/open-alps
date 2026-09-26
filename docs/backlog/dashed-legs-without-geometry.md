# Dashed legs without geometry on Discover route previews

## Symptom

On the Discover map (zoom >= 10) some tour previews contain dashed straight lines between two
huts/start points instead of the trail geometry.

## What draws a dashed line

`RouteLayer` draws a leg dashed when `useLegGeometries` returns `null` for it (`undefined` means still loading). That happens when:

1. ~~The geometry fetch is still in flight~~ — no longer drawn dashed; a loading leg is skipped.
2. `loadLegGeometry` rejected — the error is swallowed, so failures are invisible.
3. The leg has `edgeId < 0` and is never fetched (`tripToRoute` with an
   unresolved leg, or a payload without `edge_id`).
4. `legLayer` picks the wrong layer: it assumes the first/last leg is a `start_edges` edge.

## To investigate

- Reproduce: find a dashed leg, check the network tab for a failed/missing geometry range request.
- Count legs with `edgeId < 0` in `hut-edge-payload` / `approaches` output, and edges whose
  geometry point count is 0 or < 2 in `*-geometry.json`.
- If the data is at fault (missing geometry), fix it in `pipeline/`, not in the client.
- Log rejected geometry loads instead of swallowing them.
