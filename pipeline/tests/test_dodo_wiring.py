import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dodo  # noqa: E402
from lib.doit_support import SCRIPT_DIR  # noqa: E402
from lib.pipeline import DATA_DIR  # noqa: E402


def _public_names():
    return [name for _, name in dodo.PUBLIC_FILES]


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
    assert any(d.endswith("node-ele.npy") for d in deps)
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


def test_build_base_graph_tracks_only_edge_schema_version():
    # binfmt.EDGE_SCHEMA_VERSION exists so a code-only EDGE_DTYPE change (no config edit at all)
    # still changes the tracked digest and forces a rebuild instead of needing `doit forget` by
    # hand - but a RECORD_DTYPE-only change (this task never writes RECORD_DTYPE) must not
    # force-rerun this ~4h task.
    param_names = {p["name"] for p in dodo.task_build_base_graph()["params"]}
    assert "edge_schema_version" in param_names
    assert "snap_schema_version" not in param_names
    assert "record_schema_version" not in param_names


def test_build_hub_edges_tracks_all_three_schema_versions():
    # reads EDGE_DTYPE + HUB_SNAP_DTYPE, writes RECORD_DTYPE - a code-only change to any of the
    # three must force this task to rerun.
    param_names = {p["name"] for p in dodo.task_build_hub_edges()["params"]}
    assert {"edge_schema_version", "snap_schema_version", "record_schema_version"} <= param_names


def test_snap_hubs_tracks_only_snap_schema_version():
    param_names = {p["name"] for p in dodo.task_snap_hubs()["params"]}
    assert "snap_schema_version" in param_names
    assert "edge_schema_version" not in param_names
    assert "record_schema_version" not in param_names


def test_gather_route_subgraphs_tracks_only_edge_schema_version():
    param_names = {p["name"] for p in dodo.task_gather_route_subgraphs()["params"]}
    assert "edge_schema_version" in param_names
    assert "snap_schema_version" not in param_names
    assert "record_schema_version" not in param_names


def test_snap_hubs_and_gather_route_subgraphs_sit_between_compute_edge_profiles_and_build_hub_edges():
    # docs/superpowers/plans/2026-08-23-split-build-hub-edges.md: build_hub_edges.py's old
    # snapping/gather work was split into two upstream tasks so a --max-edge-km-only or
    # graph.variants-only retune doesn't repeat work that doesn't depend on it.
    ordered = dodo.DOIT_CONFIG["default_tasks"]
    assert ordered.index("compute_edge_profiles") < ordered.index("snap_hubs")
    assert ordered.index("compute_edge_profiles") < ordered.index("gather_route_subgraphs")
    assert ordered.index("snap_hubs") < ordered.index("build_hub_edges")
    assert ordered.index("gather_route_subgraphs") < ordered.index("build_hub_edges")


def test_snap_params_moved_off_build_hub_edges_onto_snap_hubs():
    # max_snap_m/max_snap_ascent_m only affect snapping (lib/hub_snap.py), not routing - after the
    # split they must be snap_hubs' params, not build_hub_edges', or TaskOptionsChanged() would
    # only invalidate the wrong (or an extra) task on a snap-only retune.
    hub_edges_params = {p["name"] for p in dodo.task_build_hub_edges()["params"]}
    snap_hubs_params = {p["name"] for p in dodo.task_snap_hubs()["params"]}
    assert "max_snap_m" not in hub_edges_params
    assert "max_snap_ascent_m" not in hub_edges_params
    assert {"max_snap_m", "max_snap_ascent_m"} <= snap_hubs_params


def test_gather_route_subgraphs_tracks_max_edge_km_not_variants():
    # the gather itself doesn't depend on graph.variants (only build_hub_edges' routing loop does)
    # - see gather_route_subgraphs.py's module docstring.
    params = {p["name"] for p in dodo.task_gather_route_subgraphs()["params"]}
    assert "max_edge_km" in params
    assert "variants_json" not in params


