# doit DAG status CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Do not use
> superpowers:subagent-driven-development or any worktree/subagent-spinning approach for this
> plan** — root `CLAUDE.md` forbids it in this repo; execute tasks directly, in-session, on the
> current checkout.

**Goal:** Add `pixi run status` (from `pipeline/`) — a read-only script that renders the doit task
DAG as a colored, deduplicated tree showing each task's up-to-date/stale status, without ever
running or mutating anything doit tracks.

**Architecture:** One new script, `pipeline/status.py`, split into small pure functions (root/child
adjacency, per-task status, "may-rerun" propagation, marker selection, tree assembly) plus a thin
`main()` that wires them together and prints via `rich`. The pure functions take plain
lists/dicts of `doit.task.Task` objects and status strings, so the one adjacency invariant worth
pinning (see Task 2) can be tested with a hand-built fixture, no real dep-DB or `dodo.py` import
required.

**Tech Stack:** Python 3.11 (pixi `alpen-osm` env), `doit` (already a pypi-dependency), new
conda-forge dependency `rich` for tree/color rendering.

**Spec:** `docs/superpowers/specs/2026-09-01-doit-dag-status-cli-design.md`

## Global Constraints

- **Never call `dep_manager.close()` or `backend.dump()`, anywhere in `status.py`.** `JsonDB` has
  no `__del__`; with no explicit dump the file is only ever read. `get_status` mutates in-memory
  state (deletes a task's recorded results if the checker class differs from the last run) — a
  stray dump would silently destroy state a multi-hour run depends on. (Spec Non-goals.)
- **Read `dep_file`/`backend` from `loader.load_doit_config()`, never hardcode `.doit.db` or
  `.doit.json.db`.** Both files exist on disk; hardcoding the wrong one reports a plausible-looking
  status from a stale database with no loud failure. (Spec Design step 2.)
- **The script must not depend on being launched from `pipeline/`** — `os.chdir` to the script's
  own directory at the top of `main()`, before importing `dodo` or touching the dep manager. Every
  `file_dep`/`targets` path is `pipeline/`-relative and resolved against the process cwd. (Spec
  "New pixi task: status".)
- **No CLI arguments in v1** — always render the full tree. (Spec Design, closing line.)
- **No `doit-graph`/Graphviz, no interactivity/drill-down** — terminal tree output only. (Spec
  Non-goals.)
- `rich` goes in `pipeline/pixi.toml`'s `[dependencies]` (conda-forge), not
  `[pypi-dependencies]`. (Spec "New dependency: rich".)

---

## Task 1: Add the `rich` dependency and `status` pixi task

**Files:**
- Modify: `pipeline/pixi.toml`

**Interfaces:**
- Produces: `rich` importable inside the `alpen-osm` pixi env; `pixi run status` invokable (will
  fail until Task 3 creates `status.py` — that's expected and checked at the end of this task).

- [ ] **Step 1: Add `rich` to `[dependencies]`**

Edit `pipeline/pixi.toml`'s `[dependencies]` block (alongside `numpy`/`shapely`, not
`[pypi-dependencies]`):

```toml
[dependencies]
python = "3.11.*"
osmium-tool = "*"
pyosmium = "*"
scipy = "*"
numpy = "*"
python-igraph = "*"
gdal = "*"
rasterio = "*"
orjson = "*"
psutil = "*"
shapely = "*"
tippecanoe = "*"
pip = "*"
rtree = ">=1.4.1,<2"
rich = "*"
```

- [ ] **Step 2: Add the `status` task**

Edit `pipeline/pixi.toml`'s `[tasks]` block:

```toml
[tasks]
doit = "doit"
test = "pytest"
status = "python status.py"
```

- [ ] **Step 3: Regenerate the lockfile**

Run: `cd pipeline && pixi install`

This updates `pipeline/pixi.lock` to include `rich` and its transitive deps. The lockfile diff is
part of this task's commit.

- [ ] **Step 4: Verify `rich` imports in the env**

Run: `cd pipeline && pixi run python -c "import rich; print(rich.__version__)"`
Expected: prints a version string, no `ModuleNotFoundError`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/pixi.toml pipeline/pixi.lock
git commit -m "$(cat <<'EOF'
build(pipeline): add rich dependency and status pixi task

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSiy9D7gGYdGCoorzewPVZ
EOF
)"
```

---

## Task 2: `status.py` adjacency core (`compute_roots`, `build_children_map`) + fixture test

This is the one piece of the design with a real correctness trap (spec's "Why" and Design step 3):
reading `task.task_dep` before `TaskControl` has run under-counts edges and produces a near-flat
tree. Pin that with a hand-built fixture before writing anything else.

**Files:**
- Create: `pipeline/status.py`
- Test: `pipeline/tests/test_status.py`

**Interfaces:**
- Produces:
  - `compute_roots(tasks: list[Task]) -> list[str]` — sorted names of tasks with empty
    `task_dep`, valid only *after* `TaskControl(tasks)` has resolved implicit file_dep edges.
  - `build_children_map(tasks: list[Task]) -> dict[str, list[str]]` — reverse of `task_dep`:
    `children[x]` is the sorted list of task names that list `x` in their (already-resolved)
    `task_dep`.
- Consumes: `doit.task.Task`, `doit.control.TaskControl` (pypi `doit`, already a dependency).

- [ ] **Step 1: Write the failing test**

Create `pipeline/tests/test_status.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from doit.control import TaskControl
from doit.task import Task

