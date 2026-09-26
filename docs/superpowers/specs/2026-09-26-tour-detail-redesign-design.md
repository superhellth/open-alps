# Tour detail view redesign

Date: 2026-09-26
Status: approved design, not yet implemented
Layer: `huts/` only (presentation and interaction). No pipeline or data-contract change.

## Problem

The trip view (sidebar `trip` view plus the trip map mode) has three defects:

1. **Legs cannot be hovered on the map.** `PlannerMap` renders the trip `RouteLayer` without
   `onHover`; the exit-leg row in `StageList` has no hover handler; a highlighted leg is only 2 px
   wider; `HeightProfile`'s `onHoverPosition` is wired to a no-op.
2. **The height profile is bland.** A bare polyline, no fill, no axes, no hut labels, no cursor
   or readout.
3. **The sidebar has no structure.** About eleven blocks (back/share, name or draft chip, stats
   line, date button, start-date strip, start/exit pickers, stages, warnings, notes, extend buttons)
   sit in one column with one gap. Each stage stacks a yellow signpost plate, availability, a
   booking link, a three-way status toggle and a ⋮ menu. Editing and booking controls are mixed.

## Decisions

- **No phases.** A leg and the night at its end are one row: "walk to hut X, sleep there on
  date Y". Splitting evaluate and book into tabs would force matching stage numbers across views.
- **The split is view vs. edit.** Editing controls appear only in an explicit edit mode.
- **Booking detail is second level.** A row shows availability and booking status as compact
  marks; the status toggle and booking link appear when the row is expanded by its chevron.
- **Hover only, no select state.** Hovering a stage row, a map leg or a profile section highlights
  the same leg in all three places. Nothing is sticky; clicking a profile section does nothing.
- **Yellow means "hovered leg".** Stage rows are plain; the signpost yellow appears on the hovered
  row (left bar), the hovered map leg and the hovered profile section. The only signpost plate in
  the sidebar is the trip header.
- **Profile stays under the map**, full width, collapsible.

## Sidebar layout

```
← Ergebnisse                              ⤴ Teilen
┌▶ Kaisertour-Variante     22:40 ───────────────╮   header plate (Signpost)
│  4 Nächte · 58 km · ↑ 3 420 ↓ 3 380          ╱
└─────────────────────────────────────────────╯
 [Entwurf]  [Speichern]                            draft only
 12.–16.07. · 2 Pers.                              date button, popover as today
 Do 11. ✕ | Fr 12. ● | Sa 13. ● | So 14. ?         start-day chips
───────────────────────────────────────────────
 Etappen                              [Bearbeiten]
 Start: Bhf X
 1  Hütte A                             5:30  ▸
    Fr 12.07. · ↑ 820 ↓ 310 · ● frei · angefragt
 2  Hütte B                             6:10  ▸
    …
 Abstieg nach Y                         3:00
 ⚠ warnings
───────────────────────────────────────────────
 Notizen [ text field ]
```

### Header (`TripHeader`)

- Top row: back button (label as today) and share button.
- One `Signpost` plate: title plus total time on the first line; nights, total km, total ascent
  and descent on the second.
- Title is the trip name for a saved trip, "Neue Tour" for a draft. Clicking the title of a
  saved trip edits it in place (text input replacing the title, commit on blur or Enter, Escape
  cancels). The separate Name field is removed.
- Draft only: `Entwurf` chip and `Speichern` button.
- Date button (`TripDateSummary`), unchanged behaviour; without a date it reads "Datum wählen".
- Start-day chips (`StartDateStrip`, reshaped): one row of chips for shifts −3…+3 days. Each chip
  shows weekday + day and the verdict mark (● bookable, ✕ blocked, ? unclear); the current day is
  highlighted and not clickable; clicking another chip shifts the start date by that many days.
  The separate −1/+1 buttons are removed. The strip is hidden while the trip has no start date.

### Stages (`StageList`)

Section heading "Etappen" with the `Bearbeiten` toggle on the right.

Row order and leg mapping (`n` = number of huts, `legs.length = n + 1`):

| Row | Leg | Hover target |
|---|---|---|
| Start: `<start label>` | none | not hoverable |
| Stage `i` (1…n), hut `i` | `legs[i-1]` (leg 0 is the approach) | leg `i-1` |
| Abstieg nach `<exit label>` | `legs[n]` | leg `n` |

For car trips the exit row reads "Abstieg zum Start".

**Stage row (`StageRow`), view mode**

- Line 1: stage number, hut name, leg time, expand chevron.
- Line 2: night date (only with a start date), ↑ ↓ of the leg, availability mark (only with a
  start date), booking status as text.
- Hover: signpost-yellow left bar; calls `onHoverLeg(i-1)` on enter, `onHoverLeg(null)` on leave.
- A night that no longer resolves ("changed since saved") renders in outline style with the
  existing text and no leg stats; it does not expand.

**Expanded booking detail (`StageBooking`)**

- `AvailabilityMark` (or "Verfügbarkeit lädt …").
- Booking link to hut-reservation.org when the hut has an `ohrsHutId` and the trip has a date;
  "Direktbuchung: die Hütte selbst kontaktieren." when it has no `ohrsHutId`.
- Status toggle `offen | angefragt | bestätigt`.
- Expansion state is local to `StageList` (set of expanded nights); not persisted.

**Exit row:** label, leg time, ↑ ↓; hoverable; never expands.

**Warnings:** overlap warnings render directly under the exit row.

### Edit mode

`Bearbeiten` toggles edit mode; the button reads `Fertig` while it is on. Leaving edit mode also
cancels any pending edit (`editing = null`).

In edit mode:

