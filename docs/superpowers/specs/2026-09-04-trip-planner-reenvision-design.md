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
  existing fully-static architecture. A trip leaves the browser via a URL-encoded share link and
  export, not sync (see "Getting the trip out of the browser").
- Pipeline/data-quality changes — any data-quality UI need is a backlog note, not designed here.

## Journey

- **Discover**: explore the map, filtered by rough constraints (region, days, difficulty, start
  point, mode) plus the active trip's dates and party size. Candidate routes (from the existing
  `tourSearch/` engine) and official tours render as hoverable/selectable overlays directly on the
  map, ranked in a compact list alongside.
- **Build**: picking a result adds it to the active trip's itinerary panel — editable, reorderable,
  leg by leg.
- **Save**: the active trip autosaves to `localStorage` as one entry in a list of saved trips;
  users can start a new trip, switch between saved ones, rename, delete. Autosave means there is no
  explicit save action and no unsaved-changes state — but deleting a trip on `#trips` is therefore
  destructive and needs an undo affordance.
- **Book**: each hut in the itinerary panel shows live per-leg availability for the trip's dates,
  and deep-links to its real booking page (or shows direct-contact info for direct-booking-only
  huts).
- **Take along**: the finished itinerary can leave the browser it was planned in — see
  "Getting the trip out of the browser".

Official tours fold into Discover as one more thing you can find and add to a trip — not a
separate "view mode" toggle like today's `viewMode: 'search' | 'official'`.

**Copy language**: user-facing text stays German throughout, as the app is today ("Tourensuche",
"Selbstversorgerhütten"). Screen and component names in this spec ("Planner", "Trips") are code
identifiers, not UI labels; the nav renders their German equivalents.

## Screens

Two customer-facing screens (down from today's single mega-page):

- **Planner (default route, no hash).** The main screen. Full-height map is the dominant surface. A
  floating filter bar sits over the map, top-left (region/days/difficulty/start-point/mode) —
  collapsed by default, not a big static form. Once the active trip has legs, a docked itinerary
  panel sits on the right and grows as more are added.
- **`#trips` — Trip list.** A separate route (not a drawer) listing saved trips: switch the active
  trip, rename, delete. Kept as its own screen for a more conventional, discoverable multi-page
  structure per user preference.

Routes are hashes, not paths — `main.tsx` is the existing hash-based router with no library, and
this spec does not change that.

**Empty state**: on a first visit the active trip has no legs, so the right-docked panel would
otherwise spend the most valuable screen real estate on nothing. The panel is absent until the trip
has its first leg; before that the Planner is map + filter bar only, and the panel slides in on the
first "Add to trip".

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
  startDate: string | null   // ISO date of the first night
  partySize: number          // people, 1-9 (OHRS bound)
  startPoint: StartPoint | null
  legs: Leg[]   // the chain leg shape from tourSearch/types.ts (HutLeg | StartLeg), which
                // carries hut identity and durations — not tourSearchPage/types.ts's RouteLeg,
                // which is map geometry only
  notes?: string
}
```

- `startDate` and `partySize` are trip fields, not search-form fields. For this customer the dates
  *are* the trip: they decide which huts are bookable, and party size decides it just as hard
  ("2 beds free" vs "4 beds free" is the difference between a trip existing and not). They are set
  in the itinerary panel and are the single source feeding both the availability search filter and
  the per-leg availability badges — today's `form.startDate`/`form.numOfPeople`
  (`TourSearchPage.tsx`) move here.
- Stored in `localStorage` as a list of trips — no backend, no accounts.
- Exactly one trip is "active" at a time on the Planner; `#trips` switches which trip is active.
- Adding a search result or official tour to the active trip appends its legs. Results that don't
  chain onto the current end are **not** offered with a modal choice — a dialog asking
  "append or replace?" puts a decision the user can't evaluate on a common path. Instead, once a
  trip has legs, the results list marks which candidates continue from the current end, and
  replacing an itinerary is an explicit action in the itinerary panel.