import status  # noqa: E402


def test_task_control_collapses_file_dep_chain_to_a_single_root():
    # A produces a target, B file_deps on it (implicit edge, only visible after TaskControl),
    # C task_deps on B directly. Pins the exact failure mode the design's review caught: reading
    # task_dep before TaskControl runs would see A and C as two separate roots.
    task_a = Task("task_a", actions=[], targets=["a_output.txt"])
    task_b = Task("task_b", actions=[], file_dep=["a_output.txt"])
    task_c = Task("task_c", actions=[], task_dep=["task_b"])
    tasks = [task_a, task_b, task_c]

    TaskControl(tasks)  # mutates task_b.task_dep to include task_a, in place

    assert status.compute_roots(tasks) == ["task_a"]

    children = status.build_children_map(tasks)
    assert children["task_a"] == ["task_b"]
    assert children["task_b"] == ["task_c"]
    assert children["task_c"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pipeline && pixi run pytest tests/test_status.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'status'` (file doesn't exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `pipeline/status.py`:

```python
"""Read-only status view over the pipeline's doit DAG: renders task dependency structure and
up-to-date/stale status as a colored tree, without ever executing or mutating anything doit
tracks. See docs/superpowers/specs/2026-09-01-doit-dag-status-cli-design.md.

Never calls dep_manager.close() or backend.dump() anywhere in this module - see that spec's
Non-goals section for why a stray dump could corrupt multi-hour pipeline state.
"""

from collections import defaultdict


def compute_roots(tasks) -> list[str]:
    """Tasks with no task_dep at all - the DAG's real sources. Only meaningful after
    TaskControl(tasks) has resolved file_dep-derived implicit edges onto task.task_dep; reading
    task_dep before that undercounts edges (see this repo's design doc's "Why" section)."""
    return sorted(t.name for t in tasks if not t.task_dep)


def build_children_map(tasks) -> dict[str, list[str]]:
    """Reverse of task_dep: children[x] is every task that lists x in its (already-resolved)
    task_dep - i.e. what renders as x's children walking the tree downward from the roots."""
    children = defaultdict(list)
    for t in tasks:
        for dep_name in t.task_dep:
            children[dep_name].append(t.name)
    for names in children.values():
        names.sort()
    return dict(children)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pipeline && pixi run pytest tests/test_status.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/status.py pipeline/tests/test_status.py
git commit -m "$(cat <<'EOF'
feat(pipeline): add doit DAG adjacency core for status CLI

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSiy9D7gGYdGCoorzewPVZ
EOF
)"
```

---

## Task 3: Status computation — local status, "may-rerun" propagation, marker selection

**Files:**
- Modify: `pipeline/status.py`

**Interfaces:**
- Consumes: `compute_roots`, `build_children_map` (Task 2, unchanged).
- Produces:
  - `compute_local_status(tasks, tasks_by_name, dep_manager) -> dict[str, str]` — per-task name to
    `'up-to-date' | 'run' | 'error' | 'ignore'`.
  - `compute_may_rerun(tasks_by_name, local_status) -> dict[str, bool]` — per-task name to whether
    it's locally up-to-date but has a `'run'`-status ancestor anywhere upstream in `task_dep`.
  - `marker_for(name, local_status, may_rerun) -> tuple[str, str]` — `(symbol, rich_color)`.

These three are exercised by the manual end-to-end check in Task 5, not unit tests — they only do
real work against `doit`'s actual status computation (`dep_manager.get_status`), which is itself
already tested by `doit`'s own test suite; a hand-rolled fixture here would just re-implement
`get_status`'s semantics. `compute_may_rerun`'s pure graph-walk logic is the same shape already
pinned by Task 2's `build_children_map` test (traverse `task_dep`/its reverse); no second fixture
needed for it. Per spec's Testing section, the whole-module correctness check is Task 5's manual
run against the real DAG.

- [ ] **Step 1: Add the status/marker functions to `status.py`**

Append to `pipeline/status.py` (after `build_children_map`):

```python
def compute_local_status(tasks, tasks_by_name, dep_manager) -> dict[str, str]:
    """status_is_ignore checked before get_status, in that order - get_status only ever returns
    'up-to-date' | 'run' | 'error'; 'ignore' is a separate query (matches doit's own
    cmd_list.py:_print_task)."""
    status_by_name = {}
    for t in tasks:
        if dep_manager.status_is_ignore(t):
            status_by_name[t.name] = "ignore"
        else:
            status_by_name[t.name] = dep_manager.get_status(t, tasks_by_name).status
    return status_by_name


