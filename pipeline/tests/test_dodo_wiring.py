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


def test_build_base_graph_tracks_road_highway_tags_and_bbox():
    # build_base_graph.py reads config["graph"]["roadHighwayTags"] (WayGraphHandler's is_road
    # classification) and config["bbox"] (pack_and_write's Grid, which decides every node's
    # cell_id) directly, with no CLI flag - without a tracked param either edit would leave
    # TaskOptionsChanged() reporting "up to date" and silently skip the multi-hour rebuild.
    param_names = {p["name"] for p in dodo.task_build_base_graph()["params"]}
    assert {"road_highway_tags_json", "bbox_json"} <= param_names
    assert dodo.task_build_base_graph()["uptodate"]


def test_build_approach_table_tracks_k_and_is_not_hardcoded_into_the_action():
    # config["approach"]["k"] used to be baked straight into the action's f-string with no
    # params/uptodate at all - doit's up-to-date check never diffs the action string (only
    # file_dep hashes and declared uptodate checks), so a k retune silently never reran this.
    task = dodo.task_build_approach_table()
    assert "k" in {p["name"] for p in task["params"]}
    assert task["uptodate"]
    assert any("%(k)s" in action for action in task["actions"])


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
    assert any("hut_edges/records.npy" in p for p in file_deps)
    assert any("hut_edges/edge_ids.npy" in p for p in file_deps)
    targets = set(task["targets"])
    assert any(p.endswith("hut-edge-ids.bin") for p in targets)
    assert any(p.endswith("hut-edge-ids.json") for p in targets)


def test_public_files_includes_hut_edge_ids():
    assert "hut-edge-ids.bin" in dodo.PUBLIC_FILES
    assert "hut-edge-ids.json" in dodo.PUBLIC_FILES


def test_fetch_huts_targets_include_partner_betriebe():
    targets = dodo.task_fetch_huts()["targets"]
    assert any(t.endswith("partner_betriebe.geojson") for t in targets)


def test_filter_start_points_depends_on_partner_betriebe():
    deps = dodo.task_filter_start_points()["file_dep"]
    assert any(d.endswith("partner_betriebe.geojson") for d in deps)


def test_match_tour_edges_depends_on_profiles_and_snaps_not_edges_npy():
    task = dodo.task_match_tour_edges()
    assert "compute_edge_profiles" in task["task_dep"]
    assert "snap_hubs" in task["task_dep"]
    assert "fetch_tour_oa_geometry" not in task["task_dep"]
    assert not any(d.endswith("edges.npy") for d in task["file_dep"])


def test_match_tour_edges_tracks_tour_gpx_files():
    task = dodo.task_match_tour_edges()
    file_deps = [str(d) for d in task["file_dep"]]
    assert any(d.endswith(".gpx") for d in file_deps)


def test_match_tour_edges_targets_tour_edges_directory():
    targets = dodo.task_match_tour_edges()["targets"]
    assert any(t.endswith("tour_edges/records.npy") for t in targets)
    assert any(t.endswith("tour_edges/tour_meta.npy") for t in targets)
    assert any(t.endswith("tour-match-gaps.json") for t in targets)


def test_match_tour_edges_does_not_track_record_schema_version():
    # spec §2.6: this task doesn't own RECORD_DTYPE, so it must never move record_schema_version
    # and never force a build_hub_edges rerun.
    param_names = {p["name"] for p in dodo.task_match_tour_edges().get("params", [])}
    assert "record_schema_version" not in param_names


def test_build_profiles_depends_on_match_tour_edges_and_tour_edges_records():
    task = dodo.task_build_profiles()
    assert any(d.endswith("tour_edges/records.npy") for d in task["file_dep"])
    assert any(t.endswith("tour_edges/profiles.npy") for t in task["targets"])
    assert "match_tour_edges" in task["task_dep"]


