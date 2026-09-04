# doit DAG status CLI — design

Date: 2026-09-01
Status: revised 2026-09-01 after review against the real DAG (§"Design" reworked — the original
draft's dep-DB path, adjacency source and tree-expansion strategy were each verifiably wrong; see
the inline notes). Ready for implementation planning.
Scope: `pipeline/` tooling only — one new script plus a `pixi.toml` task and dependency. No
changes to any `dag/`, `lib/`, or `phases/` task-wiring code, no changes to `huts/`.

## Why

There's currently no way to see the whole pipeline DAG's shape and up-to-date/stale status at a
glance. `doit list --status` gives a flat, unordered list with a status letter per task but no
dependency structure; `doit info <task>` gives one task's deps/status but has to be run once per
task to see the whole picture. Neither puts structure and staleness in the same view.

**What this tool can and cannot tell you about cascades.** `dep_manager.get_status` is a *local*
check: it compares one task's own `file_dep` hashes, targets and `uptodate` results against the dep
DB. It knows nothing about an upstream task that is about to rerun and rewrite those inputs. Against
the current DB this is not theoretical — measured while reviewing this spec:

| task | status |
|---|---|
| `gather_route_subgraphs` | run |
| `build_hub_edges` | run |
| `build_edge_payload`, `build_edge_ids` | **up-to-date** |

`build_edge_payload` consumes `build_hub_edges`' output, so a naive tree renders green leaves under
a red parent — the exact opposite of the impression a reader takes from a status tree. Note also
that a red ancestor does *not* guarantee a descendant reruns: if the upstream task rewrites its
outputs byte-identically, the hash is unchanged and the downstream task legitimately stays
up-to-date. So the cascade is genuinely not statically knowable, and the tool must not claim it is.
The design below therefore renders a **third, distinct marker** for "up-to-date itself, but has a
stale ancestor → may rerun" rather than either lying green or lying red (see Design step 4).

## Non-goals

- No interactivity, no drill-down, no filtering/search UI — confirmed with the user this is a
  one-shot status view, not a persistent TUI app. If that need shows up later it's a separate
  design (upgrade path noted below).
- No triggering of `doit` runs from this tool, ever. It only reads doit's dependency DB
  (`data/.doit.json.db`) and file hashes — the exact same read `doit list --status` already
  performs — never executes a task action. This matches `pipeline/CLAUDE.md`'s "never run a
  pipeline task without asking" rule: this tool has no code path that could accidentally kick one
  off. Verified during review by running the proposed load + `get_status` loop over all 27 tasks
  and diffing the dep DB afterwards: byte-identical. **Implementation constraint that keeps it
  that way:** never call `dep_manager.close()` or `backend.dump()`. `JsonDB` has no `__del__`, so
  with no explicit dump the file is only ever read — but `get_status` *does* mutate in-memory state
  (it deletes a task's recorded results if the checker class differs from the last run), so a stray
  dump would silently destroy the state a multi-hour run depends on.
- No static image output (the `doit-graph` + Graphviz `dot` route considered and rejected during
  brainstorming) — terminal-rendered text/tree output only.
- No stale-reason detail (e.g. "which file_dep changed") — confirmed with the user: just the
  status marker (up-to-date / stale / may-rerun), not `doit info`'s full explanation. Keeps the
  tree scannable at 27 tasks. (`get_status(..., get_log=True)` would supply the reasons if this is
  ever revisited.)

## Design

### New script: `pipeline/status.py`

Loads `dodo.py`'s task list and dependency manager in-process, the same way doit's own `list` and
`info` commands do internally (`doit.cmd_base.ModuleTaskLoader` over the `dodo` module, then
`dep_manager.get_status(task, tasks_by_name)` per task — see
`.pixi/envs/default/lib/python3.11/site-packages/doit/cmd_list.py` for the exact pattern this
follows). No subprocess, no shelling out to `doit` — this reads the same on-disk dep database and
file hashes that `doit list --status` reads, and nothing else. Every step below was executed
against the real DAG while reviewing this spec (doit 0.37.0, 27 tasks).

Steps:

1. **Load tasks.** `ModuleTaskLoader(dodo)` returns a loader, *not* tasks and *not* a dep-manager —
   the earlier draft conflated the two. `loader.load_tasks(cmd, pos_args)` needs a `cmd` object
   exposing `.execute_tasks` and needs `loader.cmd_names` set, or it raises
   `AttributeError: 'NoneType' object has no attribute 'execute_tasks'` (cmd_base.py:356). Use a
   trivial stand-in (`execute_tasks = False`, `cmd_names = []`).
2. **Build the dep-manager from `DOIT_CONFIG`, not from defaults.** The dep DB is *not* `.doit.db`
   in `pipeline/`. `dodo.py`'s `DOIT_CONFIG` sets `dep_file = data/.doit.json.db` and
   `backend = "json"`, and its comment explains why: the old dbm-format `.doit.db` cannot be read
   by the json backend. Both files still exist on disk — `data/.doit.db.dat` (dbm, last written
   2026-08-28) alongside the live `data/.doit.json.db` (2026-09-01) — so a script that hardcoded
   `.doit.db` would not fail loudly, it would report a plausible-looking status from a stale
   August database. Read the values from `loader.load_doit_config()`, never hardcode them:
   ```python
   cfg = loader.load_doit_config()          # {'dep_file': …, 'backend': 'json', …}
   db_class = {'dbm': DbmDB, 'json': JsonDB, 'sqlite3': SqliteDB}[cfg.get('backend', 'dbm')]
   dep_manager = Dependency(db_class, cfg['dep_file'], checker_cls=MD5Checker)
   ```
   `MD5Checker` is doit's default (`opt_check_file_uptodate`'s default is `'md5'`) and must match
   what actual runs use — see the checker-class warning in Non-goals.