def compute_may_rerun(tasks_by_name, local_status: dict[str, str]) -> dict[str, bool]:
    """True for a task that is locally up-to-date but has a 'run'-status ancestor anywhere
    upstream in task_dep - the third, honest marker this tool needs so it never renders a green
    leaf under a red parent (get_status is a purely local check; it knows nothing about an
    upstream task about to rewrite its inputs)."""
    memo: dict[str, bool] = {}

    def has_stale_ancestor(name: str) -> bool:
        if name in memo:
            return memo[name]
        memo[name] = False  # doit's task_dep graph is acyclic; this guards recursion regardless
        result = any(
            local_status[dep] == "run" or has_stale_ancestor(dep)
            for dep in tasks_by_name[name].task_dep
        )
        memo[name] = result
        return result

    return {
        name: local_status[name] == "up-to-date" and has_stale_ancestor(name)
        for name in tasks_by_name
    }


def marker_for(name: str, local_status: dict[str, str], may_rerun: dict[str, bool]) -> tuple[str, str]:
    """(symbol, rich color): up-to-date -> green check; run -> red dot; up-to-date-with-stale-
    ancestor -> yellow tilde; ignore/error -> yellow question mark."""
    task_status = local_status[name]
    if task_status == "up-to-date":
        return ("~", "yellow") if may_rerun[name] else ("✓", "green")
    if task_status == "run":
        return ("●", "red")
    return ("?", "yellow")  # ignore or error
