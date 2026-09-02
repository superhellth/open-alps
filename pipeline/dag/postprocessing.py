"""doit task wiring for phases/postprocessing/ - packages the routed graph into what the app and
tour-suggestion backend actually consume: vector tiles, an approach/exit table, and the hut-edge
payload."""

from lib.doit_support import cli_param, pipeline_task
from lib.pipeline import OSM_DIR, load_config

CONFIG = load_config()


def task_select_approach_pairs():
    # B2/B4: global selection over access_distances.npy - must run whole-table (loop-closure
    # reverse index isn't cell-local), so it is its own task rather than in-worker selection.
    return pipeline_task(
        "phases/postprocessing/select_approach_pairs.py",
        params=[cli_param("k", "k", int, CONFIG["approach"].get("selectK", 20))],
        task_dep=["build_hub_edges"],
        file_dep=[OSM_DIR / "access_distances.npy"],
        targets=[OSM_DIR / "selected_access_pairs.npy"],
    )


def task_build_trail_tiles():
    tiles_cfg = CONFIG.get("trailTiles", {})
    return pipeline_task(
        "phases/postprocessing/build_trail_tiles.py",
        params=[
            cli_param("min_zoom", "min-zoom", int, tiles_cfg.get("minZoom", 6)),
            cli_param("max_zoom", "max-zoom", int, tiles_cfg.get("maxZoom", 14)),
        ],
        file_dep=[OSM_DIR / "trails.osm.pbf"],
        targets=[OSM_DIR / "trails.pmtiles"],
    )


# shared param builder for both edge-tile tasks below - config["hutEdgeTiles"] used to be baked
# straight into each action's f-string with no params/uptodate at all, so retuning zoom/hover
# tolerance silently never reran either task.
def _hut_edge_tiles_params():
    tiles_cfg = CONFIG.get("hutEdgeTiles", {})
    return [
        cli_param("min_zoom", "min-zoom", int, tiles_cfg.get("minZoom", 6)),
        cli_param("max_zoom", "max-zoom", int, tiles_cfg.get("maxZoom", 14)),
        cli_param("simplify_tolerance_deg", "simplify-tolerance-deg", float,
                  tiles_cfg.get("simplifyToleranceDeg", 0.0003)),
    ]


def task_build_hut_edge_tiles():
    return pipeline_task(
        "phases/postprocessing/build_edge_tiles.py",
        args=[
            f"--edges-dir {OSM_DIR / 'hut_edges'}",
            f"--id-table {OSM_DIR / 'start_points_id_table.json'}",
            "--layer-name hut_edges",
            f"--out-tiles {OSM_DIR / 'hut-edges.pmtiles'}",
            f"--out-stats {OSM_DIR / 'hut-edge-stats.json'}",
            f"--out-geometry-bin {OSM_DIR / 'hut-edge-geometry.bin'}",
            f"--out-geometry-json {OSM_DIR / 'hut-edge-geometry.json'}",
        ],
        params=_hut_edge_tiles_params(),
        # records.npy's profile_offset/profile_count are rewritten in place by build_profiles but
        # aren't one of its declared targets, so file_dep's hash check alone wouldn't guarantee
        # this runs after it.
        task_dep=["build_profiles"],
        file_dep=[OSM_DIR / "hut_edges" / "records.npy"],
        targets=[
            OSM_DIR / "hut-edges.pmtiles", OSM_DIR / "hut-edge-stats.json",
            OSM_DIR / "hut-edge-geometry.bin", OSM_DIR / "hut-edge-geometry.json",
        ],
    )


def task_build_start_edge_tiles():
    return pipeline_task(
        "phases/postprocessing/build_edge_tiles.py",
        args=[
            f"--edges-dir {OSM_DIR / 'start_edges'}",
            f"--id-table {OSM_DIR / 'start_points_id_table.json'}",
            "--layer-name start_edges",
            f"--out-tiles {OSM_DIR / 'start-edges.pmtiles'}",
            f"--out-stats {OSM_DIR / 'start-edge-stats.json'}",
            f"--out-geometry-bin {OSM_DIR / 'start-edge-geometry.bin'}",
            f"--out-geometry-json {OSM_DIR / 'start-edge-geometry.json'}",
        ],
        params=_hut_edge_tiles_params(),
        task_dep=["build_profiles"],  # see task_build_hut_edge_tiles's comment
        file_dep=[OSM_DIR / "start_edges" / "records.npy"],
        targets=[
            OSM_DIR / "start-edges.pmtiles", OSM_DIR / "start-edge-stats.json",
            OSM_DIR / "start-edge-geometry.bin", OSM_DIR / "start-edge-geometry.json",
        ],
    )


