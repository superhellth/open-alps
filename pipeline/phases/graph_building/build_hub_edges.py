#!/usr/bin/env python3
"""Replaces build_hut_graph.py's pass1/pass2: loads the persisted base graph (build_base_graph.py,
lib/binfmt.py) and the combined hub list (huts.geojson + start_points.npy from
filter_start_points.py), partitions the bbox into lib/grid.py cells, and runs one worker process
per cell via ProcessPoolExecutor - each mmap-slicing only its own padded region
(lib/subgraph.py) rather than sharing one big in-process graph. See docs/superpowers/specs/
2026-08-19-pipeline-v2-design.md.

Usage: python pipeline/phases/graph_building/build_hub_edges.py [--max-edge-km 30] [--max-snap-m 100] [--workers N]
"""

import argparse
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import igraph as ig
import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import binfmt  # noqa: E402
from lib.edge_split import nearest_point_on_polyline, split_edge_at_point  # noqa: E402
from lib.grid import KM_PER_DEG_LAT, Grid  # noqa: E402
from lib.pipeline import OSM_DIR, hut_points, load_config  # noqa: E402
from lib.subgraph import LocalSubgraph, gather_padded_subgraph  # noqa: E402

SCRIPT_NAME = "build_hub_edges.py"


def _haversine_m(lon1, lat1, lon2, lat2):
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _haversine_m_vec(lon1: float, lat1: float, lon2: np.ndarray, lat2: np.ndarray) -> np.ndarray:
    """Same formula as _haversine_m, but against an array of points in one numpy call instead of
    a Python-level loop - used in snap_hub_to_subgraph's node scan, the hot path (one call per hub
    per cell against every candidate node)."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dlambda / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def _haversine_m_vec_pairs(lon1: np.ndarray, lat1: np.ndarray,
                            lon2: np.ndarray, lat2: np.ndarray) -> np.ndarray:
    """Fully-vectorized haversine over paired arrays (both endpoints vary per element), unlike
    _haversine_m_vec (one fixed point vs an array) - used by _build_edge_spatial_index to compute
    every polyline segment length in a cell in one call."""
    r = 6_371_000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlambda / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


@dataclass
class SnapResult:
    node_index: int = None
    edge_local_index: int = None
    split: object = None  # lib.edge_split.SplitResult, only set when node_index is None


def _project_m(lon, lat, km_per_deg_lng: float):
    """Local equirectangular projection to meters, accurate enough at the scale of one padded
    cell (tens of km) - same simplification nearest_point_on_polyline already relies on."""
    return lon * km_per_deg_lng * 1000.0, lat * KM_PER_DEG_LAT * 1000.0


def _build_edge_spatial_index(subgraph: LocalSubgraph):
    """Indexes every polyline vertex (endpoints + interior points) of every local edge in a
    cKDTree, tagged with the owning edge_local_index, so snap_hub_to_subgraph's edge scan can
    query a small candidate set instead of looping every edge. Built once per cell (called once,
    then cached on the subgraph) rather than once per hub - this is what turns the old
    candidates * edges Python loop into edges (build) + candidates * log(edges) (query).

    Correctness: the true nearest point on a polyline segment can lie strictly between its two
    vertices, so a hub within max_snap_m of that point isn't necessarily within max_snap_m of a
    vertex - it can be up to max_snap_m + segment_length away from the nearest vertex (triangle
    inequality). Query radius therefore pads max_snap_m by this cell's longest single segment
    (max_seg_len_m), computed once here, not by max_snap_m alone.

    Vectorized (binfmt.gather_ragged/ragged_positions) rather than a per-edge Python loop with
    per-point scalar structured-array access - was the hot path on a 60km cell with thousands of
    edges * tens-hundreds of interior points each."""
    local_edges = subgraph.local_edges
    n_edges = len(local_edges)
    if n_edges == 0:
        return None
    ref_lat = float(np.mean(subgraph.local_nodes["lat"])) if len(subgraph.local_nodes) else 0.0
    km_per_deg_lng = KM_PER_DEG_LAT * math.cos(math.radians(ref_lat))

    u_lon = subgraph.local_nodes["lon"][local_edges["u"]]
    u_lat = subgraph.local_nodes["lat"][local_edges["u"]]
    v_lon = subgraph.local_nodes["lon"][local_edges["v"]]
    v_lat = subgraph.local_nodes["lat"][local_edges["v"]]

    # Every edge's interior points gathered in one pass; group_ids[k] is which local edge
    # interior_pts[k] belongs to, in original (offset) order within each edge.
    interior_pts, group_ids = binfmt.gather_ragged(
        subgraph.interior, local_edges["interior_offset"], local_edges["interior_count"],
    )
    interior_lon, interior_lat = interior_pts["lon"], interior_pts["lat"]

    # Point order doesn't matter for the KDTree itself (only the edge_id tag per point does) -
    # true polyline order is only needed below, for max_seg_len_m.
    all_lon = np.concatenate([u_lon, interior_lon, v_lon])
    all_lat = np.concatenate([u_lat, interior_lat, v_lat])
    edge_ids = np.concatenate([np.arange(n_edges), group_ids, np.arange(n_edges)])
    xs, ys = _project_m(all_lon, all_lat, km_per_deg_lng)

    # True per-edge polyline order (u -> interior in offset order -> v), reconstructed via a
    # position key + lexsort, needed only to compute real consecutive-segment lengths.
    counts = local_edges["interior_count"].astype(np.int64)
    pos = np.concatenate([np.zeros(n_edges, dtype=np.int64),
                           binfmt.ragged_positions(counts) + 1, counts + 1])
    order = np.lexsort((pos, edge_ids))
    ordered_edge_ids, ordered_lon, ordered_lat = edge_ids[order], all_lon[order], all_lat[order]
    max_seg_len_m = 0.0
    if len(ordered_edge_ids) > 1:
        same_next = ordered_edge_ids[:-1] == ordered_edge_ids[1:]
        if np.any(same_next):
            seg_lens = _haversine_m_vec_pairs(
                ordered_lon[:-1][same_next], ordered_lat[:-1][same_next],
                ordered_lon[1:][same_next], ordered_lat[1:][same_next],
            )
            max_seg_len_m = float(seg_lens.max())

    tree = cKDTree(np.column_stack([xs, ys]))
    return tree, edge_ids, max_seg_len_m, km_per_deg_lng


def _candidate_edges_near(subgraph: LocalSubgraph, hub_lon: float, hub_lat: float,
                           max_snap_m: float) -> list:
    index = getattr(subgraph, "_edge_spatial_index", "unset")
    if index == "unset":
        index = _build_edge_spatial_index(subgraph)
        subgraph._edge_spatial_index = index
    if index is None:
        return []
    tree, edge_ids, max_seg_len_m, km_per_deg_lng = index
    x, y = _project_m(hub_lon, hub_lat, km_per_deg_lng)
    point_idxs = tree.query_ball_point([x, y], r=max_snap_m + max_seg_len_m)
    return sorted(set(edge_ids[point_idxs].tolist()))


def snap_hub_to_subgraph(subgraph: LocalSubgraph, hub_lon: float, hub_lat: float,
                          max_snap_m: float) -> SnapResult | None:
    # An existing graph node within range always wins over a mid-chain split, even if some
    # point along an incident edge is geometrically a hair closer - a hub sitting a few meters
    # off a real node is meant to snap to that node, not spawn a near-duplicate virtual vertex
    # right next to it.
    if len(subgraph.local_nodes) > 0:
        node_dists = _haversine_m_vec(
            hub_lon, hub_lat, subgraph.local_nodes["lon"], subgraph.local_nodes["lat"]
        )
        best_i = int(np.argmin(node_dists))
        if node_dists[best_i] <= max_snap_m:
            return SnapResult(node_index=best_i)

    best_edge = None  # (dist_m, edge_local_index, split)
    for ei in _candidate_edges_near(subgraph, hub_lon, hub_lat, max_snap_m):
        e = subgraph.local_edges[ei]
        interior = [
            (subgraph.interior[j]["lon"], subgraph.interior[j]["lat"])
            for j in range(e["interior_offset"], e["interior_offset"] + e["interior_count"])
        ]
        u = subgraph.local_nodes[e["u"]]
        v = subgraph.local_nodes[e["v"]]
        polyline = [(u["lon"], u["lat"]), *interior, (v["lon"], v["lat"])]
        seg_idx, frac = nearest_point_on_polyline(polyline, (hub_lon, hub_lat))
        px = polyline[seg_idx][0] + frac * (polyline[seg_idx + 1][0] - polyline[seg_idx][0])
        py = polyline[seg_idx][1] + frac * (polyline[seg_idx + 1][1] - polyline[seg_idx][1])
        d = _haversine_m(hub_lon, hub_lat, px, py)
        if d <= max_snap_m and (best_edge is None or d < best_edge[0]):
            split = split_edge_at_point(
                (u["lon"], u["lat"]), (v["lon"], v["lat"]), interior,
                float(e["dist"]), float(e["weight"]), float(e["road_m"]), seg_idx, frac,
            )
            best_edge = (d, ei, split)

    if best_edge is None:
        return None
    _, edge_local_index, split = best_edge
    return SnapResult(edge_local_index=edge_local_index, split=split)


def _build_igraph_with_snaps(subgraph: LocalSubgraph, hub_snaps: dict):
    """hub_snaps: {hub_key: SnapResult}. Returns (graph, hub_key -> igraph vertex id,
    vertex_id -> (lon, lat) for every vertex including virtual snap points), inserting a
    virtual vertex per mid-chain snap (edge_local_index != None). Edge attrs carry everything
    pass-2 path reconstruction needs (dist/road_m/sac_rank/via_ferrata/interior polyline), same
    fields build_hut_graph.py's pass2 reads off its contracted chain edges."""
    n_base = len(subgraph.local_nodes)
    edges_uv = list(zip(subgraph.local_edges["u"].tolist(), subgraph.local_edges["v"].tolist()))
    weights = subgraph.local_edges["weight"].tolist()
    dists = subgraph.local_edges["dist"].tolist()
    road_ms = subgraph.local_edges["road_m"].tolist()
    sac_ranks = subgraph.local_edges["sac_rank"].tolist()
    via_ferratas = subgraph.local_edges["via_ferrata"].tolist()
    interiors = [
        [
            (subgraph.interior[j]["lon"], subgraph.interior[j]["lat"])
            for j in range(e["interior_offset"], e["interior_offset"] + e["interior_count"])
        ]
        for e in subgraph.local_edges
    ]

    vertex_coords = {i: (float(n["lon"]), float(n["lat"])) for i, n in enumerate(subgraph.local_nodes)}

    hub_vertex = {}
    next_vertex = n_base
    edges_to_remove = set()
    for hub_key, snap in hub_snaps.items():
        if snap.node_index is not None:
            hub_vertex[hub_key] = snap.node_index
            continue
        ei = snap.edge_local_index
        u, v = edges_uv[ei]
        edges_to_remove.add(ei)
        split = snap.split
        vid = next_vertex
        next_vertex += 1
        vertex_coords[vid] = split.split_coord
        base_sac_rank = int(subgraph.local_edges["sac_rank"][ei])
        base_via_ferrata = bool(subgraph.local_edges["via_ferrata"][ei])
        edges_uv.append((u, vid))
        weights.append(split.weight_to_u)
        dists.append(split.dist_to_u)
        road_ms.append(split.road_m_to_u)
        sac_ranks.append(base_sac_rank)
        via_ferratas.append(base_via_ferrata)
        interiors.append(list(split.interior_to_u))
        edges_uv.append((vid, v))
        weights.append(split.weight_to_v)
        dists.append(split.dist_to_v)
        road_ms.append(split.road_m_to_v)
        sac_ranks.append(base_sac_rank)
        via_ferratas.append(base_via_ferrata)
        interiors.append(list(split.interior_to_v))
        hub_vertex[hub_key] = vid

    n_orig = len(subgraph.local_edges)

    def _filter(lst):
        kept = [x for i, x in enumerate(lst[:n_orig]) if i not in edges_to_remove]
        return kept + lst[n_orig:]

    graph = ig.Graph(n=next_vertex, edges=_filter(edges_uv), edge_attrs={
        "weight": _filter(weights), "dist": _filter(dists), "road_m": _filter(road_ms),
        "sac_rank": _filter(sac_ranks), "via_ferrata": _filter(via_ferratas),
        "interior": _filter(interiors),
    }, directed=False)
    return graph, hub_vertex, vertex_coords


