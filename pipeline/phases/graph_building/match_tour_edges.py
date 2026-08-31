#!/usr/bin/env python3
"""Matches each tour folder's legs (pipeline/tours/<Name>/<N>.gpx, spec docs/superpowers/specs/
2026-08-30-tour-folder-ingestion-design.md) onto the persisted base graph, constrained to each
leg's own GPX trace rather than routed freely. Produces data/osm/tour_edges/{records.npy,
geometry.npy, edge_ids.npy, tour_meta.npy} (same shape as hut_edges/, plus the tour_meta.npy
sidecar), data/osm/tours.json (a per-leg endpoint-intent index) and data/osm/tour-match-gaps.json
(spec §5's never-faked gap reasons).

Usage: python pipeline/phases/graph_building/match_tour_edges.py
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import binfmt  # noqa: E402
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "match_tour_edges.py"

from lib import hub_snap  # noqa: E402
from lib.cell_igraph import (  # noqa: E402
    accumulate_path, build_base_igraph_arrays, build_igraph_from_base,
)
from lib.edge_output import fold_endpoint_snaps  # noqa: E402
from lib.grid import KM_PER_DEG_LAT  # noqa: E402
from lib.subgraph import LocalSubgraph, clip_subgraph_to_bounds, gather_subgraph_for_bounds  # noqa: E402
from lib.geo import haversine_m  # noqa: E402
from lib.hubs import HUB_TYPE_JSON_NAMES, load_all_hubs, nearest_hub_to_point  # noqa: E402
from lib.pipeline import TOURS_DIR  # noqa: E402
from lib.tour_folder import load_all_tour_folders, load_tour_folder  # noqa: E402


_subgraph_cache: dict[tuple[str, tuple[int, ...]], LocalSubgraph] = {}


def _cached_gather_for_bounds(base_graph_dir, grid, bounds):
    """Caches gather_subgraph_for_bounds by (base_graph_dir, overlapping-cell-id tuple), since
    two legs whose corridors fall in the same set of grid cells can reuse the identical
    LocalSubgraph gather (array loads dominate the cost, not the per-call cell-union/closure
    work) - see lib/subgraph.py's gather_subgraph_for_bounds docstring, which already anticipated
    repeated calls with different small bounds from this exact caller. base_graph_dir is part of
    the key (not just assumed constant) so this module-level cache can't leak a stale subgraph
    across separate main() invocations against different base graphs in the same process (e.g.
    the test suite calling main() once per test)."""
    key = (str(base_graph_dir), tuple(sorted(grid.cell_ids_overlapping(bounds))))
    if key not in _subgraph_cache:
        _subgraph_cache[key] = gather_subgraph_for_bounds(base_graph_dir, grid, bounds)
    return _subgraph_cache[key]


def corridor_bounds(points: list, buffer_m: float, grid) -> dict:
    """Bbox around `points`, padded by buffer_m - the "buffer the fragments" half of spec §2.3's
    corridor construction, sized directly off a leg's own chain slice rather than a grid cell (see
    lib/subgraph.py's gather_subgraph_for_bounds, which this feeds)."""
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    dlng = (buffer_m / 1000.0) / grid.km_per_deg_lng
    dlat = (buffer_m / 1000.0) / KM_PER_DEG_LAT
    return {
        "minLng": min(lons) - dlng, "maxLng": max(lons) + dlng,
        "minLat": min(lats) - dlat, "maxLat": max(lats) + dlat,
    }


