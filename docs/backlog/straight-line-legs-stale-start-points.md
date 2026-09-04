# Search-result tour legs render as straight lines (stale `stations.geojson`/`parking.geojson`)

**Priority:** Medium

All legs of a selected search-result chain render as the straight-line fallback (dashed, "Schematische
Verbindung, nicht der reale Wegverlauf") in `ResultsMap.tsx`, even though real trail geometry exists
for every leg. Official tours are unaffected.

## Root cause (data layer)

`huts/public/data/stations.geojson`/`parking.geojson` were last regenerated **18:56–18:57**, while
`approaches.bin`/`hut-edge-payload.bin` (the routing graph's approach table) were regenerated
**21:01** — from a *different, newer* pipeline run. Sampling `approaches.bin`'s `start_id` column,
roughly a third of the ids it references don't exist in the older `stations.geojson`/`parking.geojson`
at all (verified: e.g. `92831950`, `1137665678`, `787049888` are absent from both files, while other
sampled ids resolve fine). `huts.geojson` (18:55) happens to still be compatible since hut identities
didn't change in the newer run — only the start-point extraction did.

**Fix:** ensure `stations.geojson`/`parking.geojson` are regenerated and re-copied
(`copy_public_data`) in the same pipeline run as `approaches.bin`/`hut-edge-payload.bin`, not left
stale from a partial/targeted `doit` invocation.

## Contributing robustness gap (frontend layer)

`chainToRoute` (`huts/src/tourSearchPage/helpers.ts:127-146`) builds `waypoints` *conditionally* —
only pushing the start/end point if `startById.get(chain.startId / .exitStartId)` resolves — but maps
every leg from `chain.legs` **unconditionally**. When a lookup misses, `waypoints.length` no longer
equals `legs.length + 1`. `ResultsMap.tsx:45`'s guard on that invariant then disables geometry
fetching for the **whole route**, not just the affected leg, so every leg of that chain falls back to
a straight line — a total, silent degradation instead of a visible error for the one bad endpoint.

`officialTourToRoute` (`helpers.ts:157-175`) doesn't have this gap: it builds waypoints/legs in
lockstep and returns `null` (excluding the tour) if an endpoint fails to resolve, which is why official
tours never show this symptom even when the same underlying id-space mismatch would apply to them.

**Fix:** make `chainToRoute` return `null` on a failed `startById` lookup, mirroring
`officialTourToRoute`, so a missing endpoint fails visibly (chain not shown) rather than silently
corrupting every leg's fallback rendering.
