# Discover map: signpost markers, real symbols, emphasis tiers

## Problem

In Discover mode:

- **Bubbles look like huts.** A count bubble is a yellow disc with an ink border. The route dots
  drawn by `RouteLayer` are also yellow discs with an ink border. Only size and the number differ.
- **Cluster vs. start.** A bubble that stands for several start points looks the same as one that
  stands for a single start point. The `DiscoverLayer` doc comment claims cluster bubbles "carry a
  ring", but `map.css` has no `.cluster` rule, so nothing renders it.
- **Hover does nothing in focus.** While focused on a bubble, every focused tour is already drawn at
  full strength. The hover highlight is drawn over an already full-strength route, so it is
  invisible. All routes share one yellow, so tours from the same start cannot be told apart.
- **Overlapping tours.** Each tour has its own stacked polyline; the topmost takes the hover. Tours
  that share legs cannot be hovered together.

## Goals

1. Bubbles cannot be mistaken for huts, and single tour / several tours / several start points read
   differently at a glance.
2. Route waypoints show what they are: huts as hut symbols, start and exit points as their symbols.
3. Hovering a tour is visibly different from merely being in focus, in the same style the
   single-tour screen uses.
4. Hovering an overlapping leg or a hut highlights every tour that contains it, on the map and in
   the list; clicking it focuses the list on those tours.
5. A tour's board says where it ends and how long it is, so tours from one start can be told apart
   without hovering each one.

Out of scope: per-tour colours (separate later spec); hiding route dots while
unfocused (waypoint symbols stay drawn); touch devices (the spread and shared-leg/hut hover are
pointer-only).

## Design

### 1. Signpost markers

The brand signpost shape (arrow clip-path, as `.swap-signpost`) replaces the disc. Three kinds:

| Marker stands for | Look |
|---|---|
| One start point, one tour | Single tour board (see *Tour boards*); click picks the tour |
| One start point, several tours | Stack of boards with the tour count |
| Several start points (cluster) | Two-arm signpost, arms pointing opposite ways, with the summed count |

- **Tour boards.** A board that stands for one tour (the single-tour marker, every board of a
  spread) is labelled with the tour's end point and total distance, e.g. `Kaunertal 42.3 km`:
  - End point: the bare `name` of the tour's `exitStartId` start point (`startById`), without the
    `(Parkplatz)`-style suffix `makeStartLabel` adds. The board's small start-point symbol
    (`startSymbolSvg`) shows the kind instead. An unnamed start point falls back to its kind label
    (`SOURCE_TYPE_LABEL`). When the exit is the start (`exitStartId === startId`) the label reads
    `Rundtour` instead.
  - Distance: `totalDistanceM`, formatted as the results list does (`42.3 km`). The list and the
    board share one formatter in `format/`.
  - Long names truncate with an ellipsis at a fixed maximum board width; the board's `title` holds
    the full `makeStartLabel` text.
- A cluster never spreads (it can hold hundreds of tours); click keeps today's behaviour: fit the
  map to its tours and set the focus.
- **Spread on hover (stack only).** Hovering a stack spreads it into one tour board per tour, animated,
  so each tour can be hovered and clicked on its own. Hovering a board highlights that tour (tier 3
  below); clicking it picks the tour (`onPickRoute`). Moving the pointer off the spread collapses it.
- The spread is a single hover region: the stack's icon holds all boards at once and CSS transforms
  move them, so the DOM is not replaced under the pointer (no mouseout flicker). Pointer events on
  a board resolve to its tour via a `data-tour-key` attribute. An invisible backdrop element behind
  the spread covers the gaps between boards, so the pointer never leaves the region while crossing
  from one board to another.
- **Spread layout.** Labelled boards are too wide for a radial fan. The spread stacks the boards
  vertically on one pole above the marker, like a real signpost, in list order from the top. Each
  board points left or right, whichever side has more room on screen.
- **Hover intent.** The stack spreads only after the pointer rests on it for ~200 ms, so sweeping
  across the map does not fan out every stack passed. It collapses ~250 ms after the pointer leaves
  the region, so a diagonal move to an outer board does not collapse it. It collapses at once on
  `zoomstart` and `dragstart`.
- **Stacking order.** A spread marker is raised above all other markers (`zIndexOffset`) while
  spread, so the spread is never covered by a neighbour.
- **Cap.** Spread shows at most 8 boards. A start with more tours shows the first 8 in list order
  plus an overflow board (`+n`) that, on click, does what a stack click does today: focus the
  results list on that start. The overflow board's title (`title` attribute) says so: "Alle n
  Touren in der Liste zeigen". Number chosen so the column stays short enough to read at a glance;
  revisit after seeing it on real data.
- **Reduced motion.** Under `prefers-reduced-motion: reduce` the spread and collapse happen without
  the transform transition.
- **Keyboard.** Every marker and every spread board is focusable. Focus acts as hover (a focused
  stack spreads, a focused board highlights its tour), Enter acts as click, Escape collapses a
  spread.
- The existing states carry over on the new classes: dimmed (search running or outside the focus),
  highlighted (a list row is hovered), hover.