def test_build_tour_edge_tiles_mirrors_hut_edge_tiles_wiring():
    task = dodo.task_build_tour_edge_tiles()
    assert "build_profiles" in task["task_dep"]
    assert any(d.endswith("tour_edges/records.npy") for d in task["file_dep"])
    assert any(t.endswith("tour-edges.pmtiles") for t in task["targets"])
    assert any(t.endswith("tour-edge-geometry.bin") for t in task["targets"])
    assert any("--layer-name tour_edges" in a for a in task["actions"])
    # --id-table is required=True even though tour records are hut-only (spec §3)
    assert any("start_points_id_table.json" in a for a in task["actions"])


def test_build_tour_edge_payload_passes_tour_meta_flag():
    task = dodo.task_build_tour_edge_payload()
    assert any("--tour-meta" in a and "tour_meta.npy" in a for a in task["actions"])
    assert any(t.endswith("tour-edge-payload.bin") for t in task["targets"])
    assert "build_profiles" in task["task_dep"]


def test_public_files_includes_every_tour_output():
    for name in [
        "tours.json", "tour-edges.pmtiles", "tour-edge-stats.json",
        "tour-edge-geometry.bin", "tour-edge-geometry.json",
        "tour-edge-payload.bin", "tour-edge-payload.json",
        "tour-match-gaps.json",
    ]:
        assert name in dodo.PUBLIC_FILES, name


def test_public_files_does_not_include_internal_tour_traces():
    # tour_traces.json is the ~3.5MB raw fragment file (spec §1) - internal only, never shipped.
    assert "tour_traces.json" not in dodo.PUBLIC_FILES


def test_default_tasks_includes_the_new_tour_tasks_in_dag_order():
    ordered = dodo.DOIT_CONFIG["default_tasks"]
    for name in ["match_tour_edges", "build_tour_edge_tiles", "build_tour_edge_payload"]:
        assert name in ordered, name
    assert "fetch_tours" not in ordered
    assert "fetch_tour_oa_geometry" not in ordered
    assert ordered.index("snap_hubs") < ordered.index("match_tour_edges")
    assert ordered.index("compute_edge_profiles") < ordered.index("match_tour_edges")
    assert ordered.index("match_tour_edges") < ordered.index("build_profiles")
    assert ordered.index("build_profiles") < ordered.index("build_tour_edge_tiles")
    assert ordered.index("build_profiles") < ordered.index("build_tour_edge_payload")


def test_compute_edge_profiles_is_gated_only_by_the_stamp_build_base_graph_deletes():
    # The stamp is the ONLY thing that can re-trigger this task after a base-graph rebuild:
    # edges.npy (the file it rewrites in place) can't be a file_dep - the rewrite would make it
    # dirty on every check and rerun forever - and its real file_deps (node_ele.npy /
    # interior_ele.npy) survive a rebuild untouched. So build_base_graph.pack_and_write unlinks
    # edge_profiles.stamp, and this task must keep it as a target for that to mean anything.
    task = dodo.task_compute_edge_profiles()
    assert any(str(t).endswith("edge_profiles.stamp") for t in task["targets"])
    assert not any(str(d).endswith("edges.npy") for d in task["file_dep"])


def test_check_preprocessing_depends_on_filter_start_points_output():
    task = dodo.task_check_preprocessing()
    assert "filter_start_points" in task["task_dep"]
    assert any(d.endswith("start_points.npy") for d in task["file_dep"])
    assert any(d.endswith("start_points_id_table.json") for d in task["file_dep"])
    assert any(t.endswith("data/quality/preprocessing.json") for t in task["targets"])


def test_check_elevation_depends_on_compute_edge_profiles_and_build_profiles():
    task = dodo.task_check_elevation()
    assert "compute_edge_profiles" in task["task_dep"]
    assert "build_profiles" in task["task_dep"]
    assert any(t.endswith("data/quality/elevation.json") for t in task["targets"])


def test_check_graph_building_depends_on_match_tour_edges_and_build_hub_edges():
    task = dodo.task_check_graph_building()
    assert "match_tour_edges" in task["task_dep"]
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
