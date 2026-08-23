import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dodo  # noqa: E402


def test_add_elevation_task_is_gone():
    assert not hasattr(dodo, "task_add_elevation")
    assert "add_elevation" not in dodo.DOIT_CONFIG["default_tasks"]


def test_elevation_pass_sits_between_base_graph_and_hub_edges():
    ordered = dodo.DOIT_CONFIG["default_tasks"]
    assert ordered.index("build_base_graph") < ordered.index("sample_base_elevation")
    assert ordered.index("sample_base_elevation") < ordered.index("compute_edge_profiles")
    assert ordered.index("compute_edge_profiles") < ordered.index("build_hub_edges")


def test_dem_is_a_declared_file_dep_of_the_elevation_pass():
    # spec B5: today the ordering is numbering convention only
    deps = dodo.task_sample_base_elevation()["file_dep"]
    assert any(d.endswith("dem.tif") for d in deps)


def test_compute_edge_profiles_depends_on_sample_base_elevation_outputs():
    # smoothing-kernel retunes must not re-trigger a DEM resample - the two are separate tasks
    deps = dodo.task_compute_edge_profiles()["file_dep"]
    assert any(d.endswith("node_ele.npy") for d in deps)
    assert not any(d.endswith("dem.tif") for d in deps)


def test_compute_edge_profiles_tracks_speed_model_params():
    # this task reads config["graph"]["speedModel"] directly (compute_edge_profiles.py) but its
    # only tracked param used to be smoothing_kernel_m - a speedModel-only retune (e.g. Task 11's
    # v0 calibration) would leave TaskOptionsChanged() reporting "up to date" and silently skip
    # recomputing time_s under the new constants. Every value the script reads from speedModel
    # must be a declared param so TaskOptionsChanged actually sees it change.
    param_names = {p["name"] for p in dodo.task_compute_edge_profiles()["params"]}
    assert {"speed_v0", "speed_k", "speed_s0"} <= param_names


def test_build_profiles_never_declares_the_dem():
    # spec B4: profilePoints retuning must not force a re-route or a DEM read
    deps = dodo.task_build_profiles()["file_dep"]
    assert not any("dem" in d for d in deps)


def test_build_hub_edges_tracks_the_variant_grid():
    # build_hub_edges.py reads config["graph"]["variants"] directly (variants_lib.enabled_variants)
    # with no corresponding CLI flag, so without a tracked param a three-row -> four-row config
    # edit leaves TaskOptionsChanged() reporting "up to date" and silently skips the rebuild.
    param_names = {p["name"] for p in dodo.task_build_hub_edges()["params"]}
    assert "variants_json" in param_names


def test_build_base_graph_and_hub_edges_track_schema_version():
    # binfmt.SCHEMA_VERSION exists so a code-only EDGE_DTYPE/RECORD_DTYPE change (no config edit
    # at all) still changes the tracked digest and forces a rebuild instead of needing `doit
    # forget` by hand.
    for task_fn in (dodo.task_build_base_graph, dodo.task_build_hub_edges):
        param_names = {p["name"] for p in task_fn()["params"]}
        assert "schema_version" in param_names