```

- [ ] **Step 2: Run the existing test suite to confirm nothing broke**

Run: `cd pipeline && pixi run pytest tests/test_status.py -v`
Expected: PASS (unchanged from Task 2 — this step adds no new tests, just confirms the file still
imports cleanly with the new functions added).

- [ ] **Step 3: Commit**

```bash
git add pipeline/status.py
git commit -m "$(cat <<'EOF'
feat(pipeline): add doit status computation and marker selection

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSiy9D7gGYdGCoorzewPVZ
EOF
)"
```

---

## Task 4: Load the real DAG, render the tree, wire up `main()`

**Files:**
- Modify: `pipeline/status.py`

**Interfaces:**
- Consumes: `compute_roots`, `build_children_map`, `compute_local_status`, `compute_may_rerun`,
  `marker_for` (Tasks 2–3).
- Produces: `load_tasks_and_dep_manager() -> tuple[list[Task], dict[str, Task], Dependency]`,
  `render_tree(roots, children, local_status, may_rerun) -> rich.tree.Tree`, `main() -> None`.

- [ ] **Step 1: Add the doit-loading, rendering and `main()` code**

Append to `pipeline/status.py` (imports go at the top of the file — see the full updated header
below):

```python
def load_tasks_and_dep_manager():
    """Loads dodo.py's task list the same way `doit list`/`doit info` do internally
    (ModuleTaskLoader over the dodo module - see doit's own cmd_list.py), resolves the implicit
    file_dep-derived task_dep edges (TaskControl), and builds the Dependency manager from dodo.py's
    own DOIT_CONFIG rather than hardcoding a db path or backend (two dep-db files exist on disk;
    see this repo's design doc's Design step 2 for why hardcoding one silently reads the wrong
    one)."""
    sys.path.insert(0, str(SCRIPT_DIR))
    import dodo  # noqa: E402  (import deferred until sys.path/cwd are set up)

    loader = ModuleTaskLoader(dodo)
    loader.cmd_names = []  # required by ModuleTaskLoader.load_tasks; this script names no tasks
    tasks = loader.load_tasks(_FakeCmd(), [])
    TaskControl(tasks)  # mutates each task.task_dep in place - see compute_roots's docstring

    cfg = loader.load_doit_config()
    db_class = _DB_CLASSES[cfg.get("backend", "dbm")]
    dep_manager = Dependency(db_class, cfg["dep_file"], checker_cls=MD5Checker)

    tasks_by_name = {t.name: t for t in tasks}
    return tasks, tasks_by_name, dep_manager


def render_tree(roots, children, local_status, may_rerun) -> Tree:
    """Walks the DAG from `roots` in deterministic (sorted) order, expanding each task at its
    first occurrence only; every later occurrence renders as a dim single-line back-reference with
    no children. A full multi-parent expansion of this DAG renders 1026 nodes (fan-in compounds -
    copy_public_data alone has 12 parents); this walk renders each of the 27 tasks exactly once."""
    tree = Tree("pipeline")
    visited: set[str] = set()

    def add(name: str, parent: Tree) -> None:
        if name in visited:
            parent.add(f"[dim]{name} ↑[/dim]")
            return
        visited.add(name)
        symbol, color = marker_for(name, local_status, may_rerun)
        node = parent.add(f"[{color}]{symbol} {name}[/{color}]")
        for child_name in children.get(name, []):
            add(child_name, node)

    for root_name in roots:
        add(root_name, tree)
    return tree


def main() -> None:
    os.chdir(SCRIPT_DIR)  # file_dep/targets are SCRIPT_DIR-relative (lib/doit_support.py's rel())
    tasks, tasks_by_name, dep_manager = load_tasks_and_dep_manager()
    roots = compute_roots(tasks)
    local_status = compute_local_status(tasks, tasks_by_name, dep_manager)
    may_rerun = compute_may_rerun(tasks_by_name, local_status)
    children = build_children_map(tasks)
    Console().print(render_tree(roots, children, local_status, may_rerun))


if __name__ == "__main__":
    main()
