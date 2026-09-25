# Frontend refactor plans

Spec: `docs/superpowers/specs/2026-09-25-frontend-refactor-design.md`. Written at commit `75db4f7`, 2026-09-25.
Execute strictly in order; each plan assumes the previous ones landed. Read the plan fully first and
honor its STOP conditions.

| Plan | Title | Priority | Effort | Depends on | Status |
|------|-------|----------|--------|------------|--------|
| 001 | [Foundations: alias, testing dir, useHash, stray files](001-foundations.md) | P1 | S | — | DONE |
| 002 | [Untangle dependencies and enforce layers](002-untangle-dependencies.md) | P1 | M | 001 | DONE |
| 003 | [Split plannerPage into feature folders](003-feature-folders.md) | P1 | M | 002 | DONE |
| 004 | [Ready boundary, provider split, zero lint warnings](004-ready-boundary-and-providers.md) | P2 | M | 003 | TODO |
| 005 | [Decompose PlannerPage and PlannerMap](005-decompose-planner.md) | P2 | L | 004 | TODO |
| 006 | [Styling: tokens as CSS variables, style modules](006-styling.md) | P2 | M | 005 | TODO |

Status values: TODO | IN PROGRESS | DONE | BLOCKED (one-line reason) | REJECTED (one-line rationale).

## Repo rules that apply to every plan (repeated inside each plan)

- Run all commands from `huts/`. Baseline before plan 001: `npm run typecheck` clean; `npm run lint`
  5 warnings; `npm test` = 89 files passed, 1 skipped; 523 tests passed, 1 skipped; `npm run build` ok.
- Never work on `main`. Use branch `refactor/frontend-structure` (create it once, from the current
  branch HEAD, at plan 001; later plans continue on it).
- Never create or remove a git worktree. Never spawn subagents. Never run any `doit` / `pipeline/` task.
- Do not start a dev server or browser to check UI unless the operator asks.
- Comments state what the code does now; never cite history ("moved from", "previously").
- Commit per step, conventional-commit style, e.g. `refactor(ui): move test fixtures to src/testing`.
- Do not edit files under `docs/superpowers/specs/` except adding the STATUS row noted in plan 006.

## Dependency notes

- 002 needs 001 (`@/` alias, `data/hutClass`, `testing/`).
- 003 needs 002 (layer test, `features/discover` seed).
- 004 needs 003 (files already in feature folders, so the provider split touches final paths).
- 005 needs 004 (non-null data/client inside the ready planner).
- 006 needs 005 (style files are created per final component; components stop moving).

## Rejected findings

- `tourSearch/` size (54 files): cohesive and one-way once `trip*` files leave it (plan 002). No split.
- Test coverage: 523 passing tests are sufficient to refactor against; no characterization-test plan needed.