- Size: board height fixed, width follows the digit count, with a minimum width so one- and
  two-digit boards read as the same marker kind. The old `markerRadius` scaling is dropped unless
  the stack looks wrong without it.

### 2. Waypoint symbols

- `RouteWaypoint` gains a kind: `hut` (operator, serviced) or `end` (sourceType), filled by
  `tourToRoute`/`routes.ts` from the data in `RouteContext`. If `RouteContext` does not carry the
  hut classification, the plan adds it from `data/hutClass.ts`; nothing is guessed on the client.
- `RouteLayer` draws lines only. A separate waypoint layer draws one symbol per unique hut or end
  point across all visible routes (many tours share huts; per-route markers would duplicate them).
  Symbols use `hutSymbolSvg` / `startSymbolSvg`, in Leaflet panes that follow the tier opacities.
- A symbol on a hovered tour uses `selected: true` (yellow fill), as `TripLayer` does.
- Trip and saved-trip views keep their current behaviour: `RouteLayer` with `muted=false` still
  draws its own bold route and dots there. The plan must show those views unchanged.

### 3. Emphasis tiers

| Tier | Applies to | Look |
|---|---|---|
| Rest | tours outside focus and hover | faint, today's 0.35 pane opacity |
| Focused | tours in the focus (see section 4), or of the hovered bubble | medium: thin muted line, ~0.7 opacity |
| Hovered | the hovered tour(s) | single-tour style: 4px yellow over ink casing, yellow symbols, above all |

The hovered tier is a display-only copy above the others; the interactive layers underneath never
change, so mouseout always fires (existing rule in `DiscoverLayer`).

### 4. Shared-leg and hut hover

- `RouteLeg.edgeId` identifies a leg across tours. Hovering a polyline reads its leg's `edgeId`
  and looks up every visible tour containing it; all of them get the hovered tier.
- Hovering a hut symbol from the waypoint layer does the same for every visible tour that stops at
  that hut (matched by hut GUID).
- The hover state changes from a single `hoveredTourKey: string | null` to a set of keys through
  `DiscoverLayer`, `onHoverTour` and the results list. The list highlights every matching row.
- A tooltip follows the hover: on a leg "In n Touren", on a hut the hut name plus "In n Touren".
  With n = 1 the count still shows, so the tooltip reads the same in every case.
- Clicking a shared leg or a hut focuses the results list on the tours it matched, as a stack
  click does for one start. The focus drops the same ways as today (show all tours, a map click,
  zooming out). Today's focus is a set of start ids (`focusStarts`); it becomes a focus on a set of
  tours, set either from start ids (bubble click) or from tour keys (leg or hut click), and the
  results list filters on that tour set. The leg/hut click stops propagation so it is not also read
  as the map click that drops the focus.
- Hovering a list row, or a spread board, still hovers just that one tour.
- The map highlight itself is unchanged by the size of the set: every matched tour gets the
  hovered tier.

## Components touched

- `features/map/DiscoverLayer.tsx`, `clusterStarts.ts`: marker kinds (single / stack / cluster),
  spread (hover intent, backdrop, z-order, keyboard), tier state, set-valued hover, leg click.
- `features/map/RouteLayer.tsx`, `routes.ts`, `types.ts`: lines only in Discover, waypoint kinds.
- New waypoint layer in `features/map/`: hut hover, tooltip, hut click.
- `features/map/map.css`: signpost markers, spread animation, reduced-motion rule.
- `features/discover/ResultsList.tsx` and the hooks passing the hover key: set-valued hover.
- `features/discover/useDiscover.ts`: focus as a tour set, settable from start ids or tour keys.
- The `DiscoverLayer` doc comment is rewritten to describe the shipped markers (no ring).

`features/X` never imports `features/Y` except `planner`; the hover set crosses map and discover
only through `planner`, as the single key does today.

## Testing

- Marker kind from group size and cluster membership (unit, `clusterStarts`).
- Tour board label: end-point name plus distance, `Rundtour` when exit equals start (unit).
- Stack spreads on hover into one board per tour up to the cap plus overflow (`DiscoverLayer`
  test); board hover sets that tour; board click calls `onPickRoute`.
- Spread timing: no spread before the open delay; no collapse inside the close delay; immediate
  collapse on zoom/drag start (fake timers).
- Keyboard: focus spreads a stack, Enter on a board calls `onPickRoute`, Escape collapses.
- Hover on a shared leg yields all tours containing its `edgeId`; hover on a hut yields all tours
  stopping there (unit, pure functions).
- Leg or hut click sets the focus to exactly the matched tours and does not drop it as a map click.
- Tier assignment: rest / focused / hovered for the combinations of focus, bubble hover, tour hover.
- One waypoint symbol per unique hut across overlapping routes.
- Trip and saved-trip route rendering unchanged (existing `RouteLayer`, `TripLayer`,
  `SavedTripsLayer` tests keep passing).

## Open assumptions

- Spread cap of 8 and maximum board width (see above).
- Hover-intent delays of ~200 ms open / ~250 ms close; tune on real use.
- Cluster markers do not spread.