- Chevrons and booking detail are hidden; line 2 of each row stays.
- Start row gets "ändern" (start candidates). Exit row gets "ändern" (exit candidates), except for
  car trips.
- Each stage row gets swap (⇄) and remove (✕). A disallowed remove is disabled and carries its
  reason as a tooltip.
- A "+ Etappe voranstellen" row appears between the start row and stage 1, a "+ Etappe anhängen"
  row between the last stage and the exit row.
- Starting an edit opens the candidate list directly under the row that triggered it (same
  content as today: name plus times, `Abbrechen`). Candidates also render on the map as today, and
  the map status bar stays.
- Hover on rows keeps working in edit mode.

### Footer (`TripFooter`)

Notes text field.

### Spacing

Sections (header, stages, footer) are separated by `space.section` and a divider. Inside a
section, `space.item`; inside a row, `space.inline`. All values from `ui/tokens.ts`; the design
token test must pass without new exemptions.

## Map

### Leg hover

- `PlannerMap` passes `onHover` to the trip `RouteLayer`; hover sets `highlightedLeg` through the
  existing `onHoverLeg` in `TripMapMode`.
- Each leg gets an extra invisible hit polyline (about 16 px wide, `HIT_PANE`) that owns the
  hover events; the visible lines stop being interactive.
- While a leg is highlighted it is drawn wider, and the other legs of the trip route drop to
  `opacity.dimmed`. No leg highlighted: all legs at full opacity.

### Profile cursor dot

- The profile reports the hovered position as `{ legIndex, fraction }` (fraction 0…1 along that
  leg). `PlannerMap` keeps it in local state and passes it to the trip `RouteLayer`.
- `RouteLayer` draws a dot on the leg's geometry at that fraction, using a pure helper
  `pointAlong(coords, fraction)` in `features/map/` (fraction of cumulative planar length).
  Geometry and elevation are both in travel direction: `loadLegGeometry` and `loadLegElevation`
  both honour `reversed`. A leg drawn as a straight fallback line uses the fallback segment.
- The profile spreads samples evenly over the leg distance, so the dot is an approximation of the
  same kind; that is acceptable.

## Height profile

`HeightProfile` is rewritten; `TripMapProfile` keeps the collapse toggle.

- Height about 140 px, full map width.
- Filled area under the line, muted ink tint. The hovered leg's section fills with signpost
  yellow, its line in ink.
- Night boundaries: solid thin verticals with the hut name at the top, truncated to fit the
  section; start and exit labels at the two ends. Stop names are passed through `TripMapMode`.
- Y axis: grid lines at round elevation steps (500 m, or 250 m when the span is under 1000 m),
  labelled on the left.
- X axis: km labels at each night boundary.
- Cursor: vertical line and a dot on the curve at the mouse position, with a readout
  "km 18,2 · 2 340 m · Etappe 2" (exit leg: "Abstieg").
- Hover reports `onHoverLeg(legIndex)` and `onHoverPosition({ legIndex, fraction })`; leave
  clears both.
- The SVG must render text at a fixed size, so it no longer uses `preserveAspectRatio="none"`;
  the chart measures its width (`ResizeObserver`) and computes coordinates in pixels.
- Pure helpers (scales, elevation ticks, nearest point) live in a separate module and are unit
  tested.

## Code structure

`features/trip/`:

- `TripPanel.tsx` becomes a shell composing `TripHeader`, `StageList`, `TripFooter`.
- New: `TripHeader.tsx`, `StageRow.tsx`, `StageBooking.tsx`, `TripFooter.tsx` (each with a
  `*.styles.ts`).
- `StageList.tsx` rewritten per above.
- `StartDateStrip.tsx` reshaped into the chip row.
- `TripEditor.tsx`: `useTripEditor` stops returning render functions (`renderRowMenu`,
  `renderEndpointMenu`, `renderExtendButtons`). It returns data and actions: `candidates`,
  `pickCandidate`, `activeLabel`, `trimAllowed(night)`, `startSwap(night)`, `startExtend(side)`,
  `startEndpoint(which)`, `cancel()`, plus `editing`. Rows render their own controls and the
  candidate list (a shared `CandidateList` component).
- `useTripSession.ts` owns `editMode` next to `editing`.

`features/map/`:

- `RouteLayer.tsx`: hit polylines, dimming of non-highlighted legs, cursor dot.
- `pointAlong.ts` (new, pure).
- `HeightProfile.tsx` rewritten; `profileScale.ts` (new, pure).
- `TripMapLayers.tsx` / `PlannerMap.tsx`: cursor state, stop names, hover wiring.

`features/planner/PlannerPage.tsx`: passes the new editor shape and stop names; no new state.

Feature import rules stay as they are: `trip` and `map` do not import each other; shared types go
through `planner` or down into `trip/`/`ui/`.

## Testing

- Unit: `pointAlong` (ends, midpoint, uneven segments, single point), profile ticks and scales,
  nearest-point lookup.
- Component (update existing tests):
  - `StageList`: row-to-leg hover mapping including the exit row, start row not hoverable,
    chevron expand shows booking detail, changed night does not expand, edit mode shows swap /
    remove / "+" rows and hides chevrons.
  - `TripPanel` / `TripHeader`: draft vs saved title, in-place rename, start-day chips shift the
    date, strip hidden without date.
  - `HeightProfile`: section highlight, night labels, cursor readout, hover callbacks.
  - `RouteLayer`: hover callback from hit lines, dimming, cursor dot position.
  - `TripEditor`: new action API.
- `architecture.test.ts` and `designTokens.test.ts` stay green.

## Out of scope

- Slope colouring of the profile.
- Touch-specific interaction beyond what hover-free controls already give.
- Any pipeline or data change.