def task_build_tour_edge_tiles():
    return pipeline_task(
        "phases/postprocessing/build_edge_tiles.py",
        args=[
            f"--edges-dir {OSM_DIR / 'tour_edges'}",
            # --id-table is required=True on build_edge_tiles.py even though tour records are
            # hut-only (spec §3) - the same id table hut/start edges already resolve display ids
            # from.
            f"--id-table {OSM_DIR / 'start_points_id_table.json'}",
            "--layer-name tour_edges",
            f"--out-tiles {OSM_DIR / 'tour-edges.pmtiles'}",
            f"--out-stats {OSM_DIR / 'tour-edge-stats.json'}",
            f"--out-geometry-bin {OSM_DIR / 'tour-edge-geometry.bin'}",
            f"--out-geometry-json {OSM_DIR / 'tour-edge-geometry.json'}",
        ],
        params=_hut_edge_tiles_params(),
        task_dep=["build_profiles"],  # same in-place-rewrite reasoning as the other two edge-tile tasks
        file_dep=[OSM_DIR / "tour_edges" / "records.npy"],
        targets=[
            OSM_DIR / "tour-edges.pmtiles", OSM_DIR / "tour-edge-stats.json",
            OSM_DIR / "tour-edge-geometry.bin", OSM_DIR / "tour-edge-geometry.json",
        ],
    )


def task_build_approach_table():
    return pipeline_task(
        "phases/postprocessing/build_approach_table.py",
        args=[
            f"--edges-dir {OSM_DIR / 'start_edges'}",
            f"--id-table {OSM_DIR / 'start_points_id_table.json'}",
            f"--out-bin {OSM_DIR / 'approaches.bin'}",
            f"--out-manifest {OSM_DIR / 'approaches.json'}",
        ],
        params=[cli_param("k", "k", int, CONFIG["approach"]["k"])],
        file_dep=[OSM_DIR / "start_edges" / "records.npy", OSM_DIR / "start_points_id_table.json"],
        targets=[OSM_DIR / "approaches.bin", OSM_DIR / "approaches.json"],
    )


def task_build_edge_payload():
    return pipeline_task(
        "phases/postprocessing/build_edge_payload.py",
        args=[
            f"--edges-dir {OSM_DIR / 'hut_edges'}",
            f"--huts {OSM_DIR / 'huts.geojson'}",
            f"--out-bin {OSM_DIR / 'hut-edge-payload.bin'}",
            f"--out-manifest {OSM_DIR / 'hut-edge-payload.json'}",
        ],
        task_dep=["build_profiles"],  # see task_build_hut_edge_tiles's comment
        file_dep=[OSM_DIR / "hut_edges" / "records.npy", OSM_DIR / "huts.geojson"],
        targets=[OSM_DIR / "hut-edge-payload.bin", OSM_DIR / "hut-edge-payload.json"],
    )


def task_build_tour_edge_payload():
    return pipeline_task(
        "phases/postprocessing/build_edge_payload.py",
        args=[
            f"--edges-dir {OSM_DIR / 'tour_edges'}",
            f"--huts {OSM_DIR / 'huts.geojson'}",
            f"--tour-meta {OSM_DIR / 'tour_edges' / 'tour_meta.npy'}",
            f"--out-bin {OSM_DIR / 'tour-edge-payload.bin'}",
            f"--out-manifest {OSM_DIR / 'tour-edge-payload.json'}",
        ],
        task_dep=["build_profiles"],
        file_dep=[
            OSM_DIR / "tour_edges" / "records.npy", OSM_DIR / "tour_edges" / "tour_meta.npy",
            OSM_DIR / "huts.geojson",
        ],
        targets=[OSM_DIR / "tour-edge-payload.bin", OSM_DIR / "tour-edge-payload.json"],
    )


def task_build_edge_ids():
    return pipeline_task(
        "phases/postprocessing/build_edge_ids.py",
        args=[
            f"--edges-dir {OSM_DIR / 'hut_edges'}",
            f"--out-bin {OSM_DIR / 'hut-edge-ids.bin'}",
            f"--out-manifest {OSM_DIR / 'hut-edge-ids.json'}",
        ],
        task_dep=["build_hub_edges"],
        file_dep=[OSM_DIR / "hut_edges" / "records.npy", OSM_DIR / "hut_edges" / "edge_ids.npy"],
        targets=[OSM_DIR / "hut-edge-ids.bin", OSM_DIR / "hut-edge-ids.json"],
    )
