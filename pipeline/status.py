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
    task_dep - i.e. what renders as x's children walking the tree downward from the roots. Every
    task name is present as a key (leaves map to []), not just names that appear as someone
    else's dep."""
    children: dict[str, list[str]] = {t.name: [] for t in tasks}
    for t in tasks:
        for dep_name in t.task_dep:
            children[dep_name].append(t.name)
    for names in children.values():
        names.sort()
    return children


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
