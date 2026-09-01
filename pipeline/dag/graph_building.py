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
    return pipeline_task(
        "phases/graph_building/build_hub_edges.py",
        params=[cli_param("max_edge_km", "max-edge-km", float, CONFIG["graph"]["maxEdgeKm"])],
        tracking_params=[
            # build_hub_edges.py reads config["graph"]["variants"] directly
            # (variants_lib.enabled_variants) - without this, a variant-grid edit would report
            # "up to date" and silently skip the rebuild.
            tracking_param("variants_json", str, json.dumps(CONFIG["graph"]["variants"], sort_keys=True)),
            _EDGE_SCHEMA_VERSION_PARAM, _SNAP_SCHEMA_VERSION_PARAM, _RECORD_SCHEMA_VERSION_PARAM,
        ],
        task_dep=["snap_hubs", "gather_route_subgraphs"],
        file_dep=[
            OSM_DIR / "base_graph" / "manifest.json",
            OSM_DIR / "huts.geojson", OSM_DIR / "start_points.npy",
            OSM_DIR / "hub_snaps.npy", OSM_DIR / "hub_snap_interior.npy",
            OSM_DIR / "route_subgraphs" / "manifest.json",
        ],
        targets=[OSM_DIR / "hut_edges" / "records.npy", OSM_DIR / "start_edges" / "records.npy"],
    )


def task_match_tour_edges():
    # Corridor-constrained routing of tour folders (pipeline/tours/) onto the base graph (spec
    # docs/superpowers/specs/2026-08-30-tour-folder-ingestion-design.md). task_dep, not file_dep,
    # on compute_edge_profiles/snap_hubs: both rewrite their outputs in place without declaring
    # them as targets - same reasoning as task_snap_hubs/task_gather_route_subgraphs above. Never
    # a variants_json tracking param: a tour leg is not a member of graph.variants (spec §5 of the
    # 2026-08-29 official-tours-integration design).
    tour_files = sorted(TOURS_DIR.glob("*/*.gpx"))  # flat per spec §1; computed at DAG-build time
    return pipeline_task(
        "phases/graph_building/match_tour_edges.py",
        params=[
            cli_param("corridor_buffer_m", "corridor-buffer-m", float, CONFIG["tourMatch"]["corridorBufferM"]),
            cli_param("length_divergence_ratio", "length-divergence-ratio", float,
                      CONFIG["tourMatch"]["lengthDivergenceRatio"]),
            cli_param("hmm_resample_m", "hmm-resample-m", float, CONFIG["tourMatch"]["hmmResampleM"]),
            cli_param("hmm_obs_noise_m", "hmm-obs-noise-m", float, CONFIG["tourMatch"]["hmmObsNoiseM"]),
            cli_param("hmm_max_dist_m", "hmm-max-dist-m", float, CONFIG["tourMatch"]["hmmMaxDistM"]),
            cli_param("hmm_dist_noise_m", "hmm-dist-noise-m", float, CONFIG["tourMatch"]["hmmDistNoiseM"]),
            cli_param("endpoint_bridge_max_m", "endpoint-bridge-max-m", float,
                      CONFIG["tourMatch"]["endpointBridgeMaxM"]),
        ],
        task_dep=["compute_edge_profiles", "snap_hubs"],
        file_dep=[
            OSM_DIR / "huts.geojson", OSM_DIR / "start_points.npy",
            OSM_DIR / "hub_snaps.npy", OSM_DIR / "hub_snap_interior.npy",
            *tour_files,
        ],
        targets=[
            OSM_DIR / "tour_edges" / "records.npy", OSM_DIR / "tour_edges" / "geometry.npy",
            OSM_DIR / "tour_edges" / "edge_ids.npy", OSM_DIR / "tour_edges" / "tour_meta.npy",
            OSM_DIR / "tours.json", OSM_DIR / "tour-match-gaps.json",
        ],
    )