def match_leg(subgraph, src_key: tuple, tgt_key: tuple, persisted_snaps: dict,
              trace_length_m: float, length_divergence_ratio: float) -> dict:
    """Routes one leg's src_key->tgt_key hut pair inside `subgraph` (already gathered as the leg's
    own corridor, spec §2.3) using the SAME igraph-building/path-walking primitives
    build_hub_edges.py uses (build_base_igraph_arrays/build_igraph_from_base/accumulate_path) -
    unmasked (edge_mask=None), since a tour leg is not a member of graph.variants (spec §5).

    Returns {"ok": True, "path": PathResult, "src_snap": SnapResult, "tgt_snap": SnapResult} or
    {"ok": False, "reason": <spec §2.5 reason>, "detail": {...}} - never a placeholder result."""
    if len(subgraph.local_nodes) == 0:
        return {"ok": False, "reason": "outside_extract", "detail": {}}

    local_snaps = hub_snap.reconstruct_local_snaps(subgraph, {src_key, tgt_key}, persisted_snaps)
    missing = [k for k in (src_key, tgt_key) if k not in local_snaps]
    if missing:
        return {"ok": False, "reason": "hub_unsnapped", "detail": {"missing": missing}}

    base_arrays = build_base_igraph_arrays(subgraph, local_snaps)
    graph, hub_vertex, vertex_coords = build_igraph_from_base(base_arrays, edge_mask=None)
    src_v, tgt_v = hub_vertex.get(src_key), hub_vertex.get(tgt_key)
    if src_v is None or tgt_v is None:
        return {"ok": False, "reason": "no_corridor_path", "detail": {}}

    if src_v == tgt_v:
        epath = []
    else:
        epath = graph.get_shortest_paths(src_v, to=tgt_v, weights="weight", output="epath")[0]
        if not epath:
            return {"ok": False, "reason": "no_corridor_path", "detail": {}}
    path = accumulate_path(graph, vertex_coords, src_v, tgt_v, epath)

    src_snap, tgt_snap = local_snaps[src_key], local_snaps[tgt_key]
    routed_m = path.distance_m + src_snap.gap_m + tgt_snap.gap_m
    if trace_length_m > 0:
        ratio = routed_m / trace_length_m
        if ratio > length_divergence_ratio or ratio < 1.0 / length_divergence_ratio:
            return {
                "ok": False, "reason": "length_divergent",
                "detail": {"routed_m": routed_m, "trace_m": trace_length_m, "ratio": ratio},
            }

    return {"ok": True, "path": path, "src_snap": src_snap, "tgt_snap": tgt_snap}


from lib.edge_output import write_edge_records  # noqa: E402


def build_tour_record(from_key: tuple, to_key: tuple, from_coord: tuple, to_coord: tuple,
                       path, src_snap, tgt_snap) -> dict:
    """Packs one routed leg into the dict shape lib.edge_output.write_edge_records expects -
    applies the SAME endpoint treatment build_hub_edges.py applies: snap_m/gap_dz_m folded via
    fold_endpoint_snaps, geometry prefixed/suffixed with the endpoint hub's own coordinate.
    from_key/to_key are (binfmt.TYPE_*, id) pairs - spec 2026-08-30-tour-folder-ingestion-
    design.md §2: a tour leg's endpoint can be a hut, station, parking spot or partner business,
    not just a hut."""
    from_type, from_id = from_key
    to_type, to_id = to_key
    snap_m, ascent_m, descent_m = fold_endpoint_snaps(path, src_snap, tgt_snap)
    geometry = [from_coord, *path.coords, to_coord]
    return {
        "from_id": from_id, "to_id": to_id,
        "from_type": from_type, "to_type": to_type,
        "variant": binfmt.VARIANT_OFFICIAL,
        "distance_m": float(path.distance_m + snap_m),
        "road_m": float(path.road_m),
        "ascent_m": float(ascent_m), "descent_m": float(descent_m),
        "max_ele_m": float(path.max_ele_m) if path.max_ele_m != float("-inf") else 0.0,
        "ungraded_m": float(path.ungraded_m), "inferred_m": float(path.inferred_m),
        "snap_m": float(snap_m),
        "sac_rank": int(path.sac_rank), "via_ferrata": bool(path.via_ferrata),
        "geometry": geometry, "base_edge_ids": path.base_edge_ids,
    }