def test_build_hub_edges_depends_on_both_split_out_tasks():
    task_deps = dodo.task_build_hub_edges()["task_dep"]
    assert "snap_hubs" in task_deps
    assert "gather_route_subgraphs" in task_deps


def test_build_base_graph_tracks_road_highway_tags():
    # build_base_graph.py reads config["graph"]["roadHighwayTags"] (WayGraphHandler's is_road
    # classification) directly, with no CLI flag - without a tracked param the edit would leave
    # TaskOptionsChanged() reporting "up to date" and silently skip the multi-hour rebuild.
    param_names = {p["name"] for p in dodo.task_build_base_graph()["params"]}
    assert "road_highway_tags_json" in param_names
    assert "bbox_json" not in param_names
    assert dodo.task_build_base_graph()["uptodate"]


def test_build_approach_table_tracks_duration_buckets_and_variants_and_is_not_hardcoded_into_the_action():
    # config["approach"]["durationBucketsH"]/["variants"] used to be baked straight into the
    # action's f-string with no params/uptodate at all - doit's up-to-date check never diffs the
    # action string (only file_dep hashes and declared uptodate checks), so a retune silently
    # never reran this.
    task = dodo.task_build_approach_table()
    assert {"duration_buckets_h", "variants"} <= {p["name"] for p in task["params"]}
    assert task["uptodate"]
    assert any("%(duration_buckets_h)s" in action for action in task["actions"])
    assert any("%(variants)s" in action for action in task["actions"])


def test_edge_tile_tasks_track_zoom_and_hover_tolerance():
    # config["hutEdgeTiles"]/config["trailTiles"] used to be baked straight into each action's
    # f-string with no params/uptodate at all - same doit gap as build_approach_table's --k.
    for task_fn in (dodo.task_build_hut_edge_tiles, dodo.task_build_start_edge_tiles):
        task = task_fn()
        param_names = {p["name"] for p in task["params"]}
        assert {"min_zoom", "max_zoom", "simplify_tolerance_deg"} <= param_names
        assert task["uptodate"]

    trail_task = dodo.task_build_trail_tiles()
    trail_param_names = {p["name"] for p in trail_task["params"]}
    assert {"min_zoom", "max_zoom"} <= trail_param_names
    assert trail_task["uptodate"]


def test_build_edge_ids_task_depends_on_hut_edges_records_and_ids():
    task = dodo.task_build_edge_ids()
    file_deps = set(task["file_dep"])
    assert any("hut-edges/records.npy" in p for p in file_deps)
    assert any("hut-edges/edge-ids.npy" in p for p in file_deps)
    targets = set(task["targets"])
    assert any(p.endswith("hut-edges/ids.bin") for p in targets)
    assert any(p.endswith("hut-edges/ids.json") for p in targets)


def test_public_files_includes_hut_edge_ids():
    assert "hut-edge-ids.bin" in _public_names()
    assert "hut-edge-ids.json" in _public_names()


def test_build_start_edge_ids_task_depends_on_start_edges_records_and_ids():
    task = dodo.task_build_start_edge_ids()
    file_deps = set(task["file_dep"])
    assert any("start-edges/records.npy" in p for p in file_deps)
    assert any("start-edges/edge-ids.npy" in p for p in file_deps)
    targets = set(task["targets"])
    assert any(p.endswith("start-edges/ids.bin") for p in targets)
    assert any(p.endswith("start-edges/ids.json") for p in targets)


def test_public_files_includes_start_edge_ids():
    assert "start-edge-ids.bin" in _public_names()
    assert "start-edge-ids.json" in _public_names()


def test_build_start_edge_ids_sits_after_build_access_edges():
    ordered = dodo.DOIT_CONFIG["default_tasks"]
    assert ordered.index("build_access_edges") < ordered.index("build_start_edge_ids")


def test_fetch_huts_targets_include_partner_betriebe():
    targets = dodo.task_fetch_huts()["targets"]
    assert any(t.endswith("partner_betriebe.geojson") for t in targets)


