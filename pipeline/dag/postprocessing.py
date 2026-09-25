"""doit task wiring for phases/postprocessing/ - packages the routed graph into what the app and
tour-suggestion backend actually consume: vector tiles, an approach/exit table, and the hut-edge
payload."""

from lib.doit_support import cli_param, pipeline_task
from lib.pipeline import (
    ACCESS_EDGES_DIR, HUT_EDGES_DIR, RAW_DIR, START_EDGES_DIR, START_POINTS_DIR, TOUR_EDGES_DIR,
    TRAILS_DIR, load_config,
)

CONFIG = load_config()


def task_select_approach_pairs():
    # B2/B4: global selection over access-distances.npy - must run whole-table (loop-closure
    # reverse index isn't cell-local), so it is its own task rather than in-worker selection.
    return pipeline_task(
        "phases/postprocessing/select_approach_pairs.py",
        params=[cli_param("k", "k", int, CONFIG["approach"].get("selectK", 20))],
        task_dep=["build_hub_edges"],
        file_dep=[ACCESS_EDGES_DIR / "access-distances.npy"],
        targets=[ACCESS_EDGES_DIR / "selected-access-pairs.npy"],
    )


def task_build_trail_tiles():
    tiles_cfg = CONFIG.get("trailTiles", {})
    return pipeline_task(
        "phases/postprocessing/build_trail_tiles.py",
        params=[
            cli_param("min_zoom", "min-zoom", int, tiles_cfg.get("minZoom", 6)),
            cli_param("max_zoom", "max-zoom", int, tiles_cfg.get("maxZoom", 14)),
        ],
        file_dep=[TRAILS_DIR / "trails.osm.pbf"],
        targets=[TRAILS_DIR / "trails.pmtiles"],
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
            f"--edges-dir {HUT_EDGES_DIR}",
            f"--id-table {START_POINTS_DIR / 'start-points-id-table.json'}",
            "--layer-name hut_edges",
            f"--out-tiles {HUT_EDGES_DIR / 'edges.pmtiles'}",
            f"--out-stats {HUT_EDGES_DIR / 'stats.json'}",
            f"--out-geometry-bin {HUT_EDGES_DIR / 'geometry.bin'}",
            f"--out-geometry-json {HUT_EDGES_DIR / 'geometry.json'}",
            f"--out-elevation-bin {HUT_EDGES_DIR / 'elevation.bin'}",
            f"--out-elevation-json {HUT_EDGES_DIR / 'elevation.json'}",
        ],
        params=_hut_edge_tiles_params(),
        # records.npy's profile_offset/profile_count are rewritten in place by build_profiles but
        # aren't one of its declared targets, so file_dep's hash check alone wouldn't guarantee
        # this runs after it.
        task_dep=["build_profiles"],
        file_dep=[HUT_EDGES_DIR / "records.npy"],
        targets=[
            HUT_EDGES_DIR / "edges.pmtiles", HUT_EDGES_DIR / "stats.json",
            HUT_EDGES_DIR / "geometry.bin", HUT_EDGES_DIR / "geometry.json",
            HUT_EDGES_DIR / "elevation.bin", HUT_EDGES_DIR / "elevation.json",
        ],
    )


def task_build_start_edge_tiles():
    return pipeline_task(
        "phases/postprocessing/build_edge_tiles.py",
        args=[
            f"--edges-dir {START_EDGES_DIR}",
            f"--id-table {START_POINTS_DIR / 'start-points-id-table.json'}",
            "--layer-name start_edges",
            f"--out-tiles {START_EDGES_DIR / 'edges.pmtiles'}",
            f"--out-stats {START_EDGES_DIR / 'stats.json'}",
            f"--out-geometry-bin {START_EDGES_DIR / 'geometry.bin'}",
            f"--out-geometry-json {START_EDGES_DIR / 'geometry.json'}",
            f"--out-elevation-bin {START_EDGES_DIR / 'elevation.bin'}",
            f"--out-elevation-json {START_EDGES_DIR / 'elevation.json'}",
        ],
        params=_hut_edge_tiles_params(),
        task_dep=["build_profiles"],  # see task_build_hut_edge_tiles's comment
        file_dep=[START_EDGES_DIR / "records.npy"],
        targets=[
            START_EDGES_DIR / "edges.pmtiles", START_EDGES_DIR / "stats.json",
            START_EDGES_DIR / "geometry.bin", START_EDGES_DIR / "geometry.json",
            START_EDGES_DIR / "elevation.bin", START_EDGES_DIR / "elevation.json",
        ],
    )


