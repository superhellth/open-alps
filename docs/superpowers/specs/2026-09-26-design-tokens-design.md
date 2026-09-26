# Design tokens: spacing, type scale, colors

## Problem

Colors are centralized (`ui/tokens.ts` → MUI palette → `--color-*` CSS variables); spacing and type
sizes are not.

- **Spacing is ad-hoc.** About 74 `sx` spacing props use eight different MUI steps (0.25, 0.5, 0.75,
  1, 1.2, 1.5, 2, 4) with no rule for which one means what. `map.css` and a few `sx` strings use raw
  px (`padding: 3px 14px 3px 8px`, `margin: '4px 0'`, `padding: '0 4px'`). Similar containers differ
  (`TripPanel` root `p: 2, gap: 2` vs `FilterBar` root `p: 2, gap: 1.5`), and some groupings are
  inverted (`Signpost.styles.ts`'s `titleRow` has `gap: 2` inside a card whose siblings sit 1.5
  apart).
- **Spacing is scattered.** About 20 inline `<Box sx={{ display: 'flex', gap: … }}>` blocks sit in
  `.tsx` files instead of their `*.styles.ts`. Components set outer margins (`mt`, `mb`), so their
  spacing changes with where they are placed.
- **Type sizes bypass the scale.** Raw sizes `0.85`, `0.95`, `1`, `1.05`, `1.1rem` and `14` in TS and
  `0.8`, `0.9rem` in `map.css`, next to the MUI variants. `map.css` repeats the Barlow family string
  three times; weights mix `'bold'` and `700`.
- **Color leaks.** `data/hutClass.ts` has its own hex palette (`#1565c0`, `#6a1b9a`, `#ef6c00`),
  `alpha('#000', …)` appears twice, `#fff` three times in `map.css`, and opacity levels are literals.
- **Signpost geometry is duplicated.** `features/map/placeSignposts.ts` repeats `map.css`'s board
  height, max width, paddings and font (`BOARD_H`, `BOARD_MAX_W`, `BOARD_FONT`) to measure board
  widths for collision; the two can drift silently.

## Goal

One token source for spacing, type, color, opacity and signpost geometry. Every spacing value names
the relationship it expresses. A test fails on any literal that bypasses the tokens.

Scope: the planner UI (`features/`, `data/`, `ui/`, `app/`), desktop only. Density stays roughly as
today: values snap to the nearest step, except where grouping is wrong (inner space ≥ outer space),
which is fixed even if it gets roomier.

Out of scope: mobile/responsive layouts, changing the color palette itself, marker shapes,
`adminPage/`, `gpxEditor/`.

## 1. Token model (`ui/tokens.ts`)

`tokens.ts` gains four groups next to the existing colors. `tokenCssVariables` generates a CSS
variable for each entry; `app/main.tsx` keeps injecting them on `:root` via `GlobalStyles`.

### `space` — MUI units (1 = 8 px)

| token     | px | meaning |
|-----------|----|---------|
| `inline`  | 4  | icon ↔ label, parts of one chip, stats within one line |
| `item`    | 8  | controls in one row, lines within one card or list entry |
| `row`     | 12 | vertical padding of a list entry |
| `group`   | 16 | between groups: filter blocks, list entries without dividers |
| `section` | 24 | between sections of a panel |
| `inset`   | 16 | panel edge padding (sidebar panels, header side padding) |

The underlying steps are 4, 8, 12, 16, 24 px. Today's 0.25, 0.75 and 1.2 fold into `inline` or
`item`. CSS variables: `--space-inline: 4px` etc.

### `fontSize` — rem

| token | rem   | bound to |
|-------|-------|----------|
| `xs`  | 0.75  | `caption` |
| `sm`  | 0.875 | `body2`, `subtitle2`, signpost boards, count bubbles |
| `md`  | 1     | `body1`, calendar input, sidebar tabs |
| `lg`  | 1.125 | trip Signpost title, wordmark |
| `xl`  | 1.25  | `h6` |

`theme.ts` sets the MUI typography variants from these. Changes that result: sidebar tabs
0.95 → `md`, Signpost stats 0.85 → `sm`, Signpost title 1.05 → `lg`, wordmark 1.1 → `lg`, count
bubble 0.9 → `sm`, map boards 0.8 → `sm` (boards get ~9 % wider; placement measures from the same
token, so collisions stay correct).

Font families move to tokens as `fonts.body` (Barlow) and `fonts.signpost` (the existing
`SIGNPOST_FONT`, kept as an export), with `--font-body` / `--font-signpost` variables. Weights are
numeric only (`600`, `700`).

### Colors and `opacity`

Existing colors stay. Added:

- `white` — hover faces of boards, dots and bubbles.
- `hutAv`, `hutOther`, `hutPartner` — the hut operator/partner colors, moved from
  `data/hutClass.ts` (which then reads them from tokens). Values unchanged.
- `alpha('#000', …)` becomes `alpha(tokens.ink, …)`.

`opacity`: `dimmed` 0.45 (dimmed markers), `hoverTint` 0.05, `hoverTintStrong` 0.09 (tab
backgrounds), `muted` 0.6 (unselected tab text), plus `shadow` 0.15 and `outline` 0.23 for the two
former `#000` uses. CSS variables `--opacity-*`.

### `marker` — signpost geometry

