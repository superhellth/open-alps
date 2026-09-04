# Trip Planner Reenvision — Frontend Design

## Problem

The current `TourSearchPage.tsx` is a search tool: a filter form produces a list of candidate
routes on a map. It doesn't help a user go from "where should I go?" to "I have a booked, saved
trip." Four specific gaps drove this redesign:

1. **Clunky search-first flow.** Form → list → map is a rigid sequence that doesn't match how
   people actually explore trip ideas (fuzzy region/day constraints, want to browse before
   committing).
2. **No planning object.** A selected route is ephemeral — closing the tab loses it. There's no
   way to build up a multi-day trip incrementally, save it, or come back to it.
3. **No path to booking.** Availability is a filter/badge on results, not something tied to a
   concrete itinerary a user can act on.
4. **Dated, generic visual design.** Default MUI blue theme, no distinct visual identity.

Data trust/confidence in results was also raised, but on inspection that's a pipeline-layer
concern (per this repo's rule that data-quality problems are fixed at their root layer, not
papered over in the UI) — it is *not* part of this design. It's logged as a derived need against
`docs/backlog.md` instead: the UI may eventually want to surface data-quality signals once the
pipeline's data-quality-monitoring work produces them, but no such UI is designed here.

## Customer & job-to-be-done

Primary customer: **solo/small-group hikers planning a multi-day Alpine-Club-hut tour.** The job:
go from a rough idea ("somewhere in the Kaiser, ~4 days, moderate difficulty") to a concrete,
saved, bookable itinerary.

## Scope

One coherent journey — **Discover → Build → Save → Book** — designed as a single spec, not
decomposed into independent subsystems, because discovery, itinerary-building, persistence and
booking hand-off are tightly coupled parts of one flow.

**Explicitly out of scope:**
- The internal `#admin` routing-graph debug view — stays untouched, unlinked from customer nav.
- In-app booking transactions — the app deep-links to the hut's real booking system (OHRS /
  alpenverein.at) or shows direct-contact info; it never handles payment/confirmation itself.
- Mobile-first redesign — desktop is the design target this round; the layout should remain
  responsive-safe but mobile gets no dedicated design pass.
- Accounts/backend — trips are client-side only (`localStorage`), consistent with the app's
  existing fully-static architecture.
- Pipeline/data-quality changes — any data-quality UI need is a backlog note, not designed here.

## Journey

- **Discover**: explore the map, filtered by rough constraints (region, days, difficulty, start
  point, mode). Candidate routes (from the existing `tourSearch/` engine) and official tours
  render as hoverable/selectable overlays directly on the map, ranked in a compact list alongside.
- **Build**: picking a result adds it to the active trip's itinerary panel — editable, reorderable,
  leg by leg.
- **Save**: the active trip persists to `localStorage` as one entry in a list of saved trips;
  users can start a new trip, switch between saved ones, rename, delete.
- **Book**: each hut in the itinerary panel shows live per-leg availability once trip dates are
  set, and deep-links to its real booking page (or shows direct-contact info for
  direct-booking-only huts).

Official tours fold into Discover as one more thing you can find and add to a trip — not a
separate "view mode" toggle like today's `viewMode: 'search' | 'official'`.

## Screens