def task_build_tour_edge_tiles():
    # Tour geometry is every raw GPX point: no simplify tolerance. Tiles/stats only need
    # match_tour_edges' outputs (profiles are written by match_tour_edges itself).
    tiles_cfg = CONFIG.get("hutEdgeTiles", {})
    return pipeline_task(
        "phases/postprocessing/build_tour_tiles.py",
        args=[
            f"--edges-dir {TOUR_EDGES_DIR}",
            f"--id-table {START_POINTS_DIR / 'start-points-id-table.json'}",
            f"--out-tiles {TOUR_EDGES_DIR / 'edges.pmtiles'}",
            f"--out-stats {TOUR_EDGES_DIR / 'stats.json'}",
            f"--out-geometry-bin {TOUR_EDGES_DIR / 'geometry.bin'}",
            f"--out-geometry-json {TOUR_EDGES_DIR / 'geometry.json'}",
            f"--out-elevation-bin {TOUR_EDGES_DIR / 'elevation.bin'}",
            f"--out-elevation-json {TOUR_EDGES_DIR / 'elevation.json'}",
        ],
        params=[
            cli_param("min_zoom", "min-zoom", int, tiles_cfg.get("minZoom", 6)),
            cli_param("max_zoom", "max-zoom", int, tiles_cfg.get("maxZoom", 14)),
        ],
        task_dep=["match_tour_edges"],
        file_dep=[TOUR_EDGES_DIR / "records.npy", START_POINTS_DIR / "start-points-id-table.json"],
        targets=[
            TOUR_EDGES_DIR / "edges.pmtiles", TOUR_EDGES_DIR / "stats.json",
            TOUR_EDGES_DIR / "geometry.bin", TOUR_EDGES_DIR / "geometry.json",
            TOUR_EDGES_DIR / "elevation.bin", TOUR_EDGES_DIR / "elevation.json",
        ],
    )


def task_build_approach_table():
    return pipeline_task(
        "phases/postprocessing/build_approach_table.py",
        args=[
            f"--edges-dir {START_EDGES_DIR}",
            f"--id-table {START_POINTS_DIR / 'start-points-id-table.json'}",
            f"--huts {RAW_DIR / 'huts.geojson'}",
            f"--out-bin {START_EDGES_DIR / 'approaches.bin'}",
            f"--out-manifest {START_EDGES_DIR / 'approaches.json'}",
        ],
        params=[
            cli_param(
                "duration_buckets_h", "duration-buckets-h", str,
                ",".join(str(b) for b in CONFIG["approach"]["durationBucketsH"]),
            ),
            cli_param("variants", "variants", str, ",".join(CONFIG["approach"]["variants"])),
        ],
        file_dep=[
            START_EDGES_DIR / "records.npy", START_EDGES_DIR / "geometry.npy",
            START_POINTS_DIR / "start-points-id-table.json", RAW_DIR / "huts.geojson",
        ],
        targets=[START_EDGES_DIR / "approaches.bin", START_EDGES_DIR / "approaches.json"],
    )


def task_build_edge_payload():
    return pipeline_task(
        "phases/postprocessing/build_edge_payload.py",
        args=[
            f"--edges-dir {HUT_EDGES_DIR}",
            f"--huts {RAW_DIR / 'huts.geojson'}",
            f"--out-bin {HUT_EDGES_DIR / 'payload.bin'}",
            f"--out-manifest {HUT_EDGES_DIR / 'payload.json'}",
        ],
        task_dep=["build_profiles"],  # see task_build_hut_edge_tiles's comment
        file_dep=[HUT_EDGES_DIR / "records.npy", HUT_EDGES_DIR / "geometry.npy", RAW_DIR / "huts.geojson"],
        targets=[HUT_EDGES_DIR / "payload.bin", HUT_EDGES_DIR / "payload.json"],
    )


def task_build_edge_ids():
    return pipeline_task(
        "phases/postprocessing/build_edge_ids.py",
        args=[
            f"--edges-dir {HUT_EDGES_DIR}",
            f"--out-bin {HUT_EDGES_DIR / 'ids.bin'}",
            f"--out-manifest {HUT_EDGES_DIR / 'ids.json'}",
        ],
        task_dep=["build_hub_edges"],
        file_dep=[HUT_EDGES_DIR / "records.npy", HUT_EDGES_DIR / "edge-ids.npy"],
        targets=[HUT_EDGES_DIR / "ids.bin", HUT_EDGES_DIR / "ids.json"],
    )


def task_build_start_edge_ids():
    # Sibling of task_build_edge_ids, pointed at start-edges/ - build_edge_ids.py is already
    # generic over --edges-dir, no script change needed (docs/superpowers/specs/
    # 2026-09-04-approach-exit-overlap-avoidance-design.md §2).
    return pipeline_task(
        "phases/postprocessing/build_edge_ids.py",
        args=[
            f"--edges-dir {START_EDGES_DIR}",
            f"--out-bin {START_EDGES_DIR / 'ids.bin'}",
            f"--out-manifest {START_EDGES_DIR / 'ids.json'}",
        ],
        task_dep=["build_access_edges"],
        file_dep=[START_EDGES_DIR / "records.npy", START_EDGES_DIR / "edge-ids.npy"],
        targets=[START_EDGES_DIR / "ids.bin", START_EDGES_DIR / "ids.json"],
    )
