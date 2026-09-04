import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.doit_support import (  # noqa: E402
    TaskOptionsChanged, cli_param, pipeline_task, py, rel, tracking_param,
)
from lib.pipeline import SCRIPTS_DIR  # noqa: E402


def test_rel_returns_forward_slash_path_relative_to_scripts_dir():
    target = SCRIPTS_DIR / "phases" / "downloads" / "fetch_huts.py"
    assert rel(target) == "phases/downloads/fetch_huts.py"


def test_py_quotes_interpreter_and_script_path():
    cmd = py("phases/downloads/fetch_huts.py", "--foo", "bar")
    assert cmd.startswith('"')
    assert "fetch_huts.py" in cmd
    assert cmd.endswith("--foo bar")


def test_cli_param_shape():
    p = cli_param("max_edge_km", "max-edge-km", float, 30)
    assert p == {"name": "max_edge_km", "long": "max-edge-km", "type": float, "default": 30}


def test_tracking_param_derives_long_flag_from_name():
    p = tracking_param("smoothing_kernel_m", float, 30)
    assert p["long"] == "smoothing-kernel-m"


def test_pipeline_task_builds_action_with_param_flags():
    task = pipeline_task(
        "phases/graph_building/build_hub_edges.py",
        params=[cli_param("max_edge_km", "max-edge-km", float, 30)],
        file_dep=[SCRIPTS_DIR / "pipeline.config.json"],
        targets=[SCRIPTS_DIR.parent / "data" / "osm" / "hut_edges" / "records.npy"],
    )
    assert "--max-edge-km %(max_edge_km)s" in task["actions"][0]
    assert task["file_dep"] == ["pipeline.config.json"]
    assert "uptodate" in task
    assert isinstance(task["uptodate"][0], TaskOptionsChanged)


def test_pipeline_task_omits_uptodate_when_no_params():
    task = pipeline_task("phases/preprocessing/merge_trails.py")
    assert "uptodate" not in task
    assert "params" not in task


def test_pipeline_task_tracking_params_not_interpolated_into_action():
    task = pipeline_task(
        "phases/elevation/compute_edge_profiles.py",
        tracking_params=[tracking_param("speed_v0", float, 4.013)],
    )
    assert "speed-v0" not in task["actions"][0]
    assert task["params"] == [tracking_param("speed_v0", float, 4.013)]


class _FakeTask:
    """Minimal duck-typed stand-in for doit's real Task: TaskOptionsChanged only touches
    .options, .init_options(), and .value_savers (see its own docstring/source)."""

    def __init__(self, options):
        self.options = options
        self.value_savers = []
        self._init_options_called = False

    def init_options(self):
        self._init_options_called = True


def test_task_options_changed_configure_task_registers_a_value_saver():
    check = TaskOptionsChanged()
    task = _FakeTask(options={"max_edge_km": 30})
    check.configure_task(task)
    assert len(task.value_savers) == 1
    saved = task.value_savers[0]()
    assert saved == {"_task_options": json.dumps({"max_edge_km": 30}, sort_keys=True)}


def test_task_options_changed_true_when_options_match_saved_digest():
    check = TaskOptionsChanged()
    task = _FakeTask(options={"max_edge_km": 30})
    values = {"_task_options": json.dumps({"max_edge_km": 30}, sort_keys=True)}
    assert check(task, values) is True
    assert task._init_options_called


def test_task_options_changed_false_when_options_differ_from_saved_digest():
    check = TaskOptionsChanged()
    task = _FakeTask(options={"max_edge_km": 45})  # changed since last run
    values = {"_task_options": json.dumps({"max_edge_km": 30}, sort_keys=True)}
    assert check(task, values) is False


def test_task_options_changed_false_when_no_saved_digest_yet():
    check = TaskOptionsChanged()
    task = _FakeTask(options={"max_edge_km": 30})
    assert check(task, {}) is False  # first-ever run: nothing saved yet, must not claim uptodate