3. **Resolve the real dependency edges before reading `task_dep`.** This DAG wires almost
   everything through `file_dep`/`targets`; explicit `task_dep` appears in only ~13 places, for
   the in-place-rewrite cases (`snap_hubs`, `build_profiles`, the tile builders…). Reading
   `task.task_dep` straight off the loaded tasks therefore does **not** give the pipeline's shape.
   Measured: **15 of 27 tasks have an empty `task_dep`**, so the earlier draft's tree would have
   rendered 15 roots — including `build_base_graph`, `merge_trails` and `copy_public_data` — i.e.
   a near-flat list, precisely what the tool exists to replace. (Its guessed root set, "`fetch_huts`,
   `fetch_dem`, `download_extracts`, `fetch_stations_parking`, `verify_trails`", matches neither
   reading.)

   doit fills the gap itself: `TaskControl.__init__` calls `set_implicit_deps`, which maps
   `target → producing task` and **appends the implicit deps onto each `task.task_dep` in place**
   (control.py:94-128). So one line makes the adjacency in steps 4–5 correct:
   ```python
   TaskControl(task_list)   # mutates task.task_dep to include file_dep-derived edges
   ```
   After that, roots = 3 (`download_extracts`, `fetch_dem`, `fetch_huts`) and the DAG layers
   cleanly into 12 depths, `download_extracts/fetch_huts → … → copy_public_data`. Roots stay
   derived, never hardcoded.
4. **Compute status per task, in two passes.**
   - Local status: `dep_manager.status_is_ignore(task)` **first**, then
     `dep_manager.get_status(task, tasks_by_name).status`. The order matters and the earlier draft
     had it wrong: `get_status` only ever returns `'up-to-date' | 'run' | 'error'`; `'ignore'` is a
     separate query, which is exactly why `cmd_list.py:_print_task` checks `status_is_ignore`
     before calling `get_status`. Measured over all 27 tasks: 20 `up-to-date`, 7 `run`, no
     `error`, no `ignore`.
   - Propagated status: walk the DAG from the roots and mark every task that is locally
     `up-to-date` but has a `run` ancestor. Rendered as its own marker (Design step 6) — this is
     what makes the tree honest about cascades without overclaiming, per the table in "Why".
5. **Render each task once.** The earlier draft's "render a multi-parent task in full under each
   parent, the DAG is small so the duplication is fine" does not survive contact with the real
   graph: fully expanding 27 tasks / 64 edges under every parent produces **1026 rendered nodes**
   (`fetch_huts` alone 466), because the fan-in compounds — `copy_public_data` has 12 parents,
   `snap_hubs` 6. A 1026-line "at a glance" view is not at a glance.

   Instead: walk in a deterministic topological order and expand each task **at its first
   occurrence only**; every later occurrence renders as a dim single-line back-reference
   (`build_hub_edges ↑`) with no children. That is 27 full nodes + 40 reference leaves = 67 lines,
   preserves the approved tree shape, and needs no legend beyond the `↑`. (A flat depth-layered
   listing — 27 lines, each task with its parents inline — is the obvious fallback if even 67
   lines reads as noisy; the layering computed above is clean enough that it would work well.)
6. Each node's label: task name, colored green with `✓` for up-to-date, red with `●` for run/stale,
   yellow with `~` for "up-to-date but has a stale ancestor → may rerun" (step 4), yellow with `?`
   for ignore/error (not observed in practice, but doit exposes them so the script handles them
   rather than crashing).
7. Print the assembled `Tree` via a `rich.console.Console`.

No CLI arguments in v1 — always shows the full tree. (A `--task <name>` filter to show just one
subtree is easy to add later if it turns out useful, but nothing in this design blocks it — YAGNI
for now.)