def main(argv=None):
    config = load_config()
    tm = config["tourMatch"]
    max_snap_m = config["graph"]["maxSnapM"]
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph-dir", default=str(OSM_DIR / "base_graph"),
                        help="directory holding the persisted base graph (build_base_graph.py's output)")
    parser.add_argument("--out-dir", default=str(OSM_DIR),
                        help="directory to write matched tour edge output into")
    parser.add_argument("--corridor-buffer-m", type=float, default=tm["corridorBufferM"],
                        help="buffer width (m) around a leg's GPX trace used to select candidate base-graph edges")
    parser.add_argument("--length-divergence-ratio", type=float, default=tm["lengthDivergenceRatio"],
                        help="max allowed ratio between matched-edge length and the leg's own GPX trace length")
    args = parser.parse_args(argv)

    from lib.grid import Grid

    base_graph_dir = Path(args.base_graph_dir)
    manifest = binfmt.load_manifest(base_graph_dir / "manifest.json")
    grid = Grid(manifest["bbox"], manifest["tile_size_km"])

    hubs = load_all_hubs(OSM_DIR)

    hub_snaps_arr = binfmt.load_array(Path(args.out_dir) / "hub_snaps.npy", mmap=False)
    hub_snap_interior_arr = binfmt.load_array(Path(args.out_dir) / "hub_snap_interior.npy", mmap=False)
    persisted_snaps = hub_snap.load_persisted_snaps(hub_snaps_arr, hub_snap_interior_arr)

    tour_folders = load_all_tour_folders(TOURS_DIR)
    all_records, tour_meta_rows, gaps, tours_index = [], [], [], []

    with phase(SCRIPT_NAME, "match_tour_edges", n_tours=len(tour_folders)):
        for tour_id, (tour_name, folder) in enumerate(tour_folders):
            legs = load_tour_folder(folder)
            tour_legs_json = []

            for leg_number, points in legs:
                leg_index = leg_number - 1
                gap_ctx = {"tourId": tour_id, "tourName": tour_name, "legIndex": leg_index}

                from_chosen, from_nearest, from_dist = nearest_hub_to_point(hubs, points[0], max_snap_m)
                to_chosen, to_nearest, to_dist = nearest_hub_to_point(hubs, points[-1], max_snap_m)

                def _hub_json(hub):
                    return {"type": HUB_TYPE_JSON_NAMES[hub["type"]], "id": hub["id"]} if hub else None

                tour_legs_json.append({
                    "legIndex": leg_index, "from": _hub_json(from_chosen), "to": _hub_json(to_chosen),
                })

                if from_chosen is None or to_chosen is None:
                    endpoint = "from" if from_chosen is None else "to"
                    nearest, dist = (from_nearest, from_dist) if from_chosen is None else (to_nearest, to_dist)
                    gaps.append({
                        **gap_ctx, "reason": "leg_endpoint_unsnapped",
                        "detail": {
                            "endpoint": endpoint,
                            "nearestType": HUB_TYPE_JSON_NAMES[nearest["type"]] if nearest else None,
                            "nearestId": nearest["id"] if nearest else None,
                            "nearestDistM": dist,
                        },
                    })
                    continue

                from_key = (from_chosen["type"], from_chosen["id"])
                to_key = (to_chosen["type"], to_chosen["id"])
                from_coord = (from_chosen["lon"], from_chosen["lat"])
                to_coord = (to_chosen["lon"], to_chosen["lat"])

                trace_length_m = sum(
                    haversine_m(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
                    for i in range(len(points) - 1)
                )
                bounds = corridor_bounds(points, args.corridor_buffer_m, grid)
                subgraph = clip_subgraph_to_bounds(
                    _cached_gather_for_bounds(base_graph_dir, grid, bounds), bounds,
                )

                result = match_leg(subgraph, from_key, to_key, persisted_snaps,
                                    trace_length_m, args.length_divergence_ratio)
                if not result["ok"]:
                    gaps.append({**gap_ctx, "reason": result["reason"], "detail": result["detail"]})
                    continue

                record = build_tour_record(
                    from_key, to_key, from_coord, to_coord,
                    result["path"], result["src_snap"], result["tgt_snap"],
                )
                all_records.append(record)
                tour_meta_rows.append((tour_id, leg_index))

            tours_index.append({"tourId": tour_id, "name": tour_name, "legs": tour_legs_json})

    print(f"tour legs matched: {len(all_records)}, gaps: {len(gaps)}")

    out_dir = Path(args.out_dir) / "tour_edges"
    write_edge_records(all_records, out_dir, write_edge_ids=True)
    tour_meta_arr = np.zeros(len(tour_meta_rows), dtype=binfmt.TOUR_META_DTYPE)
    for i, row in enumerate(tour_meta_rows):
        tour_meta_arr[i] = row
    binfmt.save_array(out_dir / "tour_meta.npy", tour_meta_arr)

    tours_path = Path(args.out_dir) / "tours.json"
    with open(tours_path, "w", encoding="utf-8") as fh:
        json.dump(tours_index, fh)

    gaps_path = Path(args.out_dir) / "tour-match-gaps.json"
    with open(gaps_path, "w", encoding="utf-8") as fh:
        json.dump(gaps, fh)
    print(f"written {out_dir}, {tours_path} and {gaps_path}")


if __name__ == "__main__":
    main()