def test_filter_start_points_depends_on_partner_betriebe():
    deps = dodo.task_filter_start_points()["file_dep"]
    assert any(d.endswith("partner_betriebe.geojson") for d in deps)




def test_match_tour_edges_tracks_tour_gpx_files():
    task = dodo.task_match_tour_edges()
    file_deps = [str(d) for d in task["file_dep"]]
    assert any(d.endswith(".gpx") for d in file_deps)







GRAPH_TASKS = {"build_base_graph", "snap_hubs", "compute_edge_profiles", "sample_base_elevation",
               "gather_route_subgraphs", "build_hub_edges", "build_access_edges", "build_profiles"}


def test_match_tour_edges_has_no_base_graph_task_dependency():
    task = dodo.task_match_tour_edges()
    assert not (GRAPH_TASKS & set(task.get("task_dep", [])))
    assert not any(str(d).endswith(("base-graph/nodes.npy", "hub-snaps.npy", "edges.npy"))
                   for d in task["file_dep"])


def test_match_tour_edges_declares_dem_huts_and_start_points():
    deps = [str(d) for d in dodo.task_match_tour_edges()["file_dep"]]
    for name in ("dem.tif", "huts.geojson", "start-points.npy"):
        assert any(d.endswith(name) for d in deps), name


def test_match_tour_edges_targets_include_profiles_and_hubs_json():
    targets = [str(t) for t in dodo.task_match_tour_edges()["targets"]]
    assert sorted(os.path.basename(t) for t in targets) == sorted(
        ["records.npy", "geometry.npy", "profiles.npy",
         "tours.json", "tour-match-gaps.json", "hubs.json"])
    assert all("build/tour-edges/" in t for t in targets)


def test_match_tour_edges_tracks_only_its_own_schema_version():
    names = {p["name"] for p in dodo.task_match_tour_edges().get("params", [])}
    assert "tour_leg_schema_version" in names
    assert not names & {"record_schema_version", "edge_schema_version", "snap_schema_version"}
    assert {"max_snap_m", "smoothing_kernel_m", "min_slope_segment_m", "profile_points",
            "speed_v0", "speed_k", "speed_s0", "min_speed_ms"} <= names


def test_build_profiles_no_longer_owns_tour_edges():
    task = dodo.task_build_profiles()
    assert "match_tour_edges" not in task["task_dep"]
    assert not any("tour_edges" in str(x) for x in (*task["file_dep"], *task["targets"]))







def test_public_files_includes_every_tour_output():
    for name in [
        "tours.json", "tour-edges.pmtiles", "tour-edge-stats.json",
        "tour-edge-geometry.bin", "tour-edge-geometry.json",
    ]:
        assert name in _public_names(), name


def test_public_files_does_not_include_tour_match_gaps():
    # gap reports are data-quality only; tours.json ships complete tours.
    assert "tour-match-gaps.json" not in _public_names()


def test_public_files_does_not_include_internal_tour_traces():
    # tour_traces.json is the ~3.5MB raw fragment file (spec §1) - internal only, never shipped.
    assert "tour_traces.json" not in _public_names()


def test_default_tasks_includes_the_new_tour_tasks_in_dag_order():
    ordered = dodo.DOIT_CONFIG["default_tasks"]
    for name in ["match_tour_edges", "build_tour_edge_tiles"]:
        assert name in ordered, name
    assert "fetch_tours" not in ordered
    assert "fetch_tour_oa_geometry" not in ordered
    assert ordered.index("match_tour_edges") < ordered.index("build_tour_edge_tiles")


def test_compute_edge_profiles_is_gated_only_by_the_stamp_build_base_graph_deletes():
    # The stamp is the ONLY thing that can re-trigger this task after a base-graph rebuild:
    # edges.npy (the file it rewrites in place) can't be a file_dep - the rewrite would make it
    # dirty on every check and rerun forever - and its real file_deps (node-ele.npy /
    # interior_ele.npy) survive a rebuild untouched. So build_base_graph.pack_and_write unlinks
    # edge-profiles.stamp, and this task must keep it as a target for that to mean anything.
    task = dodo.task_compute_edge_profiles()
    assert any(str(t).endswith("edge-profiles.stamp") for t in task["targets"])
    assert not any(str(d).endswith("edges.npy") for d in task["file_dep"])


