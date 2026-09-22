# Planner UI iteration

Date: 2026-09-21
Status: in progress

## Purpose

The map-first Planner (`2026-09-04-trip-planner-reenvision-design.md`) shipped. Using it surfaced
friction in the filter bar, result discovery, map interaction, the trip panel and Meine Touren. This
spec settles the direction for each point. All points are presentation/interaction problems and
belong in `huts/`.

## The user's job

"I have *these days* (or *N days*), *X people*, I arrive *by train/car*, I manage *~Y hours a day*
at *this difficulty*. Show me hut tours I can actually book, let me adjust one, and keep it."

Three structural problems in the shipped flow break that job:

1. **Picking commits.** Clicking a result (`PlannerPage.pick`) immediately creates and persists a
   `Trip`. "Look at this tour" and "keep this tour" are the same action, so Meine Touren fills up
   with every tour the user glanced at, and the detail screen reads like a form for a trip the user
   never chose to keep.
2. **Results are hidden.** Without a selected cluster the result list shows only a count and "Marker
   anklicken …". The user sees no tour until they find and click the right marker.
3. **Primary inputs are buried among secondary ones.** Date and party size already exist in the
   filter bar (`plannerState.ts` `TripDraft`) but sit below operator checkboxes, and the trip panel
   repeats them as a second form.

The sections below are ordered by implementation priority; each becomes its own plan.

## 1. Draft vs saved (E.15, E.16, E.17, D.14)

### Model

- `TripsState` (`tripsReducer.ts`, persisted by `tripStorage.ts`) gains one draft slot,
  `draft: Trip | null`, stored alongside `trips` and `activeId`. It survives a reload.
- Clicking a tour in the result list builds a trip (`tripFromTour`) into the draft slot and opens
  it. It does not touch `trips`.
- If the current draft was edited since it was opened (any change to huts, start, exit, dates or
  party size), replacing it asks first: "Entwurf verwerfen?" with "Verwerfen" / "Abbrechen". An
  untouched draft is replaced silently.
- "← Ergebnisse" leaves the draft in place. The next result click replaces it (with the question
  above if edited).
- The detail header shows an "Entwurf" badge and a primary "Speichern" button while the open trip
  is the draft. "Speichern" moves the draft into `trips`, clears the slot and keeps the trip open;
  from then on edits autosave as today. The header then shows the editable name instead of the
  badge.
- Opening a trip from Meine Touren edits that saved trip directly (autosave).
- Importing a share link (`ImportTripDialog`) saves directly: "Importieren" is already an explicit
  keep action.
- `activeId` points either at a saved trip or at the draft (a reserved id such as `'draft'`, or a
  separate `activeIsDraft` flag; the plan decides).

### Detail screen

The detail screen keeps route shaping and availability. It drops:

- booking status per night (offen/angefragt/bestätigt) and Notizen, which move to Meine Touren;
- the start/exit button lists, which move to the map (section 3).

Start date and party size show as a compact, clickable summary line ("12.–15.07. · 2 Pers." or
"ohne Datum · 2 Pers."). Clicking it opens a small popover with the two inputs. `StartDateStrip`
(shift the start date to find availability) stays.

### Meine Touren

- Only saved trips appear.
- The whole card is clickable and opens the trip in the planner.
- A `⋮` menu on each card holds "Umbenennen" and "Löschen" (delete keeps its undo snackbar).
- The card shows name, date range, nights, party size and a booking summary ("2/3 Nächte
  bestätigt"). Expanding the card shows per-night booking status (offen/angefragt/bestätigt, set
  here) and the Notizen field.
- "Sicherung exportieren/importieren" becomes "Touren exportieren (Datei)" and "Touren
  importieren". The import error reads "Die Datei enthält keine gültigen Touren."

## 2. Filter bar (A.1–A.5, D.11)

Order follows the user's job: primary inputs first, then collapsed secondary groups.

