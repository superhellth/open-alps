# Hut-availability-based routing — design

Date: 2026-09-01
Status: approved in brainstorming, ready for implementation planning
Scope: `huts/` app (new form fields, new `huts/src/availability/` client module, `tourSearch/`
engine changes) + a small additive `pipeline/` data-contract change (`fetch_huts.py`). Graduates
the "Hut-availability-based routing" item out of `docs/backlog.md`.

## Why

Today a user has to leave the app and check `hut-reservation.org`/the Bettencheck tool by hand to
know whether any hut on a candidate tour actually has free beds on their dates. `docs/alpenverein-api.md`
already documents the two OHRS endpoints this needs; nothing has used them from this app yet.

## Non-goals

- No booking/reservation flow — the app never writes to OHRS, only reads and links out
  (`hut-reservation.org/reservation/book-hut/...`, already documented).
- No rest days / per-leg custom dates — one leg is one night, full stop (see "Date model" below).
- No fix for the unrelated "hut ids are sequential, not stable" backlog item (positional `hut_id`
  index in the binary edge payload) — investigated during brainstorming, confirmed to be a
  separate, wider-blast-radius change (`binfmt.py`'s `u2` encoding, `build_edge_payload.py`,
  `GraphPage.tsx`) untouched by this design. `huts.geojson`'s `properties.id` GUID, which this
  design's new fields attach to, is already stable.

## 1. Pipeline change: ship `ohrsHutId`/`tenantCode`

`pipeline/phases/downloads/fetch_huts.py` already fetches `verein_nr` from the ArcGIS layer (used
internally for classification) but doesn't fetch `ohrs_hut_id`, and ships neither field in
`huts.geojson`. Add `ohrs_hut_id` to the ArcGIS `outFields` list, and add two properties to every
hut feature `split_features()` emits:

- `ohrsHutId: string | null` — `null` for direct-booking-only huts (per `docs/alpenverein-api.md`
  §1, this is expected and must be handled, not treated as a bug).
- `tenantCode: int` — copied from `verein_nr`, OHRS's required `tenantCode` param for the per-hut
  endpoint (§2b).

Purely additive to `huts.geojson`'s schema (new properties on an existing feature type) — no
existing consumer (`TourSearchPage.tsx`, `GraphPage.tsx`) breaks. `partner_betriebe.geojson` is
untouched — partner businesses aren't in OHRS at all.

`docs/alpenverein-api.md`'s status-vocabulary table already got a section added during
brainstorming for the `HUT_CLOSED_TO_PUBLIC` finding (§4 below) — no further doc changes needed
here.

## 2. Client availability module (`huts/src/availability/`)

New module, independent of `tourSearch/`, two entry points:

- `fetchAvailabilityByOffset(startDate: Date, numOfPeople: number, maxOffsetDays: number): Promise<Map<number, Set<string> | 'unknown'>>`
  — fires one `collectAll` POST per night-offset `1..maxOffsetDays` (date = `startDate + offset`
  days, formatted `DD.MM.YYYY`), **in parallel**. Returns a map from offset → the set of
  `ohrsHutId`s with free beds that night, or the literal `'unknown'` if that offset's request
  failed (§5). One call per offset, never per hut — matches the existing "never loop 2a/2b over
  huts" constraint (`docs/alpenverein-api.md`).
- `fetchHutDetail(ohrsHutId: string, tenantCode: number, date: Date, numOfPeople: number): Promise<HutDetail>`
  — wraps the 2b per-hut endpoint for one hut/night. Only called on-demand from the per-tour
  detail panel (§4), never from the bulk search path.

Both cache in-memory for the session, keyed by `(offsetDays, numOfPeople)` and
`(ohrsHutId, date, numOfPeople)` respectively, so re-submitting the same search or re-opening the
same detail panel doesn't refetch.

## 3. Search engine integration (`tourSearch/`)

**Date model:** one leg = one night. For a chain, the hut at `path[i]` (0-indexed, so
`path.length` after insertion) is the night-`path.length` stop — this falls directly out of how
`search.ts` already builds `path` (verified against the current implementation: the seed loop
sets `path: [h]`, i.e. `path.length === 1` on the first hut; each later hop appends one hut so
`path.length` at insertion time is exactly the night offset). No new bookkeeping needed — the
existing `path` gives us the offset for free.

`Query` gains one optional field:

```ts
availability?: {
  ohrsIdByHutIndex: Map<number, string | null>  // hutIndex -> ohrsHutId, from huts.geojson
  freeByOffset: Map<number, Set<string> | 'unknown'>  // from fetchAvailabilityByOffset
}
```

When `query.availability` is absent, behavior is byte-for-byte identical to today — this is an
opt-in constraint, not a new required one (per the "optional start date" decision below).