def test_check_preprocessing_depends_on_filter_start_points_output():
    task = dodo.task_check_preprocessing()
    assert "filter_start_points" in task["task_dep"]
    assert any(d.endswith("start-points.npy") for d in task["file_dep"])
    assert any(d.endswith("start-points-id-table.json") for d in task["file_dep"])
    assert any(t.endswith("data/quality/preprocessing.json") for t in task["targets"])


def test_check_elevation_depends_on_compute_edge_profiles_and_build_profiles():
    task = dodo.task_check_elevation()
    assert "compute_edge_profiles" in task["task_dep"]
    assert "build_profiles" in task["task_dep"]
    assert any(t.endswith("data/quality/elevation.json") for t in task["targets"])


def test_check_graph_building_depends_on_hub_edge_tasks_not_tour_matching():
    task = dodo.task_check_graph_building()
    assert "match_tour_edges" not in task["task_dep"]
    assert "build_hub_edges" in task["task_dep"]
    assert "build_access_edges" in task["task_dep"]
    assert any(t.endswith("data/quality/graph_building.json") for t in task["targets"])


def test_quality_tasks_are_not_file_deps_of_copy_public_data():
    # spec §3: non-blocking - nothing in copy_public_data's file_dep may come from data/quality/.
    copy_task = dodo.task_copy_public_data()
    assert not any("quality" in d for d in copy_task["file_dep"])


def test_quality_check_tasks_exit_zero_scripts_are_wired_not_hardcoded():
    # every quality task's action must invoke its own phases/quality/check_*.py script, not a
    # hand-copied inline command.
    assert "check_preprocessing.py" in dodo.task_check_preprocessing()["actions"][0]
    assert "check_elevation.py" in dodo.task_check_elevation()["actions"][0]
    assert "check_graph_building.py" in dodo.task_check_graph_building()["actions"][0]


def test_check_postprocessing_depends_on_approach_table_and_edge_payloads():
    task = dodo.task_check_postprocessing()
    assert "build_approach_table" in task["task_dep"]
    assert "build_edge_payload" in task["task_dep"]
    assert "build_hut_edge_tiles" in task["task_dep"]
    # freshness (§4.4.4) reads huts/public/data/, so this task must run AFTER copy_public_data -
    # not circular, since copy_public_data has no dependency back on this task.
    assert "copy_public_data" in task["task_dep"]
    assert any(t.endswith("data/quality/postprocessing.json") for t in task["targets"])


def test_check_postprocessing_is_not_a_file_dep_of_copy_public_data():
    copy_task = dodo.task_copy_public_data()
    postprocessing_targets = set(dodo.task_check_postprocessing()["targets"])
    assert not (postprocessing_targets & set(copy_task["file_dep"]))


def test_quality_summary_depends_on_all_four_check_reports():
    task = dodo.task_quality_summary()
    for phase_name in ["check_preprocessing", "check_elevation", "check_graph_building",
                       "check_postprocessing"]:
        assert phase_name in task["task_dep"]
    assert any(t.endswith("data/quality/summary.json") for t in task["targets"])


def test_quality_summary_is_not_a_file_dep_of_copy_public_data():
    copy_task = dodo.task_copy_public_data()
    assert not any("quality" in d for d in copy_task["file_dep"])


def test_default_tasks_ends_with_quality_summary():
    assert dodo.DOIT_CONFIG["default_tasks"][-1] == "quality_summary"


def test_no_quality_task_is_hardcoded_into_copy_public_data_public_files():
    # data/quality/ reports are internal diagnostics, never shipped to the client.
    assert not any("quality" in name for name in _public_names())