Single source for `placeSignposts.ts` and `map.css`:

`boardH` 26, `mastH` 24, `boardMaxW` 220, `boardPadNear` 8, `boardPadFar` 16, `boardGap` 6,
`arrowW` 10 (px), and `boardFont` — the full canvas font string built from `fontSize.sm` and
`fonts.signpost` at weight 600. `placeSignposts.ts` imports these; `.signpost-marker` sets
`--board-h: var(--marker-board-h)` etc. The swap signpost uses the same padding tokens.

## 2. Usage rules

1. **Parents own spacing.** Components set no outer margin (`m`, `mt`, `mb`, `mx`, …); sibling
   spacing comes from the parent's `gap`. Components use `p*` for their own inset and `gap` for their
   children. Margins appear only as `0` resets.
2. **Space inside ≤ space outside.** An element's inner gaps never exceed the gap around it.
3. **Spacing lives in `*.styles.ts`.** Inline `sx` blocks that set spacing move into the component's
   styles file.
4. **Text sizes via MUI variants or `fontSize.*` only.** Icons use MUI's `fontSize="small"` or
   `"inherit"` (the ResultsList sort arrows' `fontSize: 14` becomes `inherit`). SVG glyph geometry
   (`AvailabilityMark`'s `fontSize="9"`) is icon geometry and stays.
5. **Colors via `tokens.*`, palette keys or `var(--color-*)` only;** `alpha()` levels via
   `opacity.*`.
6. **Exempt by nature:** Leaflet API numbers (tooltip offset, pane z-indices), route line styling in
   `routePanes.ts` (its tier opacities stay local, named in the `TIERS` table), SVG glyph geometry,
   marker positioning (`left`, `top`, `width`, `height`, `inset` in `map.css`).

## 3. Enforcement

`huts/src/designTokens.test.ts`, next to `architecture.test.ts`, reuses its file-walking approach
and scans text by regex (no AST).

Scope: every `.ts`, `.tsx`, `.css` under `src/` except `ui/tokens.ts`, `ui/theme.ts`, test files,
`adminPage/`, `gpxEditor/`.

Rules — a line fails when it contains:

1. **Spacing literal** — TS: a `p|px|py|pt|pb|pl|pr|gap|rowGap|columnGap|padding\w*` key with a
   non-zero numeric or px/rem string value. CSS: `padding`, `gap` with a px/rem literal.
2. **Margin** — TS: a `m|mx|my|mt|mb|ml|mr|margin\w*` key with a value other than `0`. CSS:
   `margin` with a value other than `0`.
3. **Font size literal** — TS: `fontSize:` with a numeric or rem/px literal. CSS: `font-size` or the
   `font` shorthand with a literal size.
4. **Color literal** — a hex color, `rgb(`/`rgba(`, or `'white'`/`'black'` as a value. CSS: same,
   outside `var(--color-*)`.
5. **Opacity literal** — `alpha(<x>, <number literal>)`.
6. **Font family literal** — `Barlow` in a string outside `ui/tokens.ts`.

Exceptions carry a marker on the same line: `// design-exempt: <reason>` (TS) or
`/* design-exempt: <reason> */` (CSS). The test fails on a marker with an empty reason. Expected
exemptions: the MUI accordion summary margin override in `FilterBar.styles.ts` (if it cannot be
expressed as a token), the Leaflet tooltip offset, the `routePanes.ts` tier opacities.

Failures list `file:line  rule  offending text`.

`tokens.test.ts` is extended: `tokenCssVariables` has exactly one variable per token across all
groups (`--color-*`, `--space-*` in px, `--font-size-*`, `--font-*`, `--opacity-*`, `--marker-*`)
with matching values. `theme.test.ts` asserts the typography variants read from `fontSize`.

## 4. Migration

One commit per step; the enforcement test runs from step 2 with a temporary `PENDING` list of
not-yet-migrated files that each step shrinks.

1. **Tokens and theme** — the groups from §1, typography variants bound to `fontSize`, CSS variable
   generation, `tokens.test.ts` / `theme.test.ts`.
2. **Enforcement test** with `PENDING` holding every currently failing file.
3. **Sidebar shell** — `PlannerPage`, `SidebarHeader`, `PlannerLoading`.
4. **Discover** — `FilterBar`, `RangeCalendar`, `ResultsList`.
5. **Trip** — `TripPanel`, `TripEditor`, `StageList`, `Signpost`, `StartDateStrip`,
   `TripDateSummary`, `AvailabilityMark`.
6. **Saved** — `SavedTripsList`.
7. **Map** — `map.css` onto the variables, `placeSignposts.ts` onto `tokens.marker`,
   `TripMapLayers.styles.ts`, `routePanes.ts` naming; boards to `sm`.
8. **Colors** — `hutClass.ts` colors to tokens, remaining `#000`/`#fff`.
9. **Close out** — delete `PENDING`; add a design-tokens paragraph to `.claude/CLAUDE.md`'s "App
   structure" (token groups, the usage rules, the enforcement test).

## Verification

- After each step: `npm test` (including the existing `placeSignposts` tests, whose width
  assertions must follow the new board font), `tsc`, lint.
- Visual review by the user; each step's commit message lists what to look at (e.g. "Signpost title
  row tighter", "boards slightly wider"). No dev server is started by the implementer.