```

Now replace the top of `pipeline/status.py` (the module docstring plus everything before
`compute_roots`) so the file's imports and constants match what the code above needs. The full
file, in final form, is:

```python
"""Read-only status view over the pipeline's doit DAG: renders task dependency structure and
up-to-date/stale status as a colored tree, without ever executing or mutating anything doit
tracks. See docs/superpowers/specs/2026-09-01-doit-dag-status-cli-design.md.

Never calls dep_manager.close() or backend.dump() anywhere in this module - see that spec's
Non-goals section for why a stray dump could corrupt multi-hour pipeline state.
"""

import os
import sys
from collections import defaultdict
from pathlib import Path

from doit.cmd_base import ModuleTaskLoader
from doit.control import TaskControl
from doit.dependency import Dependency, DbmDB, JsonDB, MD5Checker, SqliteDB
from rich.console import Console
from rich.tree import Tree

SCRIPT_DIR = Path(__file__).resolve().parent
_DB_CLASSES = {"dbm": DbmDB, "json": JsonDB, "sqlite3": SqliteDB}


class _FakeCmd:
    """Stand-in for doit's own Cmd object - ModuleTaskLoader.load_tasks() only reads
    cmd.execute_tasks off whatever it's given (doit/cmd_base.py), never calls any of its
    methods."""

    execute_tasks = False


def compute_roots(tasks) -> list[str]:
    """Tasks with no task_dep at all - the DAG's real sources. Only meaningful after
    TaskControl(tasks) has resolved file_dep-derived implicit edges onto task.task_dep; reading
    task_dep before that undercounts edges (see this repo's design doc's "Why" section)."""
    return sorted(t.name for t in tasks if not t.task_dep)


def build_children_map(tasks) -> dict[str, list[str]]:
    """Reverse of task_dep: children[x] is every task that lists x in its (already-resolved)
    task_dep - i.e. what renders as x's children walking the tree downward from the roots."""
    children = defaultdict(list)
    for t in tasks:
        for dep_name in t.task_dep:
            children[dep_name].append(t.name)
    for names in children.values():
        names.sort()
    return dict(children)


def compute_local_status(tasks, tasks_by_name, dep_manager) -> dict[str, str]:
    """status_is_ignore checked before get_status, in that order - get_status only ever returns
    'up-to-date' | 'run' | 'error'; 'ignore' is a separate query (matches doit's own
    cmd_list.py:_print_task)."""
    status_by_name = {}
    for t in tasks:
        if dep_manager.status_is_ignore(t):
            status_by_name[t.name] = "ignore"
        else:
            status_by_name[t.name] = dep_manager.get_status(t, tasks_by_name).status
    return status_by_name


def compute_may_rerun(tasks_by_name, local_status: dict[str, str]) -> dict[str, bool]:
    """True for a task that is locally up-to-date but has a 'run'-status ancestor anywhere
    upstream in task_dep - the third, honest marker this tool needs so it never renders a green
    leaf under a red parent (get_status is a purely local check; it knows nothing about an
    upstream task about to rewrite its inputs)."""
    memo: dict[str, bool] = {}

    def has_stale_ancestor(name: str) -> bool:
        if name in memo:
            return memo[name]
        memo[name] = False  # doit's task_dep graph is acyclic; this guards recursion regardless
        result = any(
            local_status[dep] == "run" or has_stale_ancestor(dep)
            for dep in tasks_by_name[name].task_dep
        )
        memo[name] = result
        return result

    return {
        name: local_status[name] == "up-to-date" and has_stale_ancestor(name)
        for name in tasks_by_name
    }


def marker_for(name: str, local_status: dict[str, str], may_rerun: dict[str, bool]) -> tuple[str, str]:
    """(symbol, rich color): up-to-date -> green check; run -> red dot; up-to-date-with-stale-
    ancestor -> yellow tilde; ignore/error -> yellow question mark."""
    task_status = local_status[name]
    if task_status == "up-to-date":
        return ("~", "yellow") if may_rerun[name] else ("✓", "green")
    if task_status == "run":
        return ("●", "red")
    return ("?", "yellow")  # ignore or error