def _path_for(graph, vertex_coords: dict, src_v: int, tgt_v: int):
    """Walks the weight-shortest src_v->tgt_v path (road-penalized, mirroring
    build_hut_graph.py's pass2) and returns (trail_coords, distance_m, road_m, sac_rank,
    via_ferrata) - trail_coords excludes the hub endpoints themselves, which the caller
    prepends/appends."""
    if src_v == tgt_v:
        return [], 0.0, 0.0, -1, False
    epath = graph.get_shortest_paths(src_v, to=tgt_v, weights="weight", output="epath")[0]
    trail_coords = []
    distance_m = 0.0
    road_m = 0.0
    max_sac_rank = -1
    has_via_ferrata = False
    cur = src_v
    for eid in epath:
        e = graph.es[eid]
        forward = e.source == cur
        nxt = e.target if forward else e.source
        interior = e["interior"] if forward else list(reversed(e["interior"]))
        trail_coords.append(vertex_coords[cur])
        trail_coords.extend(interior)
        distance_m += e["dist"]
        road_m += e["road_m"]
        if e["sac_rank"] > max_sac_rank:
            max_sac_rank = e["sac_rank"]
        if e["via_ferrata"]:
            has_via_ferrata = True
        cur = nxt
    trail_coords.append(vertex_coords[cur])
    return trail_coords, distance_m, road_m, max_sac_rank, has_via_ferrata


