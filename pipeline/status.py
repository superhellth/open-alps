"""Read-only status view over the pipeline's doit DAG: renders task dependency structure and
up-to-date/stale status as a colored tree, without ever executing or mutating anything doit
tracks. See docs/superpowers/specs/2026-09-01-doit-dag-status-cli-design.md.

Never calls dep_manager.close() or backend.dump() anywhere in this module - see that spec's
Non-goals section for why a stray dump could corrupt multi-hour pipeline state.
"""

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
