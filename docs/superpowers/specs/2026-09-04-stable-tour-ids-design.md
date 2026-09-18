# Stable hut/leg references for persistence

## Problem

`docs/backlog.md`'s "Stable hut ids" entry: `hutIndex`/`edgeId`, as used throughout
`huts/src/tourSearch/`, are array positions in the emitted payloads (`hut-edge-payload.bin`'s
`from_id`/`to_id` narrow into `hut_ids`; `approaches.bin`'s rows and `hut-edge-payload.bin`'s rows
are both plain `enumerate()` position), not stable identities. A pipeline rerun that reorders
`huts.geojson`'s feature order, or `hut_edges`/`start_edges`' row order, silently remaps every
position to a different hut or leg. This blocks trip persistence in the Trip Planner Reenvision
design (`docs/superpowers/specs/2026-09-04-trip-planner-reenvision-design.md`): a saved trip in
`localStorage` referencing huts/edges by position would, after a rerun, render as a *different but
plausible-looking* trip with nothing visibly broken.

## Non-goal

This is not a pipeline change. `hutIndex`/`edgeId` keep meaning exactly what they mean today —
session-local positions into the currently-loaded payload, needed for the u2-narrowed columns and
for indexing into `hut-edges.pmtiles`/`hut-edge-geometry.bin`/elevation binaries, all of which are
themselves built in the same row order and only ever read within one loaded session. The actual
defect is narrower: nothing today turns a position into something worth writing to `localStorage`,
and nothing turns such a value back into a position against whatever data happens to be loaded
later. Every field needed to build a real stable identity already ships in the payload:

- `graphData.hutEdges.hutIds[hutIndex]` is the AV's own ArcGIS `OBJECTID`
  (`pipeline/phases/downloads/fetch_huts.py`), not a pipeline invention.
- A hut-hut edge is already unique per `(fromIndex, toIndex, variant)` — one row per unordered pair
  per variant (`docs/tour-suggestion-payload.md` §3).
- An approach/exit edge is already unique per `(hutIndex, startId, sourceType, variant)` — `startId`
  is itself a real OSM node id or ArcGIS `OBJECTID` (§6), not a pipeline invention either.

So no new identity needs to be assigned or persisted pipeline-side; the fix is a small resolution
layer client-side.

## Design

New module `huts/src/tourSearch/stableId.ts`.

**Derive** (pure, no lookup beyond the `hutIds` array already on `GraphData`):

```ts
hutStableId(graphData: GraphData, hutIndex: number): string
// "hut:<realId>"

hutEdgeStableId(graphData: GraphData, leg: { fromIndex: number; toIndex: number; variant: number }): string
// "edge:<min(realFrom,realTo)>:<max(realFrom,realTo)>:<variant>"
// sorted so the same undirected edge produces one key regardless of which direction it was walked
// (mirrors §3: the graph itself is undirected, direction is a client-side synthesis)

approachStableId(graphData: GraphData, leg: { hutIndex: number; startId: number; sourceType: SourceType; variant: number }): string
// "approach:<realHutId>:<startId>:<sourceType>:<variant>"
```

These take the leg shapes already in `types.ts` (`HutLeg` has `fromIndex`/`toIndex`/`variant`
directly; `StartLeg` has `hutIndex`/`startId`/`sourceType`/`variant` directly) — no extra lookup by
`edgeId` needed to derive a key from a leg the client already has in hand.

**Resolve** (stable key → current session's position, against whichever `GraphData` is loaded):

```ts
resolveHut(graphData: GraphData, key: string): number | null           // -> hutIndex
resolveHutEdge(graphData: GraphData, key: string): HutEdgeRecord | null
resolveApproachLeg(graphData: GraphData, key: string): ApproachRecord | null
```

Each builds a `Map<string, ...>` from the corresponding array on first call and caches it in a
module-level `WeakMap<GraphData, {...}>` keyed by the `GraphData` instance, so a saved trip
resolving many legs at once doesn't rescan `hutEdges.records`/`approaches.records` per leg, and
`GraphData` itself gains no new fields.

**Failure mode.** A key that doesn't resolve (hut/edge removed by a later pipeline run) returns
`null`. No fuzzy fallback, no nearest-match — this is exact resolution succeeding or failing, not
the client-side staleness heuristic the backlog entry explicitly rules out. Callers (Trip Planner,
once built) decide how to surface a `null` leg; that UI is out of scope here.

## Testing

`stableId.test.ts`, same style as the rest of `tourSearch/`:

- Key derivation is stable and round-trips through `resolve*`.
- `hutEdgeStableId` produces the same key for a leg and its reverse (sorted-pair ordering).
- `resolve*` against a synthetic `GraphData` (same fixture style as `search.test.ts`).
- A key referencing a hut/edge absent from the given `GraphData` resolves to `null`.
- Two calls to `resolve*` against the same `GraphData` instance reuse the cached map (assert via a
  spy on the array access, or just that behavior is correct — no need to assert caching
  mechanically if it complicates the test).

## Docs

- Add a short "Stable references for persistence" section to `docs/tour-suggestion-payload.md`
  pointing at `stableId.ts` as the sanctioned contract, so a future Trip Planner implementer finds
  it instead of reinventing something.
- Remove the "Stable hut ids" entry from `docs/backlog.md` once this lands (per `CLAUDE.md`'s
  backlog convention).