- The itinerary panel supports removing and reordering legs directly, independent of a new search.
- This reuses the existing `Route`/leg types and the `tourSearch/` search engine's routing logic —
  the new thing is the persistent wrapper around a selected route.

### Prerequisite: stable ids (pipeline layer)

A saved trip references huts and edges by `hutIndex`/`edgeId`, both of which are **positions in the
payload arrays**, not stable identities — `hutIds` is indexed by array order
(`TourSearchPage.tsx`), and `edgeId` indexes the geometry payload the same way. A pipeline rerun
that reorders either one turns every saved trip into a *different but plausible-looking* trip, with
nothing visibly broken.

This is a data-contract problem, and per this repo's root-layer rule it is fixed in the pipeline —
emitting ids that are stable across runs — not worked around in the client with denormalized copies
or staleness heuristics. It is tracked as **"Stable hut ids"** in `docs/backlog.md` and is a
prerequisite for shipping trip persistence. No UI mitigation is designed here.

## Discovery: map, filters, results

- **Filter bar**: floating pill over the map, expands to reveal controls for day-count range,
  per-day walking-time range, difficulty/SAC grade, region, start point, and mode
  (`car` round-trip / `transit` open route / `village` start in a Bergsteigerdorf).
- **Region and start-point filtering are new engine capability, not just new UI.** `Query`
  (`tourSearch/types.ts`) has no geography and no start point — `search.ts` enumerates every start
  point in the graph and has no way to restrict results to an area. Region filtering is the single
  most important control for the "where should I go?" half of the job, so it is in scope, and
  `Query`, `search.ts` and `formState.ts` are **extended**, not reused unchanged. Everything else
  in the filter bar does reuse `formState.ts`'s query-building as-is.
- **The filter bar must not silently drop today's controls.** Beyond the ones listed above, the
  current form carries a per-leg ascent cap, a max-elevation cap, hut-operator selection
  (AV / sonstige) and serviced-vs-self-service. Self-service is trip-defining, not an advanced
  detail — self-catering huts often need a key arranged in advance — so it belongs in the primary
  expanded filter bar alongside difficulty; the two numeric caps stay behind an "advanced"
  disclosure as they are today.
- **Results on the map**: candidate routes (`findTours`) and matching official tours draw as
  distinct, hoverable polylines directly on the map, building on the hover-leg interaction already
  shipped (`feat(ui): make tour-legs hoverable`). A compact ranked list sits alongside the filter
  bar; clicking a list item highlights its line on the map (today's interaction is
  effectively map → list only; this adds list → map).
- **Only a bounded set of routes is drawn at once.** `findTours` returns an uncapped result set, and
  leg geometry is fetched lazily per edge over HTTP range requests (`loadLegGeometry.ts`), so
  "draw every candidate" would mean hundreds of requests and unreadable line spaghetti over the
  Alps. Only the currently visible page of ranked results draws, plus the hovered/selected route
  emphasized on top.
- **Adding to trip**: each result carries an explicit "Add to trip" action.

## Booking hand-off

- Each hut in the itinerary panel shows live availability (existing
  `availability/fetchAvailability.ts`) for the trip's `startDate`/`partySize`.
- Huts with an `ohrs_hut_id` (existing field, already joined via `hutClass.ts`/availability code)
  get a "Book on alpenverein.at" deep link (existing `availability/bookingLink.ts`).
  Direct-booking-only huts (`ohrs_hut_id === null`) show their existing contact info instead. This
  distinction already exists in the data/logic layer — the change is surfacing it per-leg in the
  itinerary panel instead of only in a detail popup.

### Availability stays a search filter, and gains a trip-level answer

Today `onlyAvailable` prunes chains where *every* hut has beds on the right night
(`formState.ts` → `Query.availability`) — the strongest thing the app currently does, because the
hardest part of hut-tour planning is not finding a nice route, it is finding consecutive nights that
are all actually free. Moving availability to post-hoc per-leg badges would replace that with
"build a four-day trip, then discover night three is full, then start over."

So availability is **both**:

