# doit DAG status CLI — design

Date: 2026-09-01
Status: approved in brainstorming, ready for implementation planning
Scope: `pipeline/` tooling only — one new script plus a `pixi.toml` task and dependency. No
changes to any `dag/`, `lib/`, or `phases/` task-wiring code, no changes to `huts/`.

## Why

There's currently no way to see the whole pipeline DAG's shape and up-to-date/stale status at a
glance. `doit list --status` gives a flat, unordered list with a status letter per task but no
dependency structure; `doit info <task>` gives one task's deps/status but has to be run once per
task to see the whole picture. Neither shows "what's stale and why it'll cascade" in one view.

## Non-goals

- No interactivity, no drill-down, no filtering/search UI — confirmed with the user this is a
  one-shot status view, not a persistent TUI app. If that need shows up later it's a separate
  design (upgrade path noted below).
- No triggering of `doit` runs from this tool, ever. It only reads doit's dependency DB and file
  mtimes/hashes — the exact same read `doit list --status` already performs — never executes a
  task action. This matches `pipeline/CLAUDE.md`'s "never run a pipeline task without asking"
  rule: this tool has no code path that could accidentally kick one off.
- No static image output (the `doit-graph` + Graphviz `dot` route considered and rejected during
  brainstorming) — terminal-rendered text/tree output only.
- No stale-reason detail (e.g. "which file_dep changed") — confirmed with the user: just the
  status marker (up-to-date / stale), matching `doit list --status`'s R/U, not `doit info`'s full
  explanation. Keeps the tree scannable at ~26 tasks.

## Design

### New script: `pipeline/status.py`

Loads `dodo.py`'s task list and dependency manager in-process, the same way doit's own `list` and
`info` commands do internally (`doit.cmd_base.ModuleTaskLoader` over the `dodo` module, then
`dep_manager.get_status(task, tasks_by_name)` per task — see
`.pixi/envs/default/lib/python3.11/site-packages/doit/cmd_list.py` for the exact pattern this
follows). No subprocess, no shelling out to `doit` — this reads the same on-disk `.doit.db` dep
database and file mtimes/hashes that `doit list --status` reads, and nothing else.

Steps:
1. Load tasks via `ModuleTaskLoader(dodo)` → get `task_list` (all `Task` objects) and the
   `Dependency` dep-manager (same objects `DoitCmdBase` subclasses receive).
2. Build `tasks_by_name: dict[str, Task]`.
3. For each task, call `dep_manager.get_status(task, tasks_by_name).status` → one of doit's
   `'up-to-date' | 'run' | 'ignore' | 'error'` — map to a single character/color, mirroring
   `cmd_list.py`'s `STATUS_MAP` (`{'ignore': 'I', 'up-to-date': 'U', 'run': 'R', 'error': 'E'}`).
4. Build a forward-edge adjacency map from each task's `task_dep` list: for every name in
   `task.task_dep`, record `task.name` as a child of that dependency. This gives dependency →
   dependent edges, i.e. the direction the pipeline actually runs in (downloads → preprocessing →
   graph_building → postprocessing).
5. Roots = tasks with an empty `task_dep` list (currently `fetch_huts`, `fetch_dem`,
   `download_extracts`, `fetch_stations_parking`, `verify_trails` if independent — exact root set
   comes from `dodo.py`, not hardcoded in the script).
6. Render with `rich.tree.Tree`, one root `Tree` per root task, recursively adding each child as a
   sub-`Tree` under every parent that lists it in `task_dep`. A task with multiple parents (e.g.
   `build_hub_edges` depends on both `snap_hubs` and `gather_route_subgraphs`) is rendered in full
   under each parent branch — accepted duplication rather than cross-references, since the DAG is
   small (~26 tasks) and duplication keeps the tree readable without a legend.
7. Each node's label: task name, colored green with `✓` for up-to-date, red with `●` for
   run/stale, yellow with `?` for ignore/error (rare in practice, but doit exposes them so the
   script handles them rather than crashing).
8. Print the assembled `Tree` via a `rich.console.Console`.

No CLI arguments in v1 — always shows the full tree. (A `--task <name>` filter to show just one
subtree is easy to add later if it turns out useful, but nothing in this design blocks it — YAGNI
for now.)

### New dependency: `rich`

Added to `pipeline/pixi.toml`'s dependencies (not currently present — verified via `grep -i rich
pixi.toml` returning nothing). Small, single-purpose (colored tree/console rendering), no
transitive footprint beyond its own package. Only added to the `pipeline` pixi environment, not
`huts/`.

### New pixi task: `status`

Added to `pipeline/pixi.toml`'s `[tasks]` alongside the existing `doit` task, e.g.:
```toml
status = "python status.py"
```
so it's invoked identically to how `doit` itself is already invoked (`pixi run status`, from
`pipeline/`), no new invocation pattern to learn.

## Error handling

- Empty/missing `.doit.db` (fresh checkout, never run `doit` before): `dep_manager.get_status`
  already handles this — every task reports `'run'` (nothing recorded yet). No special-casing
  needed in `status.py`.
- A task with a `task_dep` on a name that doesn't exist in `tasks_by_name` (shouldn't happen —
  doit itself would fail to load the dodo file first) — not defended against; if `dodo.py` is
  malformed, the existing `doit list`/`doit run` already fail the same way, so this script failing
  identically is consistent, not a regression.

## Testing

- Manual: run `pixi run status` from `pipeline/` against the current (mixed R/U, per the earlier
  `doit list --status` output) state and confirm the tree's colors/structure match what
  `doit list --status` and `doit info <task>` report for a sample of tasks (e.g. `build_hub_edges`
  should show red/stale, `build_profiles` green/up-to-date, matching the R/U columns already
  captured earlier in this conversation).
- No dedicated automated test — this is a read-only reporting script over doit's own already-tested
  status computation (`dep_manager.get_status`); the only logic worth verifying is the tree
  construction from `task_dep`, which manual inspection against the known ~26-task DAG covers
  adequately for a tool this size. (`pipeline/tests/` exists for pipeline data-processing logic;
  this script has none of that shape.)

## Upgrade path (not built now)

If a one-shot view later turns out insufficient (e.g. wanting to drill into why a task is stale,
or re-check status after a run without re-invoking), the natural next step is a `--watch` flag or
a `textual`-based interactive mode built on the same `tasks_by_name`/status-computation core this
script already has — noted here so a future design doesn't have to re-derive the doit-API-loading
approach from scratch.