1. **Anreise** — unchanged select.
2. **Wann?** — a from–to date range. From is the first walking day and the first night
   (`Trip.startDate`); to is the day of the descent. Days = to − from + 1, nights = days − 1 (the
   search's `legCount` equals days: `search.ts` uses `nights = legCount − 1`). The field shows
   "4 Tage · 3 Nächte". With dates set, the length is exact (`legCountMin = legCountMax`).
   Without dates, a stepper "N Tage" (default 3) replaces the range, with a "flexibel ±1 Tag" chip
   that widens the search to N−1…N+1. A "Datum wählen" / "ohne Datum" link switches between the
   two. The ranking target is the exact day count; `targetLegCount` and its advanced field go away.
3. **Wie viele?** — stepper 1–9 (OHRS bound), default 1.
4. **Gehzeit pro Tag** — single-select chips "bis 5 h", "bis 7 h", "bis 9 h", default 7 h. The
   lower bound is derived as half the maximum (2.5 / 3.5 / 4.5 h). `legTimeRange` stays in the
   `Query`; only the control changes.
5. **Höchste Schwierigkeit** — the SAC ceiling, labelled as an upper limit. Each option carries a
   plain description:
   - T1 Wandern — breite Wege, kaum Absturzgefahr
   - T2 Bergwandern — schmale Pfade, Trittsicherheit nötig
   - T3 anspruchsvolles Bergwandern — ausgesetzte Stellen, teils Hände nötig
   - keine Grenze
6. **Wege & Hütten** (collapsed group) — "auch ungeratete Wege", "Klettersteige" (both default
   **off**), Hüttenarten (operators), "Bewirtschaftete Hütten", "Selbstversorgerhütten". The
   Selbstversorger checkbox has a short label plus a `?` icon button; click or keyboard focus opens
   a popover: "Unbewirtschaftet, meist Selbstverpflegung, ggf. Schlüssel beim Verein holen."
7. **Erweitert** (collapsed group) — Anstiegslimit pro Etappe, Maximalhöhe.
8. **Verfügbarkeit prüfen** — a checkbox, shown only when dates are set, default off. When on, the
   OHRS `collectAll` check runs for the chosen nights and party size; tours with a full night are
   hidden; huts without `ohrs_hut_id` (direct booking) count as "unbekannt" and are kept. A chip
   "auch volle Touren zeigen" brings full tours back, marked as such. Target behaviour is that
   setting dates alone triggers this; the checkbox gates it during development so that not every
   filter change fires availability requests. Removing the checkbox is a one-line change once
   wanted.

A collapsed group shows a summary of non-default values in its header (for example "Wege & Hütten
· Klettersteige an") so hidden filters are never invisible.

## 3. Map interaction and on-map editing (B.6, B.7, C.8, C.9, D.12, D.13)

### Discover

- The click gate stays: the list shows tours only for a selected start cluster.
- Without a selection, the panel shows the match count as a prominent primary button "N Touren
  anzeigen". It zooms to the cluster with the most matches and selects it. A one-line hint below
  explains that markers are start points and the number is the tour count.
- From zoom 11 on, the map draws the route lines of tours whose start is in the viewport, capped
  at the 50 best by the current sort. Below zoom 11, count clusters as today. Lines are drawn thin
  and muted; hovering a line (or its list row) highlights it and dims the others; clicking it opens
  the tour as the draft (section 1).

### Trip on the map

Every edit action lives on the object it changes, and is mirrored in the panel for keyboard use and
discoverability.

- **Hover** on a leg: tooltip with day number, from → to, time, ↑/↓ m. Hover on a hut: name, hut
  class, availability for that night when known. The matching stage row in the panel highlights,
  and vice versa.
- **Click on a trip hut**: popover with name, availability, "Hütte tauschen", "Hütte entfernen"
  (disabled with the reason when `trimAllowed` says no). "Hütte tauschen" shows candidates as
  markers exactly as today.
- **Click on the start or exit marker**: alternative start/exit points appear as markers; each
  tooltip says what changes ("Zug bis Mayrhofen · +0:40 h Zustieg"). Clicking one applies it.
  Escape or clicking elsewhere cancels. In car mode the exit follows the start.
- **"+" handle** at each end of the hut chain: "Etappe vorne anhängen" / "Etappe hinten anhängen";
  candidates appear as markers.
- **Panel mirror**: each stage row has a `⋮` menu with the same actions (Hütte tauschen, Hütte
  entfernen), the start and exit rows have "Anderen Start wählen" / "Anderes Ziel wählen", and the
  chain ends have "Etappe anhängen". Choosing one enters the same map candidate mode. Candidates
  are also listed in the panel as buttons so every edit works without the map.
- While a candidate mode is active, a small bar at the top of the map states it ("Neue Hütte für
  Nacht 2 wählen") with "Abbrechen".

### Station and parking markers

Stations use a rounded-square marker with a public-transport glyph; parking uses a rounded-square
"P". Both differ in shape from hut markers (`hutSymbol.ts`) and stay legible at the smallest zoom
they render at.

## 4. Height profile (C.10)

- Docked at the bottom of the map, collapsible, shown for the open trip (draft or saved).
- One profile for the whole trip, with vertical separators and day labels at each night.
- Hovering the profile marks the position on the map; hovering a leg on the map or in the panel
  highlights that stretch of the profile.
- Data comes from `tourSearch/loadLegElevation.ts` on the main thread (byte-range fetch of the
  elevation files). Neither the profile nor the hover summaries of section 3 need the worker's
  tables.

## Out of scope

Pipeline or data-contract changes. If a point turns out to need new data, it is filed against
`pipeline/` separately. A viewport-scoped result list (list follows the map's visible area) was
considered and rejected for now in favour of keeping the click gate.

## Resolved questions

- **Nights vs days in the `Query`:** `legCount` is days; `search.ts` derives nights as
  `legCount − 1`. The UI asks for days (via dates or the stepper) and shows nights alongside; the
  `Query` does not change.
- **Draft persistence:** one draft slot in `TripsState`, not a `saved` flag on `Trip`. Saved trips
  keep the current `Trip` shape.
- **Worker data for C.8/C.10:** not needed; leg scalars are in `TripLegs` and elevation loads on the
  main thread.