- a Discover-time filter, as today, driven by the active trip's `startDate`/`partySize`; and
- a per-leg badge in the itinerary panel, for a trip already built.

The itinerary panel additionally answers the question at trip level: which start dates make the
whole chain bookable, so a user whose Friday start is blocked at hut three is told the trip works
starting Thursday or Saturday, rather than being left to re-derive it hut by hut. Sliding the whole
trip by a day is one action.

Note that availability is only ever partially knowable: huts without an `ohrs_hut_id` are
direct-booking-only and report nothing, so "unknown" is a distinct state from "full" everywhere
availability is shown or filtered on.

## Getting the trip out of the browser

`localStorage` plus a desktop-only design means the itinerary lives in exactly one browser profile
on one machine — while the trip itself happens on a phone, in the mountains, days later. Accounts
and sync stay out of scope, but the trip must have a way out of the browser, or "Save" saves it
somewhere the user can never be while doing the trip. At least one of:

- a **share/restore link** encoding the trip in the URL (no backend needed, and doubles as the
  way to send an itinerary to the people coming along);
- **GPX export** of the itinerary, for the phone's map app;
- a **print view** of the itinerary — huts, nights, walking times, contact/booking info.

The share link is the primary one; the others are cheap follow-ons.

## Visual design language (validated via visual companion)

**"Topo Charcoal"**: dark neutral charcoal/topo-map-gray base, off-white/cream text and surfaces,
a high-contrast red/orange accent reserved for primary actions (Add to trip, Book, active/selected
states). Map styling should echo topographic-map conventions (contour-like line weight, muted
terrain colors) rather than a generic default basemap tone. MUI remains the component library, but
`theme.ts` is rewritten with a custom palette/typography instead of `ThemeProvider`'s defaults.

## What's kept vs. rebuilt

**Kept as-is:**
- `tourSearch/` engine internals (`diversity.ts`, `adjacency.ts`, `legFilters.ts`,
  `dinDuration.ts`, `overlap.ts`, `resolveVariant.ts`, `reverseLeg.ts`, loaders)
- `availability/fetchAvailability.ts`, `availability/bookingLink.ts`
- `hutClass.ts`
- Pipeline outputs/contracts and the pipeline itself, with one prerequisite: stable hut/edge ids
  (see "Prerequisite: stable ids")
- `#admin` page (`AdminPage.tsx` and its supporting components), untouched

**Extended (not reused unchanged):**
- `Query` (`tourSearch/types.ts`) + `search.ts` → gain region and start-point constraints
- `formState.ts` → builds those constraints; `startDate`/`numOfPeople` move out of form state onto
  the active `Trip`

**Rebuilt:**
- `TourSearchPage.tsx` → becomes the new Planner screen composition
- `ResultsMap.tsx` → becomes the map-first surface rendering both search-result overlays and the
  active trip's itinerary
- `TourList.tsx` / `OfficialTourList.tsx` → become the compact results list feeding "Add to trip"
  (sort/rank logic carries over)
- `theme.ts` → Topo Charcoal palette
- `AppShell.tsx` nav → Planner / Trips tabs

**New:**
- `Trip` type (incl. `startDate`/`partySize`) + `localStorage` persistence module
- `#trips` route and screen
- Itinerary panel component (right-docked, on the Planner screen), incl. trip-level date/party
  controls and the whole-trip availability answer
- Floating filter-bar component
- Trip share link (URL-encoded trip), plus GPX/print export as follow-ons

## Non-goals

- No accounts/backend — trips are client-side/`localStorage` only, taken out of the browser via
  share link/export rather than sync.
- No in-app booking transactions.
- No mobile-first design pass this round. (The share link is what bridges to the phone; a mobile
  layout pass is a later round.)
- No changes to `#admin`.
- No pipeline changes in this spec — but stable hut/edge ids are a pipeline-layer prerequisite for
  trip persistence, tracked in `docs/backlog.md`.
- No UI for data-quality signals (tracked as a pipeline-layer backlog note, not this spec).