def compute_hub_edges_for_cell(subgraph: LocalSubgraph, core_hubs: list,
                                all_hubs: list, max_edge_km: float,
                                max_snap_m: float) -> list:
    """all_hubs: candidate targets already filtered (by the caller) to hubs whose straight-line
    distance to this cell could possibly be within max_edge_km of trail distance - trail distance
    is always >= straight-line distance, so a bbox padded by max_edge_km around the cell is a safe
    superset. Without that prefilter this used to snap every hub in the whole bbox against every
    cell's local subgraph (O(cells * total_hubs) snap calls), which is what made this step take
    hours instead of minutes."""
    if not core_hubs:
        return []

    snaps = {}
    for hub in core_hubs + all_hubs:
        key = (hub["type"], hub["id"])
        if key in snaps:
            continue
        snap = snap_hub_to_subgraph(subgraph, hub["lon"], hub["lat"], max_snap_m)
        if snap is not None:
            snaps[key] = snap

    graph, hub_vertex, vertex_coords = _build_igraph_with_snaps(subgraph, snaps)

    max_edge_m = max_edge_km * 1000
    records = []
    # a hut-hut pair where both ends are core hubs of this cell is visited from both sides
    # below (hub->target and target->hub); collapse it to the one record merge_and_dedup would
    # otherwise keep anyway - core_hubs of a single cell call all belong to the same shard, so
    # merge_and_dedup's cross-shard dedup never sees the in-shard duplicate to drop it.
    seen_hut_pairs = set()
    for hub in core_hubs:
        src_key = (hub["type"], hub["id"])
        if src_key not in hub_vertex:
            continue
        src_v = hub_vertex[src_key]
        targets = [h for h in all_hubs if (h["type"], h["id"]) != (hub["type"], hub["id"])
                   and (h["type"], h["id"]) in hub_vertex]
        if not targets:
            continue
        target_vs = [hub_vertex[(t["type"], t["id"])] for t in targets]
        # Two different hubs can snap to the same graph vertex (both within max_snap_m of one
        # existing node), so target_vs can contain duplicates - igraph's distances() rejects a
        # target list with duplicates, so query only the unique vertex set and fan the results
        # back out per-hub by vertex id.
        unique_target_vs = sorted(set(target_vs))
        # cutoff uses real-distance ("dist") weights, same as build_hut_graph.py's pass1 -
        # max-edge-km stays a guarantee about actual trail length, unaffected by the
        # road-penalty cost ("weight") used to pick the routed path below.
        unique_dists = graph.distances(source=[src_v], target=unique_target_vs, weights="dist")[0]
        dist_by_vertex = dict(zip(unique_target_vs, unique_dists))
        cutoff_dists = [dist_by_vertex[tv] for tv in target_vs]
        for t, tv, cutoff_d in zip(targets, target_vs, cutoff_dists):
            if not np.isfinite(cutoff_d) or cutoff_d > max_edge_m:
                continue
            if hub["type"] == binfmt.TYPE_HUT and t["type"] == binfmt.TYPE_HUT:
                pair_key = tuple(sorted([(hub["type"], hub["id"]), (t["type"], t["id"])]))
                if pair_key in seen_hut_pairs:
                    continue
                seen_hut_pairs.add(pair_key)
            trail_coords, distance_m, road_m, sac_rank, via_ferrata = _path_for(
                graph, vertex_coords, src_v, tv
            )
            geometry = [(hub["lon"], hub["lat"]), *trail_coords, (t["lon"], t["lat"])]
            records.append({
                "from_id": hub["id"], "from_type": hub["type"],
                "to_id": t["id"], "to_type": t["type"],
                "distance_m": float(distance_m),
                "road_m": float(road_m),
                "sac_rank": int(sac_rank),
                "via_ferrata": bool(via_ferrata),
                "geometry": geometry,
            })
    return records


