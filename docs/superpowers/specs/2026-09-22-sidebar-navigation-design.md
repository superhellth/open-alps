# Sidebar navigation: drop the app bar, fold "Meine Touren" into the planner

## Problem

The planner is map-first, but a 64px `AppBar` (`AppShell.tsx`) spans the top of the page holding only
the "Hüttentouren" title and two destinations (Planen / Meine Touren). It is ~90% empty and costs map
height. "Meine Touren" is a separate full page (`TripsPage.tsx`) without a map, although opening a
trip from it just jumps back into the planner's trip mode — it is really a step in front of trip mode,
not a separate place.

## Goals

- The map fills the full viewport height; no app bar on the planner.
- Brand and top-level navigation live in the sidebar's top row.
- "Meine Touren" becomes a sidebar view next to the map, with saved trips drawn on the map.
- Booking status and notes are edited in the trip panel, where the trip is visible on the map.

Non-goals: mobile layout, changes to trip persistence or the share-link format, pipeline changes
(this is a `huts/`-only change).

## Layout and navigation

- `AppShell` is removed. The planner is a full-height row: 420px sidebar left, map right.
- **Sidebar top row** (~48px, fixed; view content below scrolls):
  - left: "Hüttentouren" wordmark; clicking it closes any open trip and shows the Discover view (`#`; filters and results are kept);
  - right: two-part signpost switch **Planen ▸ | Meine Touren (n) ▸** (the fingerpost styling of the
    `SignpostNav` WIP), `n` = number of saved trips.
- **Sidebar views**, one at a time:
  - `discover` — Filter/Ergebnisse tabs, unchanged;
  - `saved` — the saved-trips list (below);
  - `trip` — `TripPanel`, unchanged apart from the additions below.
  The signpost marks "Planen" active for `discover` and `trip`, "Meine Touren" for `saved`.
- **URL:** `#trips` selects the `saved` view (back button and existing links keep working).
  `#trip=<payload>` (share import) and `#admin` are unchanged.
- **Trip panel back button** returns to where the trip was opened from: "← Ergebnisse" (opened from
  results) or "← Meine Touren" (opened from the list, back navigates to `#trips`).
- The discover view stays mounted (hidden) while `saved` or `trip` is shown, so filters, results and
  scroll position survive switching.

## "Meine Touren" view

- **Header:** "Meine Touren" + a ⋮ menu with *Exportieren (Datei)* and *Importieren*. An invalid
  import file shows an error `Alert` below the header.
- **Rows**, newest `updatedAt` first:
  - name;
  - summary line `4 Nächte · ab 12.07.2026 · 2 Pers. · 2/4 bestätigt` (`ohne Datum` without a start
    date);
  - ⋮ menu: *Umbenennen* (inline name field) and *Löschen* (snackbar with *Rückgängig*).
  - Clicking a row opens the trip in `trip` view and fits the map to it.
- **Unsaved draft:** if a draft exists, a pinned first row "Entwurf · nicht gespeichert" opens it.
- **Unresolvable trip** (`legsFromTrip` flags a night as changed since saved): the row shows a small
  "geändert" marker and has no map line; it can still be opened.
- **Empty state:** "Noch keine Touren gespeichert." with a "Tour planen" link switching to Planen.

## Map in the `saved` view

- Discover result markers are hidden; every resolvable saved trip is drawn as a thin muted route.
- Hovering a row highlights its route (thick, full color); hovering a route highlights its row.
- Clicking a route opens that trip.
- Entering the view fits the map to all saved trips; with none, the map keeps its viewport.
- Routes come from `tripToRoute` and the existing `loadLegGeometry`; a leg is drawn as a dashed
  straight segment until its geometry loads, or if the fetch fails.

## Switching views with an open trip

- Clicking "Meine Touren" in `trip` view closes the trip (`closeActive`). A draft stays in state and
  appears as the pinned draft row, so no discard dialog is needed.
- Opening a saved trip while a changed draft exists leaves the draft pinned. Only picking a new result
  tour still triggers `DiscardDraftDialog`, as today.

## Trip panel additions

- Each night row gets the offen / angefragt / bestätigt toggle (`Trip.nights[i].status`).
- A notes field (`Trip.notes`) at the bottom, above Share.
- Both go through the existing `onChange`, so they work for drafts and saved trips alike and survive
  saving a draft.

## Components

| File | Change |
|---|---|
| `plannerPage/SidebarHeader.tsx` | new: wordmark + `SignpostNav`; props: active view, saved count. `activeTabIndex` moves here from `AppShell.tsx`. |
| `plannerPage/SavedTripsList.tsx` | new: list, row menu, pinned draft row, header ⋮ export/import, empty state. Logic moves over from `TripsPage.tsx`; hover/open are callbacks to `PlannerPage`. |
| `plannerPage/map/SavedTripsLayer.tsx` | new: muted routes for all saved trips, one highlighted, click to open. |
| `plannerPage/PlannerMap.tsx` | `saved` mode alongside `discover`/`trip`. |
| `plannerPage/PlannerPage.tsx` | derives the sidebar view from the hash and `mode`, tracks `openedFrom: 'results' \| 'saved'`, renders `SidebarHeader` above the views, no `AppShell`. |
| `plannerPage/TripPanel.tsx` | per-night status toggle, notes field, back label from `openedFrom`. |
| `main.tsx` | `#trips` renders `PlannerPage`; the `TripsPage` branch is removed. |
| `adminPage/AdminPage.tsx` | own minimal inline title bar (no nav — the view is unlinked). |
| `AppShell.tsx`, `AppShell.test.tsx`, `plannerPage/TripsPage.tsx`, `plannerPage/TripsPage.test.tsx` | removed. |

`.claude/CLAUDE.md` "App structure" is updated to drop `AppShell`/`TripsPage` and describe the
sidebar views.

## Error handling

- Unresolvable saved trip: row with "geändert", no map line, still openable (trip panel already shows
  "changed since saved").
- Invalid import file: `Alert` in the list, trips unchanged.
- Leg geometry fetch failure: straight dashed segment.

## Testing

Vitest + React Testing Library, following the existing `*.test.tsx` files:

- `SidebarHeader`: active signpost per view; count in the label.
- `SavedTripsList`: rename, delete + undo, import (valid and invalid), export — carried over from
  `TripsPage.test.tsx`; pinned draft row; "geändert" row; empty-state link.
- `PlannerPage`: `#trips` shows the list; opening from the list → back label "← Meine Touren" and back
  returns to the list; opening from results → "← Ergebnisse"; switching to Meine Touren in trip view
  keeps the draft.
- `TripPanel`: status toggle and notes call `onChange` with the updated trip.
- `SavedTripsLayer`: one line per resolvable trip; hover and click callbacks.