### New dependency: `rich`

Added to `pipeline/pixi.toml`'s `[dependencies]` (the conda-forge block, alongside `numpy`/`shapely`
— not `[pypi-dependencies]`, which is reserved there for what conda-forge doesn't carry: `doit`,
`pmtiles`, `pytest`, `leuvenmapmatching`). Still absent today, confirmed. Small, single-purpose
(colored tree/console rendering). Only added to the `pipeline` pixi environment, not `huts/`.

Adding it regenerates `pipeline/pixi.lock` — the implementation step is `pixi install` from
`pipeline/`, and the lockfile change is part of the commit. Worth stating because it is the one
part of this task that touches the environment every multi-hour pipeline run uses.

### New pixi task: `status`

Added to `pipeline/pixi.toml`'s `[tasks]` alongside the existing `doit` task, e.g.:
```toml
status = "python status.py"
```
so it's invoked identically to how `doit` itself is already invoked (`pixi run status`, from
`pipeline/`), no new invocation pattern to learn.

**The script must not depend on being launched from `pipeline/`.** Every `file_dep`/`targets` entry
is a path relative to `pipeline/` (`lib/doit_support.py`'s `rel()`, deliberately — see its
docstring), and `get_status` resolves those against the *process* cwd. Run from anywhere else, every
file looks missing and every task reports `run`. `pixi run` happens to use the manifest directory,
but the script should `os.chdir(Path(__file__).resolve().parent)` at startup anyway, so a bare
`python pipeline/status.py` from the repo root is correct rather than confidently wrong.

## Error handling

- Empty/missing `data/.doit.json.db` (fresh checkout, never run `doit` before):
  `dep_manager.get_status` already handles this — every task reports `'run'` (nothing recorded
  yet). No special-casing needed in `status.py`. (`JsonDB._load` treats a missing file as an empty
  DB and does not create it; combined with never dumping, a fresh checkout stays untouched.)
- `dodo.py` builds part of the DAG from the filesystem at import time — `task_match_tour_edges`
  globs `pipeline/tours/*/*.gpx` for its `file_dep`. Importing `dodo` is therefore not free of
  environment assumptions, but it is read-only and is exactly what `doit list` already does. It is
  also the reason the script must import `dodo` rather than reconstruct the task list itself.
- A task with a `task_dep` on a name that doesn't exist in `tasks_by_name` (shouldn't happen —
  doit itself would fail to load the dodo file first) — not defended against; if `dodo.py` is
  malformed, the existing `doit list`/`doit run` already fail the same way, so this script failing
  identically is consistent, not a regression.

## Testing

- Manual: run `pixi run status` from `pipeline/` and confirm colors/structure against
  `doit list --status`. Expected against the state measured while writing this revision (2026-09-01,
  27 tasks): 7 red — `build_profiles`, `gather_route_subgraphs`, `build_hub_edges`,
  `build_approach_table`, `build_tour_edge_tiles`, `build_tour_edge_payload`, `copy_public_data` —
  and the rest green *except* for the `~` propagated marker, which must appear on at least
  `build_edge_payload` and `build_edge_ids` (locally up-to-date, downstream of a red
  `build_hub_edges`). Note the earlier draft's expectation "`build_profiles` green/up-to-date" is
  wrong: it currently reports `run`. Roots must be exactly `download_extracts`, `fetch_dem`,
  `fetch_huts` — if `merge_trails` or `build_base_graph` shows up as a root, `TaskControl` was not
  applied (Design step 3).
- **Verify the DB is untouched:** `cp data/.doit.json.db /tmp/before && pixi run status && diff -q
  /tmp/before data/.doit.json.db`. This is the one check worth running every time the script is
  changed, since a regression here corrupts multi-hour pipeline state rather than just printing
  something wrong. It passed against the prototype used to verify this design.
- No dedicated automated test for rendering — this is a read-only reporting script over doit's own
  already-tested status computation. **One small `pipeline/tests/` test is worth adding anyway:**
  build the adjacency from a hand-written 3-task fixture (A produces a target, B `file_dep`s on it,
  C `task_dep`s on B) and assert A is the only root. That pins the exact mistake this review
  caught — the graph silently degrading to a flat list if `TaskControl`'s implicit-dep pass is
  dropped or reordered — which is invisible in a screenshot of a colored tree.

## Upgrade path (not built now)

If a one-shot view later turns out insufficient (e.g. wanting to drill into why a task is stale,
or re-check status after a run without re-invoking), the natural next step is a `--watch` flag or
a `textual`-based interactive mode built on the same `tasks_by_name`/status-computation core this
script already has — noted here so a future design doesn't have to re-derive the doit-API-loading
approach from scratch.