def merge_and_dedup(shard_records: list) -> list:
    seen = set()
    merged = []
    for shard in shard_records:
        for r in shard:
            if r["from_type"] == binfmt.TYPE_HUT and r["to_type"] == binfmt.TYPE_HUT:
                key = tuple(sorted([(r["from_type"], r["from_id"]), (r["to_type"], r["to_id"])]))
                if key in seen:
                    continue
                seen.add(key)
            merged.append(r)
    return merged


def _write_edge_output(records: list, out_dir: Path) -> None:
    """Packs merge_and_dedup's dict records into binfmt.RECORD_DTYPE + a flat geometry.npy
    (binfmt.COORD_DTYPE), mirroring how build_base_graph.py packs contracted-edge interior
    polylines: one growing geometry array, each record's geom_offset/geom_count pointing into
    it. ascent_m/descent_m/profile_offset/profile_count stay UNSET/0 here - add_elevation.py
    (Task 9) fills those in a later pass over this same records.npy."""
    records_arr = np.zeros(len(records), dtype=binfmt.RECORD_DTYPE)
    flat_geometry = []
    cursor = 0
    for i, r in enumerate(records):
        geom = r["geometry"]
        records_arr[i] = (
            r["from_id"], r["to_id"], r["from_type"], r["to_type"], binfmt.VARIANT_SHORTEST,
            r["distance_m"], r["road_m"], binfmt.UNSET, binfmt.UNSET, r["sac_rank"],
            r["via_ferrata"], cursor, len(geom), 0, 0,
        )
        flat_geometry.extend(geom)
        cursor += len(geom)

    geometry_arr = np.zeros(len(flat_geometry), dtype=binfmt.COORD_DTYPE)
    if flat_geometry:
        geometry_arr["lon"] = [p[0] for p in flat_geometry]
        geometry_arr["lat"] = [p[1] for p in flat_geometry]

    binfmt.save_array(out_dir / "records.npy", records_arr)
    binfmt.save_array(out_dir / "geometry.npy", geometry_arr)


