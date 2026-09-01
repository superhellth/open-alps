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