Two customer-facing screens (down from today's single mega-page):

- **`/` — Planner.** The main screen. Full-height map is the dominant surface. A floating filter
  bar sits over the map, top-left (region/days/difficulty/start-point/mode) — collapsed by
  default, not a big static form. A docked itinerary panel sits on the right, always showing the
  active trip, and grows as legs are added.
- **`/trips` — Trip list.** A separate route (not a drawer) listing saved trips: switch the active
  trip, rename, delete. Kept as its own screen for a more conventional, discoverable multi-page
  structure per user preference.

`#admin` is unaffected and unlinked from the new nav (`AppShell.tsx`'s tabs become
Planner / Trips).

## Layout (validated via visual companion)

Planner screen: map fills the viewport; filter bar floats top-left as a small pill/overlay over
the map; itinerary panel is docked on the right as a fixed-width column (not a bottom sheet or
left rail — validated against three options, right-docked chosen for keeping filters and the trip
panel visually separate rather than stacked on the same edge).

## Trip data model & persistence

```
Trip {
  id: string
  name: string
  createdAt: string
  updatedAt: string
  startPoint: StartPoint | null
  legs: Leg[]   // reuses the existing chain/Route leg shape from tourSearchPage/types.ts
  notes?: string
}
```

- Stored in `localStorage` as a list of trips — no backend, no accounts.
- Exactly one trip is "active" at a time on the Planner; `/trips` switches which trip is active.
- Adding a search result or official tour to the active trip appends its legs (or replaces, if the
  new route doesn't chain onto the existing legs — user is prompted to choose).
- The itinerary panel supports removing and reordering legs directly, independent of a new search.
- This reuses the existing `Route`/leg types and the entire `tourSearch/` search engine unchanged —
  the new thing is the persistent wrapper around a selected route, not the routing logic.

## Discovery: map, filters, results

- **Filter bar**: floating pill over the map, expands to reveal controls for day-count range,
  difficulty/SAC grade, region (map-bounds-based or named-region picker), start point
  (station/parking/coordinate), and mode (hiking/via ferrata). Reuses `formState.ts`'s
  `Query`-building logic as-is; only the surrounding UI is new.
- **Results on the map**: candidate routes (`findTours`) and matching official tours draw as
  distinct, hoverable polylines directly on the map, building on the hover-leg interaction already
  shipped (`feat(ui): make tour-legs hoverable`). A compact ranked list sits alongside the filter
  bar; clicking a list item highlights its line on the map (today's interaction is
  effectively map → list only; this adds list → map).
- **Adding to trip**: each result carries an explicit "Add to trip" action.

## Booking hand-off

- Each hut in the itinerary panel shows live availability (existing
  `availability/fetchAvailability.ts`) once the trip has dates.
- Huts with an `ohrs_hut_id` (existing field, already joined via `hutClass.ts`/availability code)
  get a "Book on alpenverein.at" deep link. Direct-booking-only huts (`ohrs_hut_id === null`) show
  their existing contact info instead. This distinction already exists in the data/logic layer —
  the change is surfacing it per-leg in the itinerary panel instead of only in a detail popup.

## Visual design language (validated via visual companion)

**"Topo Charcoal"**: dark neutral charcoal/topo-map-gray base, off-white/cream text and surfaces,
a high-contrast red/orange accent reserved for primary actions (Add to trip, Book, active/selected
states). Map styling should echo topographic-map conventions (contour-like line weight, muted
terrain colors) rather than a generic default basemap tone. MUI remains the component library, but
`theme.ts` is rewritten with a custom palette/typography instead of `ThemeProvider`'s defaults.

## What's kept vs. rebuilt

**Kept as-is:**
- `tourSearch/` engine (`search.ts`, `diversity.ts`, `adjacency.ts`, `legFilters.ts`,
  `dinDuration.ts`, `overlap.ts`, `resolveVariant.ts`, `reverseLeg.ts`, loaders)
- `formState.ts`'s query-building logic
- `availability/fetchAvailability.ts`
- `hutClass.ts`
- All pipeline outputs/contracts and the pipeline itself
- `#admin` page (`AdminPage.tsx` and its supporting components), untouched

**Rebuilt:**
- `TourSearchPage.tsx` → becomes the new Planner screen composition
- `ResultsMap.tsx` → becomes the map-first surface rendering both search-result overlays and the
  active trip's itinerary
- `TourList.tsx` / `OfficialTourList.tsx` → become the compact results list feeding "Add to trip"
  (sort/rank logic carries over)
- `theme.ts` → Topo Charcoal palette
- `AppShell.tsx` nav → Planner / Trips tabs

**New:**
- `Trip` type + `localStorage` persistence module
- `/trips` route and screen
- Itinerary panel component (right-docked, on the Planner screen)
- Floating filter-bar component

## Non-goals

- No accounts/backend — trips are client-side/`localStorage` only.
- No in-app booking transactions.
- No mobile-first design pass this round.
- No changes to `#admin` or the pipeline.
- No UI for data-quality signals (tracked as a pipeline-layer backlog note, not this spec).
