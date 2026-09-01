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