def _run_cell(args):
    base_graph_dir, grid, cell_id, buffer_km, core_hubs, candidate_hubs, max_edge_km, \
        max_snap_m = args
    t0 = time.time()
    subgraph = gather_padded_subgraph(base_graph_dir, grid, cell_id, buffer_km)
    records = compute_hub_edges_for_cell(subgraph, core_hubs, candidate_hubs, max_edge_km,
                                          max_snap_m)
    return {
        "cell_id": cell_id, "elapsed_s": time.time() - t0, "n_core_hubs": len(core_hubs),
        "n_nodes": len(subgraph.local_nodes), "n_edges": len(subgraph.local_edges),
        "records": records,
    }


if __name__ == "__main__":
    config = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph-dir", default=str(OSM_DIR / "base_graph"))
    parser.add_argument("--out-dir", default=str(OSM_DIR))
    parser.add_argument("--max-edge-km", type=float, default=config["graph"]["maxEdgeKm"])
    parser.add_argument("--max-snap-m", type=float, default=config["graph"]["maxSnapM"])
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()

    manifest = binfmt.load_manifest(Path(args.base_graph_dir) / "manifest.json")
    grid = Grid(manifest["bbox"], manifest["tile_size_km"])

    hut_coords = hut_points(OSM_DIR / "huts.geojson")
    hut_coords_by_id = {i: tuple(c) for i, c in enumerate(hut_coords)}
    start_points = binfmt.load_array(OSM_DIR / "start_points.npy", mmap=False)
    start_by_id = {}
    for p in start_points:
        start_by_id.setdefault(int(p["type"]), {})[int(p["osm_id"])] = (float(p["lon"]), float(p["lat"]))

    all_hub_coords_by_type = {binfmt.TYPE_HUT: hut_coords_by_id, **start_by_id}

    all_hubs_flat = [
        {"id": hid, "type": htype, "lon": lon, "lat": lat}
        for htype, coords_by_id in all_hub_coords_by_type.items()
        for hid, (lon, lat) in coords_by_id.items()
    ]

    hubs_by_cell = {}
    for hub in all_hubs_flat:
        cid = grid.cell_id_for_point(hub["lon"], hub["lat"])
        hubs_by_cell.setdefault(cid, []).append(hub)

    def _candidate_hubs_for_cell(cid):
        # Trail distance is always >= straight-line distance, so a bbox padded by max_edge_km
        # around the cell is a safe superset of every hub that could end up within max_edge_km
        # trail distance of a hub in this cell - see compute_hub_edges_for_cell's docstring.
        b = grid.padded_bounds(cid, args.max_edge_km)
        return [
            h for h in all_hubs_flat
            if b["minLng"] <= h["lon"] <= b["maxLng"] and b["minLat"] <= h["lat"] <= b["maxLat"]
        ]

    tasks = [
        (args.base_graph_dir, grid, cid, args.max_edge_km, hubs, _candidate_hubs_for_cell(cid),
         args.max_edge_km, args.max_snap_m)
        for cid, hubs in hubs_by_cell.items()
    ]

    total = len(tasks)
    print(f"{total} cells with hubs to process", flush=True)
    shard_records = []
    completed = 0
    t_start = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(_run_cell, t) for t in tasks]
        for fut in as_completed(futures):
            result = fut.result()
            shard_records.append(result["records"])
            completed += 1
            overall_elapsed = time.time() - t_start
            avg_s = overall_elapsed / completed
            remaining_s = avg_s * (total - completed)
            print(
                f"[{completed}/{total}] cell {result['cell_id']}: {result['elapsed_s']:.1f}s "
                f"({result['n_core_hubs']} hubs, {result['n_nodes']:,} nodes, "
                f"{result['n_edges']:,} edges) -> {len(result['records'])} edge records "
                f"| elapsed {overall_elapsed/60:.1f}m, ~{remaining_s/60:.1f}m remaining",
                flush=True,
            )

    merged = merge_and_dedup(shard_records)
    hut_records = [r for r in merged if r["to_type"] == binfmt.TYPE_HUT and r["from_type"] == binfmt.TYPE_HUT]
    start_records = [r for r in merged if r["from_type"] != binfmt.TYPE_HUT]

    print(f"hut-hut edges: {len(hut_records)}, start-hut edges: {len(start_records)}")

    out_dir = Path(args.out_dir)
    _write_edge_output(hut_records, out_dir / "hut_edges")
    _write_edge_output(start_records, out_dir / "start_edges")
    print(f"written {out_dir / 'hut_edges'} and {out_dir / 'start_edges'}")