def load_tasks_and_dep_manager():
    """Loads dodo.py's task list the same way `doit list`/`doit info` do internally
    (ModuleTaskLoader over the dodo module - see doit's own cmd_list.py), resolves the implicit
    file_dep-derived task_dep edges (TaskControl), and builds the Dependency manager from dodo.py's
    own DOIT_CONFIG rather than hardcoding a db path or backend (two dep-db files exist on disk;
    see this repo's design doc's Design step 2 for why hardcoding one silently reads the wrong
    one)."""
    sys.path.insert(0, str(SCRIPT_DIR))
    import dodo  # noqa: E402  (import deferred until sys.path/cwd are set up)

    loader = ModuleTaskLoader(dodo)
    loader.cmd_names = []  # required by ModuleTaskLoader.load_tasks; this script names no tasks
    tasks = loader.load_tasks(_FakeCmd(), [])
    TaskControl(tasks)  # mutates each task.task_dep in place - see compute_roots's docstring

    cfg = loader.load_doit_config()
    db_class = _DB_CLASSES[cfg.get("backend", "dbm")]
    dep_manager = Dependency(db_class, cfg["dep_file"], checker_cls=MD5Checker)

    tasks_by_name = {t.name: t for t in tasks}
    return tasks, tasks_by_name, dep_manager


def render_tree(roots, children, local_status, may_rerun) -> Tree:
    """Walks the DAG from `roots` in deterministic (sorted) order, expanding each task at its
    first occurrence only; every later occurrence renders as a dim single-line back-reference with
    no children. A full multi-parent expansion of this DAG renders 1026 nodes (fan-in compounds -
    copy_public_data alone has 12 parents); this walk renders each of the 27 tasks exactly once."""
    tree = Tree("pipeline")
    visited: set[str] = set()

    def add(name: str, parent: Tree) -> None:
        if name in visited:
            parent.add(f"[dim]{name} ↑[/dim]")
            return
        visited.add(name)
        symbol, color = marker_for(name, local_status, may_rerun)
        node = parent.add(f"[{color}]{symbol} {name}[/{color}]")
        for child_name in children.get(name, []):
            add(child_name, node)

    for root_name in roots:
        add(root_name, tree)
    return tree


def main() -> None:
    os.chdir(SCRIPT_DIR)  # file_dep/targets are SCRIPT_DIR-relative (lib/doit_support.py's rel())
    tasks, tasks_by_name, dep_manager = load_tasks_and_dep_manager()
    roots = compute_roots(tasks)
    local_status = compute_local_status(tasks, tasks_by_name, dep_manager)
    may_rerun = compute_may_rerun(tasks_by_name, local_status)
    children = build_children_map(tasks)
    Console().print(render_tree(roots, children, local_status, may_rerun))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the test suite**

