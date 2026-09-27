# Frontend refactor: layered structure, feature folders, one styling system

Status: done

## Problem

Audit of `huts/src` at commit `75db4f7` (typecheck clean, 523 tests pass, 5 lint warnings):

1. **Inverted and cyclic dependencies.** `search/` and `data/` import from `plannerPage/`
   (`formState`, `plannerState`, `labels`, `types`); `tourSearch/` and `trip/` import each other
   (`tourSearch/tripLegs.ts:6`, `tourSearch/tripEdit.ts:7` import `trip/trip.js`; `trip/trip.ts:1`
   imports `tourSearch/types.js`).
2. **`plannerPage/` is flat**: 57 files plus 20 in `map/`. Pure logic (`rankTours`, `availabilityFilter`,
   `tripFromTour`, `tours`, `routes`, `plannerState`, `formState`) sits beside UI.
3. **`PlannerPage.tsx` is a god component**: 22 `useState`s; owns search, ranking, selection, map view,
   navigation, trip editing, sharing and dialogs.
4. **`PlannerMap` takes ~38 props** across three modes.
5. **Null-object placeholders** (`EMPTY_GRAPH`, `PLACEHOLDER_TRIP`, `PLACEHOLDER_LEGS`, `EMPTY_TRIP_LEGS`)
   exist because the planner renders before data is ready.
6. **Styling is scattered**: ~114 inline `sx` props in `plannerPage/`, 22 hardcoded color literals outside
   `theme.ts` tokens (`map.css` repeats `#f5b700` / `#23272b`), three unrelated CSS files (251 lines total).
7. Test fixtures in production directories; stray root files; `subscribeHash` copy-pasted twice;
   provider files mixing components and hooks (5 `react/only-export-components` lint warnings).

## Decisions

- **Incremental, not a rewrite.** The 523-test suite is the safety net; every step keeps
  `typecheck`, `lint`, `test` and `build` green.
- **No SCSS.** The app is MUI/Emotion; theme tokens live in JS. Tokens become CSS custom properties
  generated from one JS source (`ui/tokens.ts`); plain CSS (native nesting, `var()`, `color-mix()`)
  is used only where MUI cannot reach (Leaflet DOM).
- **Hand-rolled hash router stays** (tiny); it gets a shared `useHash` hook.
- **`@/` import alias** for cross-directory imports (`@/data/buildAppData.js`); `./` within a directory.
- `adminPage/` and `gpxEditor/` keep their names and locations.

## Target layout

```
huts/src/
  app/         main.tsx, Router.tsx, index.css
  lib/         useHash.ts (generic hooks/utilities)
  ui/          tokens.ts, theme.ts
  format/  availability/  tourSearch/      engine, pure TS (tourSearch no longer contains trip*)
  trip/        model, reducer, storage, shareLink, TripsProvider, tripLegs, tripEdit, tripOverlaps
  data/        AppData, loaders, hutClass, labels, StartPoint type
  search/      worker + client + provider
  features/
    planner/   PlannerPage (composition root), SidebarHeader, dialogs, first-visit prompt
    discover/  filters, results, formState, plannerState, ranking, usePlannerSearch, tripFromTour
    trip/      TripPanel, TripEditor, StageList, availability/overlap hooks
    saved/     SavedTripsList
    map/       PlannerMap, layers, routes, map.css
  adminPage/  gpxEditor/  testing/
```

**Layering rule** (enforced by `src/architecture.test.ts`): a file may import only from its own
top-level directory or a lower layer.

| Layer | Directories |
|---|---|
| 0 | `lib`, `ui`, `format`, `availability`, `tourSearch` |
| 1 | `trip` |
| 2 | `data`, `search` |
| 3 | `features/*`, `adminPage`, `gpxEditor` |
| 4 | `app` |

Additionally `features/X` never imports `features/Y`, except `features/planner`, which composes all.
`testing/` (fixtures) is exempt.

## Phases (each is one plan)

1. `001-foundations` — `@/` alias, `testing/`, `lib/useHash`, stray files, dead code.
2. `002-untangle-dependencies` — cycle and inversion fixes, `architecture.test.ts`.
3. `003-feature-folders` — split `plannerPage/` into `features/*`.
4. `004-ready-boundary-and-providers` — no placeholders, zero lint warnings.
5. `005-decompose-planner` — per-feature hooks, `PlannerMap` mode-specific props.
6. `006-styling` — tokens as CSS variables, `*.styles.ts`, Leaflet CSS, conventions.
