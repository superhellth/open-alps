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


def test_build_profiles_never_declares_the_dem():
    # spec B4: profilePoints retuning must not force a re-route or a DEM read
    deps = dodo.task_build_profiles()["file_dep"]
    assert not any("dem" in d for d in deps)
