"""doit task wiring for phases/graph_building/ - the base trail graph plus hub snapping and
hut-hut/start-hut edge routing on top of it.

build_base_graph and build_hub_edges are NOT force-rerun: their predecessor (build_hut_graph.py)
measured ~4.1 hour runs (data/timings.jsonl, 2026-08-15). Each is freshness-checked normally, with
a TaskOptionsChanged check (via pipeline_task's params) on its own params so a flag retune still
reruns it without needing `doit forget` first.
"""

import json

from lib import binfmt
from lib.doit_support import cli_param, pipeline_task, tracking_param
from lib.pipeline import DEM_DIR, OSM_DIR, TOURS_DIR, load_config

CONFIG = load_config()

# Split so bumping RECORD_DTYPE (this change) doesn't force-rerun task_build_base_graph's ~4h
# EDGE_DTYPE build - see root CLAUDE.md's warning on that task and lib/binfmt.py's dtype table.
_EDGE_SCHEMA_VERSION_PARAM = tracking_param("edge_schema_version", int, binfmt.EDGE_SCHEMA_VERSION)
_SNAP_SCHEMA_VERSION_PARAM = tracking_param("snap_schema_version", int, binfmt.SNAP_SCHEMA_VERSION)
_RECORD_SCHEMA_VERSION_PARAM = tracking_param(
    "record_schema_version", int, binfmt.RECORD_SCHEMA_VERSION
)
_ACCESS_DISTANCE_SCHEMA_VERSION_PARAM = tracking_param(
    "access_distance_schema_version", int, binfmt.ACCESS_DISTANCE_SCHEMA_VERSION
)
_TOUR_LEG_SCHEMA_VERSION_PARAM = tracking_param(
    "tour_leg_schema_version", int, binfmt.TOUR_LEG_SCHEMA_VERSION
)


def task_build_base_graph():
    return pipeline_task(
        "phases/graph_building/build_base_graph.py",
        params=[cli_param("tile_size_km", "tile-size-km", float, CONFIG["graph"]["tileSizeKm"])],
        tracking_params=[
            # build_base_graph.py reads config["graph"]["roadHighwayTags"] (WayGraphHandler's
            # is_road classification) and config["bbox"] (pack_and_write's Grid, which decides
            # every node's cell_id) directly - without these, editing either would silently leave
            # the multi-hour rebuild un-triggered.
            tracking_param("road_highway_tags_json", str,
                            json.dumps(CONFIG["graph"]["roadHighwayTags"])),
            tracking_param("bbox_json", str, json.dumps(CONFIG["bbox"], sort_keys=True)),
            _EDGE_SCHEMA_VERSION_PARAM,
        ],
        file_dep=[OSM_DIR / "trails.osm.pbf"],
        targets=[OSM_DIR / "base_graph" / "manifest.json"],
    )


def task_snap_hubs():
    # Split out of build_hub_edges.py (docs/superpowers/plans/2026-08-23-split-build-hub-edges.md):
    # snapping only needs trail data within max_snap_m, not max_edge_km, and doesn't depend on
    # graph.variants at all - see snap_hubs.py's module docstring.
    return pipeline_task(
        "phases/graph_building/snap_hubs.py",
        params=[
            cli_param("max_snap_m", "max-snap-m", float, CONFIG["graph"]["maxSnapM"]),
            cli_param("max_snap_ascent_m", "max-snap-ascent-m", float,
                      CONFIG["graph"]["maxSnapAscentM"]),
        ],
        tracking_params=[_SNAP_SCHEMA_VERSION_PARAM],
        # compute_edge_profiles rewrites base_graph/edges.npy's time_s/ascent_m/descent_m in place
        # but doesn't declare it as a target (build_base_graph already owns it), so this needs the
        # explicit task_dep - node_ele.npy alone wouldn't prove that in-place rewrite happened.
        task_dep=["compute_edge_profiles"],
        file_dep=[
            OSM_DIR / "base_graph" / "manifest.json", OSM_DIR / "base_graph" / "node_ele.npy",
            OSM_DIR / "huts.geojson", OSM_DIR / "start_points.npy",
            # spec E3: hub elevation is sampled directly from the DEM (same raster as
            # node_ele.npy/interior_ele.npy).
            DEM_DIR / "dem.tif",
        ],
        targets=[
            OSM_DIR / "hub_snaps.npy", OSM_DIR / "hub_snap_interior.npy",
            OSM_DIR / "unsnapped_huts.json",
        ],
    )


def task_gather_route_subgraphs():
    # Split out of build_hub_edges.py: this is the expensive part of gather_padded_subgraph (cell
    # union + one-hop closure + array copy - see lib/subgraph.py), cached so a graph.variants-only
    # retune of build_hub_edges doesn't repeat it. Depends on max_edge_km (unlike snap_hubs above).
    return pipeline_task(
        "phases/graph_building/gather_route_subgraphs.py",
        params=[cli_param("max_edge_km", "max-edge-km", float, CONFIG["graph"]["maxEdgeKm"])],
        tracking_params=[_EDGE_SCHEMA_VERSION_PARAM],
        task_dep=["compute_edge_profiles"],  # same in-place-edit reasoning as snap_hubs above
        file_dep=[
            OSM_DIR / "base_graph" / "manifest.json", OSM_DIR / "base_graph" / "node_ele.npy",
            OSM_DIR / "huts.geojson", OSM_DIR / "start_points.npy",
        ],
        targets=[OSM_DIR / "route_subgraphs" / "manifest.json"],
    )


