# Discover map: signpost placement instead of stacks

Supersedes the stack and spread parts of
[2026-09-25-discover-map-signposts](2026-09-25-discover-map-signposts-design.md) and the stack part
(§4) of [2026-09-26-signpost-route-anchors](2026-09-26-signpost-route-anchors-design.md).

## Problem

From `ROUTE_REVEAL_ZOOM` on, each tour's board stands on a mast planted on its route's mid-route
anchor. `createAnchorClusterer` (`features/map/clusterStarts.ts`) groups anchors within 70 px into
one stack signpost that spreads on hover.

- **Stacks are a collision device, and a poor one.** Stacks were designed for start-point boards,
  where every tour of a start shared one point. With route anchors a stack is just tours whose
  anchors happen to fall within 70 px. The mast stands on the best-ranked tour's anchor; the other
  boards belong to routes up to 70 px away, so the post cannot point at their cards.
- **The spread is detached from the mast.** The count sign is centred on the mast, the boards start
  12 px beside it and climb up to nine pitches above a 24 px mast, the side is picked by viewport
  half rather than heading, and the backdrop is a fixed 240 px.
- **Some stacks never resolve.** Tours sharing their middle leg get the identical 50 % anchor, so
  zooming in never separates them.

## Goal

Every board stands on its own route. Where boards would collide, lower-ranked tours move to another
anchor along their route; tours that fit nowhere show as a foot dot that reveals its board on hover.
No stacks, no spread.

## 1. Placement

- **Candidates.** `tourSearch/tourAnchor.ts` gains
  `anchorCandidates(route, lookup, bbox): TourAnchor[]`: every anchor candidate of the route (the
  shipped per-leg anchors, chord points for legs without) inside `bbox`, ordered by distance from
  half the tour's total distance, each with its heading. `tourAnchor` returns the first candidate
  of the unfiltered list when it is in view, else the first in-view one (unchanged behaviour),
  implemented on top of the same candidate list.
- **Board size.** `measureBoard(label): number` measures the board's text with canvas
  `measureText` in the board font (`600 0.8rem 'Barlow Semi Condensed'`), adds padding and gap and
  the distance text, and clamps to 220 px (the CSS `max-width`). Board height is `--board-h`
  (26 px), mast height `--mast-h` (24 px). The measure function is a parameter so tests use fixed
  widths.
- **Greedy placement.** `placeSignposts(tours, project, measure, viewport)` in the new
  `features/map/placeSignposts.ts`, a pure function:
  - `tours` are in rank order, best first (the order of `allTours`), each with its key, label and
    `anchorCandidates`. `project` maps lat/lng to container pixels.
  - For each tour, for each candidate, try the heading side first, then the other side. The box is
    the board plus its mast in screen pixels with a 4 px margin. The first box that lies inside the
    viewport and hits no box placed so far wins: the tour becomes a `board` at that candidate and
    side.
  - A tour with no fitting box becomes a `dot`, placed after all boards: at the first candidate
    not within 8 px of an existing foot or dot, else at its first candidate. Dots never block
    boards.
  - Result: `{ key, kind: 'board' | 'dot', lat, lng, side: 'left' | 'right' }[]`, where `side` of a
    dot is its heading side (used for its preview).
- **When.** On every view change (`moveend`/`zoomend`), where `DiscoverLayer` runs the anchor
  clusterer today. Never while dragging. No hysteresis and no cap on the number of boards; the
  collision test bounds density.
- **Below `ROUTE_REVEAL_ZOOM`** the start-point count bubbles are unchanged.

## 2. Rendering and interaction

- **Board.** Today's single board: mast, foot, one sign, with the side class (`side-left` /
  `side-right`) from the placement instead of `SignpostMarker`'s own viewport-edge flip. Hover or
  focus hovers its tour; click or Enter picks it (`onPickRoute`). Dimmed, highlighted and faded
  behave as today.
- **Dot.** A foot without a mast: 8 px, signpost yellow with an ink border, 16 px hit area.
  - Hover or focus hovers its tour and shows the tour's board as a preview on the dot's side, raised
    above every marker and ignoring collisions. No open delay.
  - Click or Enter picks the tour.
  - While its tour is hovered from elsewhere (results list row, route line), the dot shows the same
    preview, so hovering a list row always shows a board on the map.
  - Dims like a board.
- **`SignpostMarker`** takes `kind: 'board' | 'dot'` and `side`. `Activation` shrinks to the tour
  activation. The spread state, hover-intent timers, backdrop, spread z-offset, Escape handling and
  `to-left`/`to-right` classes are deleted.
- **`signpostHtml`** keeps `singleHtml` (taking the side) and gains `dotHtml` (the dot plus a hidden
  board for the preview). `stackHtml` and `SPREAD_CAP` are deleted.
- **Dropped behaviour.** The stack click (focus the list on the stack's tours and fly to their
  bounds) goes away; a shared leg or hut click still does that.
- **Keyboard.** Boards and dots are focusable, boards first, then dots, each in rank order.

## 3. Files

| File | Change |
|---|---|
| `tourSearch/tourAnchor.ts` | `anchorCandidates`; `tourAnchor` built on it |
| `features/map/routes.ts` | `tourAnchorCandidatesOf` alongside `tourAnchorOf` |
| `features/map/placeSignposts.ts` (new) | `placeSignposts`, `measureBoard` |
| `features/map/DiscoverLayer.tsx` | calls `placeSignposts` on view change; stack activation and stack HTML removed |
| `features/map/SignpostMarker.tsx` | board / dot kinds, preview; spread code removed |
| `features/map/signpostHtml.ts` | `stackHtml`, `SPREAD_CAP` removed; `dotHtml` added |
| `features/map/clusterStarts.ts` | `createAnchorClusterer`, `AnchorMarker`, `anchorMarkerKind`, `MarkerKind` removed |
| `features/map/map.css` | stack and spread rules removed; dot and preview rules added |

## 4. Testing

- `placeSignposts` (unit, fixed widths, identity-like projection):
  - rank order wins a collision;
  - a lower-ranked tour moves to its next candidate;
  - the other side is used when the heading side collides or leaves the viewport;
  - a tour with no fitting box becomes a dot;
  - two tours with an identical first candidate both get boards on different candidates;
  - dots avoid each other's candidates, and fall back to their first candidate when all are taken.
- `anchorCandidates`: ordered by distance from half-way, bbox-filtered, headings kept. Existing
  `tourAnchor` tests keep passing.
- `SignpostMarker`: dot preview on hover, on focus and on outside highlight; click and Enter pick
  the tour; board side class follows the placement.
- `DiscoverLayer`: stack tests replaced by board/dot tests; a dropped tour renders as a dot, and
  hovering its tour from outside shows the preview.
- Spread, overflow and anchor-clusterer tests are deleted.

## 5. Docs

- `STATUS.md`: row for this spec; the two earlier signpost specs note that their stack parts are
  superseded by this one.
- `.claude/CLAUDE.md`: the sentence on `createAnchorClusterer` stacks and hover spread is replaced by
  the placement and foot-dot description.