New check, structurally identical in shape to the existing `allowedHutIndices` check (hut-identity
based, not leg-property based, so it doesn't go through `legPasses`) — added at both points in
`searchChains` where a hut is about to be added to a state's `path`:

```ts
function hutAvailable(h: number, offsetDays: number, availability: Query['availability']): boolean {
  if (!availability) return true
  const ohrsId = availability.ohrsIdByHutIndex.get(h)
  if (ohrsId == null) return true // no OHRS id (direct-booking-only) or huts.geojson lacked it: pass/unknown
  const free = availability.freeByOffset.get(offsetDays)
  if (free === 'unknown' || free === undefined) return true // fetch failed for this night: pass/unknown
  return free.has(ohrsId)
}
```

- Seed loop (`for (const approachLeg of getApproachLegs(h, ...))`): after the existing
  `allowedHutIndices` check, `if (!hutAvailable(h, 1, availability)) { killCounters.availability++; continue }`.
- Expansion loop (`for (const leg of legs)`, building `h2`): after the existing
  `allowedHutIndices`/revisit checks, `if (!hutAvailable(h2, s.path.length + 1, availability)) { killCounters.availability++; continue }`.
- `collectFinished`'s exit-leg loop: **no check** — the exit leg goes to a parking lot/station/
  village point, not a hut; there's no night there.

New `killCounters.availability` counter, alongside the existing `hutFiltered`/`revisit`/etc.

This is pruning during search (per the brainstorming decision), not a post-filter — infeasible
chains never get expanded further, so the existing dominance-pruning-by-visited-set machinery
(`search.ts`'s per-layer `Map<hutIndex, Map<"startId|visitedKey", State>>`) needs no changes: the
new check sits at the same "evaluate the next hut/leg against current state" chokepoint the other
filters already use, before a `State` is ever constructed for a rejected candidate.

**Badges-only mode** (checkbox off, per §4): don't pass `query.availability` to `findTours` at all
— run the unconstrained search, and let the UI (§4) independently look up
`freeByOffset.get(path.length).has(ohrsId)` per hut in each *already-found* chain to render badges,
using the same `fetchAvailabilityByOffset` result. Both modes share one fetch; only whether it's
threaded into `Query` differs.

## 4. UI

- **Form fields** (`formState.ts`/`TourSearchPage.tsx`): optional start date (native date input)
  and party size (number, default 1, only shown/used once a date is picked). Party size feeds
  `numOfPeople` in both `fetchAvailabilityByOffset` and `fetchHutDetail`.
- **New checkbox**, "nur Touren mit Verfügbarkeit" (default off), enabled only once a date is
  picked. Controls whether `Query.availability` is set (filtering) or the search runs unconstrained
  and availability is shown as badges only (§3).
- On submit, if a date is picked: call `fetchAvailabilityByOffset(startDate, numOfPeople, legCountMax)`
  before (or concurrently with, then awaited before) calling `findTours`, since the engine needs
  the result synchronously as part of `Query`.
- **`TourList.tsx`**: each hut in a displayed chain gets a small badge from four states — frei /
  ausgebucht-oder-geschlossen / Direktbuchung (no `ohrsHutId`) / unbekannt (offset fetch failed).
  The coarse `collectAll` data can't distinguish "full" from "closed for season" (§ pipeline docs
  update) — that distinction only shows up once a user opens the detail panel below.
- **New per-tour detail panel** (expand one result): calls `fetchHutDetail` once per hut in that
  one chain (small, user-triggered count — never looped over the whole result list). Shows bed
  category counts per night, and for a night with no availability, the precise reason if OHRS gave
  one (`HUT_CLOSED_TO_PUBLIC` → "Hütte geschlossen (Saison)" vs `RESERVATION_NOT_POSSIBLE` →
  "ausgebucht"), plus the `hut-reservation.org` deep link for that hut/date.

## 5. Error handling

A failed `collectAll` call for one offset (network error, non-2xx, malformed body) marks that
offset `'unknown'` in the map rather than throwing — `hutAvailable()` treats `'unknown'` as a pass,
so one bad night degrades to badges-only for that night rather than breaking the whole search.
`fetchHutDetail` failures in the detail panel fall back to the existing `TECHNICAL_ERROR` display
already documented in `docs/alpenverein-api.md`.

## Testing plan

- Pipeline: extend `pipeline/tests/test_fetch_huts.py` to assert `ohrsHutId`/`tenantCode` appear
  on hut features (including the `null` case for a direct-booking-only fixture) and are absent
  from `partner_betriebe.geojson` features.
- `huts/src/availability/`: unit tests against mocked `fetch` — one offset succeeds/fails
  independently, in-memory cache hit avoids a second call for a repeated `(offset, numOfPeople)`.
- `tourSearch/search.test.ts`: extend with synthetic-graph cases — a chain through a hut with no
  free beds on its night is rejected when `query.availability` is set and accepted when absent;
  a hut with `ohrsHutId: null` always passes; an `'unknown'` offset always passes;
  `killCounters.availability` increments on rejection.
- Manual smoke test (per root `CLAUDE.md`, no dev-server verification unless asked — covered by
  the automated tests above; UI verification only if explicitly requested later).