Run: `cd pipeline && pixi run pytest tests/test_status.py -v`
Expected: PASS (Task 2's fixture test is unaffected by these additions).

- [ ] **Step 3: Commit**

```bash
git add pipeline/status.py
git commit -m "$(cat <<'EOF'
feat(pipeline): render doit DAG status tree in status.py main()

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSiy9D7gGYdGCoorzewPVZ
EOF
)"
```

---

## Task 5: Manual verification against the real DAG + dep-DB safety check

Per the spec's Testing section, this is the load-bearing check for the whole tool — no automated
test replaces running it against the actual `data/.doit.json.db`. Do not skip any step.

**Files:** none (verification only).

- [ ] **Step 1: Snapshot the dep DB before running**

Run: `cp data/.doit.json.db /tmp/before_status_db` (from repo root; adjust path if
`data/.doit.json.db` doesn't exist yet — see Step 4 for that case).

- [ ] **Step 2: Run the tool**

Run: `cd pipeline && pixi run status`

- [ ] **Step 3: Confirm the dep DB is byte-identical afterward**

Run: `diff -q /tmp/before_status_db data/.doit.json.db` (from repo root)
Expected: no output (files identical). If this reports a difference, stop — do not commit — and
re-check that `status.py` never calls `dep_manager.close()`/`.dump()`/any mutating method; this is
the one regression that would corrupt multi-hour pipeline state.

- [ ] **Step 4: Confirm the rendered tree's shape**

Visually confirm against `pixi run doit list --status` (run from `pipeline/`, this is read-only
too):
- Roots are exactly `download_extracts`, `fetch_dem`, `fetch_huts` (if `merge_trails` or
  `build_base_graph` appears as a root, `TaskControl(tasks)` isn't being applied — re-check Task 4
  Step 1's `load_tasks_and_dep_manager`).
- Every task name from `doit list --status` appears exactly once in the tree, either as a full
  colored node or as a dim `name ↑` back-reference — 27 full nodes total.
- Colors/markers agree with `doit list --status`'s `R`/`U`/`I` letters: green `✓` for `U`, red `●`
  for `R`, with the exception that a `U` task downstream of an `R` task instead renders yellow `~`
  (this is the intentional "may rerun" marker — it is not a mismatch).

(The specific task names expected `run`/`~` in the spec's Testing section — `build_profiles`,
`gather_route_subgraphs`, `build_hub_edges`, `build_approach_table`, `build_tour_edge_tiles`,
`build_tour_edge_payload`, `copy_public_data` red; `build_edge_payload`, `build_edge_ids` at least
among the yellow `~` — are a snapshot from 2026-09-01 and will drift as the pipeline is rerun; use
them only as a sanity check if today's dep DB happens to match, not as a hard requirement.)

- [ ] **Step 5: Confirm cwd-independence**

Run from the repo root (not `pipeline/`): `python pipeline/status.py`
Expected: same tree as Step 2, not a wall of `run` statuses (which would indicate the `os.chdir`
in `main()` isn't taking effect before path resolution).

No commit for this task — it's verification only, folded into the next task's commit if any
follow-up fix is needed. If Step 3 or Step 5 fails, fix `status.py` and re-run this entire task
before proceeding.

---

## Self-Review Notes

- **Spec coverage:** Design steps 1–2 → Task 4 (`load_tasks_and_dep_manager`); step 3 → Task 2
  (`compute_roots`/`build_children_map` + `TaskControl` fixture test); step 4 → Task 3
  (`compute_local_status`/`compute_may_rerun`); step 5 → Task 4 (`render_tree`); step 6 → Task 3
  (`marker_for`); step 7 → Task 4 (`main`'s `Console().print`). "New dependency: rich" and "New
  pixi task: status" → Task 1. Error-handling section needs no dedicated task — every case
  described (missing dep DB, `dodo.py`'s filesystem globs, a malformed `task_dep` name) is already
  handled by `get_status`/`dodo` import/doit itself, per the spec's own reasoning; nothing to add.
  Testing section → Task 5 (manual + DB-diff) and Task 2 (adjacency fixture). Upgrade path is
  explicitly "not built now" — no task.
- **Placeholder scan:** no TBD/TODO markers; every step has literal code or an exact shell command.
- **Type consistency:** `compute_roots`, `build_children_map`, `compute_local_status`,
  `compute_may_rerun`, `marker_for`, `load_tasks_and_dep_manager`, `render_tree` are each defined
  once (Tasks 2–4) and called with the same names/signatures throughout; Task 4's "full file"
  listing is the single source of truth and supersedes the incremental snippets shown in Tasks
  2–4's earlier steps (executors should end up with the Task 4 "final form" content regardless of
  whether they apply the incremental diffs or the full-file replacement literally).