def test_build_tour_edge_tiles_depends_on_match_tour_edges_only():
    task = dodo.task_build_tour_edge_tiles()
    assert "match_tour_edges" in task["task_dep"]
    assert "build_profiles" not in task["task_dep"]
    assert any(str(d).endswith("tour-edges/records.npy") for d in task["file_dep"])
    assert any(str(d).endswith("start-points-id-table.json") for d in task["file_dep"])
    assert any("build_tour_tiles.py" in a for a in task["actions"])
    assert not any("simplify" in a for a in task["actions"])
    assert not any(p["name"].startswith("simplify") for p in task.get("params", []))


def test_no_tour_edge_payload_task_or_public_file():
    assert not hasattr(dodo, "task_build_tour_edge_payload")
    assert "tour-edge-payload.bin" not in _public_names()
    assert "tour-edge-payload.json" not in _public_names()
    assert "build_tour_edge_payload" not in dodo.DOIT_CONFIG["default_tasks"]


def test_check_tour_matching_depends_only_on_tour_outputs():
    task = dodo.task_check_tour_matching()
    assert task["task_dep"] == ["match_tour_edges"]
    assert not any("base_graph" in str(d) for d in task["file_dep"])


def test_graph_and_elevation_checks_no_longer_read_tour_outputs():
    for name in ("task_check_graph_building", "task_check_elevation"):
        task = getattr(dodo, name)()
        assert "match_tour_edges" not in task["task_dep"]
        assert not any("tour" in str(d) for d in task["file_dep"]), name


def test_check_postprocessing_reads_tours_json_not_tour_payload():
    task = dodo.task_check_postprocessing()
    assert "build_tour_edge_payload" not in task["task_dep"]
    assert any(str(d).endswith("tours.json") for d in task["file_dep"])
    assert not any("tour-edge-payload" in str(d) for d in task["file_dep"])


def _declared_data_paths():
    """Every data/ path any default task declares as file_dep or target, relative to data/."""
    paths = set()
    for name in dodo.DOIT_CONFIG["default_tasks"]:
        task = getattr(dodo, f"task_{name}")()
        for entry in [*task.get("file_dep", []), *task.get("targets", [])]:
            resolved = (SCRIPT_DIR / entry).resolve() if not os.path.isabs(entry) else Path(entry)
            try:
                paths.add(resolved.relative_to(DATA_DIR).as_posix())
            except ValueError:
                pass  # tours/*.gpx and huts/public/data/ are not under data/
    return paths


def test_no_task_declares_a_path_in_the_old_layout():
    for p in _declared_data_paths():
        assert not p.startswith(("osm/", "dem/")), p


def test_declared_data_paths_are_under_a_known_tier():
    for p in _declared_data_paths():
        assert p.startswith(("raw/", "build/", "quality/")), p


def test_public_files_are_source_and_public_name_pairs():
    assert len(dodo.PUBLIC_FILES) == 32
    names = [name for _, name in dodo.PUBLIC_FILES]
    assert len(names) == len(set(names))
    for src, name in dodo.PUBLIC_FILES:
        rel = Path(src).resolve().relative_to(DATA_DIR).as_posix()
        assert rel.startswith(("raw/", "build/")), rel
    by_name = {name: Path(src).resolve().relative_to(DATA_DIR).as_posix()
               for src, name in dodo.PUBLIC_FILES}
    assert by_name["hut-edges.pmtiles"] == "build/hut-edges/edges.pmtiles"
    assert by_name["unsnapped_huts.json"] == "build/snapping/unsnapped-huts.json"
    assert by_name["huts.geojson"] == "raw/huts.geojson"
    assert by_name["approaches.bin"] == "build/start-edges/approaches.bin"


def test_copy_public_data_declares_every_source_and_public_target():
    task = dodo.task_copy_public_data()
    assert {os.path.basename(t) for t in task["targets"]} == {n for _, n in dodo.PUBLIC_FILES}
    assert all(t.startswith("../huts/public/data/") for t in task["targets"])