def task_build_hub_edges():
    # B1/B3 of spec 2026-09-02-hub-edge-scaling-design.md: this task now writes hut_edges/ (full
    # geometry, unchanged) and access_distances.npy (distance/time scalars only, no geometry) -
    # start_edges/ is now build_access_edges' target, materialized only for the pairs
    # select_approach_pairs.py selects out of access_distances.npy.
    return pipeline_task(
        "phases/graph_building/build_hub_edges.py",
        params=[cli_param("max_edge_km", "max-edge-km", float, CONFIG["graph"]["maxEdgeKm"])],
        tracking_params=[
            # build_hub_edges.py reads config["graph"]["variants"] directly
            # (variants_lib.enabled_variants) - without this, a variant-grid edit would report
            # "up to date" and silently skip the rebuild.
            tracking_param("variants_json", str, json.dumps(CONFIG["graph"]["variants"], sort_keys=True)),
            _EDGE_SCHEMA_VERSION_PARAM, _SNAP_SCHEMA_VERSION_PARAM, _RECORD_SCHEMA_VERSION_PARAM,
            _ACCESS_DISTANCE_SCHEMA_VERSION_PARAM,
        ],
        task_dep=["snap_hubs", "gather_route_subgraphs"],
        file_dep=[
            OSM_DIR / "base_graph" / "manifest.json",
            OSM_DIR / "huts.geojson", OSM_DIR / "start_points.npy",
            OSM_DIR / "hub_snaps.npy", OSM_DIR / "hub_snap_interior.npy",
            OSM_DIR / "route_subgraphs" / "manifest.json",
        ],
        targets=[OSM_DIR / "hut_edges" / "records.npy", OSM_DIR / "access_distances.npy"],
    )


def task_build_access_edges():
    # B5/B6: the second and final igraph pass, restricted to select_approach_pairs.py's survivor
    # list - this is what writes the actual start_edges/ every downstream consumer reads.
    return pipeline_task(
        "phases/graph_building/build_access_edges.py",
        params=[cli_param("max_edge_km", "max-edge-km", float, CONFIG["graph"]["maxEdgeKm"])],
        tracking_params=[
            tracking_param("variants_json", str, json.dumps(CONFIG["graph"]["variants"], sort_keys=True)),
            _EDGE_SCHEMA_VERSION_PARAM, _SNAP_SCHEMA_VERSION_PARAM, _RECORD_SCHEMA_VERSION_PARAM,
        ],
        task_dep=["select_approach_pairs", "snap_hubs", "gather_route_subgraphs"],
        file_dep=[
            OSM_DIR / "base_graph" / "manifest.json",
            OSM_DIR / "huts.geojson", OSM_DIR / "start_points.npy",
            OSM_DIR / "hub_snaps.npy", OSM_DIR / "hub_snap_interior.npy",
            OSM_DIR / "route_subgraphs" / "manifest.json",
            OSM_DIR / "selected_access_pairs.npy",
        ],
        targets=[OSM_DIR / "start_edges" / "records.npy"],
    )


def task_match_tour_edges():
    # Reads only huts.geojson, start_points.npy, the DEM and the GPX files: no base-graph task or
    # file is a dependency, so tour iteration never triggers build_base_graph.
    speed = CONFIG["graph"]["speedModel"]
    tour_files = sorted(TOURS_DIR.glob("*/*.gpx"))  # computed at DAG-build time
    return pipeline_task(
        "phases/graph_building/match_tour_edges.py",
        params=[
            cli_param("max_snap_m", "max-snap-m", float, CONFIG["graph"]["maxSnapM"]),
            cli_param("smoothing_kernel_m", "smoothing-kernel-m", float, CONFIG["dem"]["smoothingKernelM"]),
            cli_param("min_slope_segment_m", "min-slope-segment-m", float, CONFIG["dem"]["minSlopeSegmentM"]),
            cli_param("profile_points", "profile-points", int, CONFIG["dem"].get("profilePoints", 30)),
            cli_param("speed_v0", "speed-v0", float, speed["v0"]),
            cli_param("speed_k", "speed-k", float, speed["k"]),
            cli_param("speed_s0", "speed-s0", float, speed["s0"]),
            cli_param("min_speed_ms", "min-speed-ms", float, speed["minSpeedMs"]),
        ],
        tracking_params=[_TOUR_LEG_SCHEMA_VERSION_PARAM],
        file_dep=[
            OSM_DIR / "huts.geojson", OSM_DIR / "start_points.npy", DEM_DIR / "dem.tif",
            *tour_files,
        ],
        targets=[
            OSM_DIR / "tour_edges" / "records.npy", OSM_DIR / "tour_edges" / "geometry.npy",
            OSM_DIR / "tour_edges" / "profiles.npy",
            OSM_DIR / "tours.json", OSM_DIR / "tour-match-gaps.json", OSM_DIR / "hubs.json",
        ],
    )
