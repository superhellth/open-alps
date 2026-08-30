#!/usr/bin/env python3
"""Matches each official AV tour's legs (hutIndices[i] -> hutIndices[i+1], plus the closing leg
for a Rundtour) onto the persisted base graph, constrained to the AV's own published route
geometry rather than routed freely - see docs/superpowers/specs/2026-08-29-official-tours-
integration-design.md. Produces data/osm/tour_edges/{records.npy, geometry.npy, edge_ids.npy,
tour_meta.npy} (same shape as hut_edges/, plus the tour_meta.npy sidecar) and
tour-match-gaps.json (spec §2.5's never-faked gap reasons).

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
from lib.subgraph import clip_subgraph_to_bounds, gather_subgraph_for_bounds  # noqa: E402


def build_tour_legs(tour: dict) -> list:
    """(leg_index, from_hut_index, to_hut_index) triples in tour order, plus the Rundtour closing
    leg (spec §2.1). A leg touching fetch_tours.py's -1 unresolved-GUID sentinel is dropped -
    BOTH legs on either side of a -1 entry are skipped, since neither has a real hut on both ends
    (spec §1's "split the chain" convention)."""
    huts = tour["hutIndices"]
    pairs = list(zip(huts, huts[1:]))
    if tour.get("isLoop") and len(huts) >= 2:
        pairs.append((huts[-1], huts[0]))
    legs = []
    for i, (a, b) in enumerate(pairs):
        if a == -1 or b == -1:
            continue
        legs.append((i, a, b))
    return legs


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
        return {"ok": False, "reason": "hut_unsnapped", "detail": {"missing": missing}}

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
from lib.tour_geometry import (  # noqa: E402
    assign_hut_position, leg_chain_slice, orient_chain, reassemble_fragments,
)


def build_tour_record(from_hut: int, to_hut: int, from_coord: tuple, to_coord: tuple,
                       path, src_snap, tgt_snap) -> dict:
    """Packs one routed leg into the dict shape lib.edge_output.write_edge_records expects -
    applies the SAME endpoint treatment build_hub_edges.py applies (spec §2.6): snap_m/gap_dz_m
    folded via fold_endpoint_snaps, geometry prefixed/suffixed with the hut's own coordinate."""
    snap_m, ascent_m, descent_m = fold_endpoint_snaps(path, src_snap, tgt_snap)
    geometry = [from_coord, *path.coords, to_coord]
    return {
        "from_id": from_hut, "to_id": to_hut,
        "from_type": binfmt.TYPE_HUT, "to_type": binfmt.TYPE_HUT,
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


def _chain_for_tour(paths: list, break_threshold_m: float, hut_coords_in_order: list, is_loop: bool):
    """Reassembles + orients a tour's fragments (spec §2.2). Returns (chains, oriented_primary) -
    oriented_primary is the single reassembled+oriented chain when reassembly produced exactly
    one, else None (callers fall back to a whole-tour bbox built from ALL chains' points, per
    spec §2.3's mitigation note, and every leg whose two huts don't land in the SAME chain becomes
    a chain_not_reassembled gap - spec §2.5)."""
    chains = reassemble_fragments(paths, break_threshold_m)
    if len(chains) == 1:
        return chains, orient_chain(chains[0], hut_coords_in_order, is_loop)
    return chains, None


import math  # noqa: E402


def _leg_segment_m(a, b):
    r = 6_371_000.0
    p1, p2 = math.radians(a[1]), math.radians(b[1])
    dphi = math.radians(b[1] - a[1])
    dlambda = math.radians(b[0] - a[0])
    x = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


def main(argv=None):
    config = load_config()
    tm = config["tourMatch"]
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph-dir", default=str(OSM_DIR / "base_graph"))
    parser.add_argument("--out-dir", default=str(OSM_DIR))
    parser.add_argument("--fragment-break-m", type=float, default=tm["fragmentBreakM"])
    parser.add_argument("--corridor-buffer-m", type=float, default=tm["corridorBufferM"])
    parser.add_argument("--max-hut-trace-m", type=float, default=tm["maxHutTraceM"])
    parser.add_argument("--length-divergence-ratio", type=float, default=tm["lengthDivergenceRatio"])
    args = parser.parse_args(argv)

    from lib.grid import Grid

    base_graph_dir = Path(args.base_graph_dir)
    manifest = binfmt.load_manifest(base_graph_dir / "manifest.json")
    grid = Grid(manifest["bbox"], manifest["tile_size_km"])

    with open(OSM_DIR / "tours.json", encoding="utf-8") as fh:
        tours = json.load(fh)
    with open(OSM_DIR / "tour_traces.json", encoding="utf-8") as fh:
        traces_by_tour_id = {t["tourId"]: t["paths"] for t in json.load(fh)}
    with open(OSM_DIR / "huts.geojson", encoding="utf-8") as fh:
        hut_features = json.load(fh)["features"]
    hut_coords = [tuple(f["geometry"]["coordinates"]) for f in hut_features]

    hub_snaps_arr = binfmt.load_array(Path(args.out_dir) / "hub_snaps.npy", mmap=False)
    hub_snap_interior_arr = binfmt.load_array(Path(args.out_dir) / "hub_snap_interior.npy", mmap=False)
    persisted_snaps = hub_snap.load_persisted_snaps(hub_snaps_arr, hub_snap_interior_arr)

    all_records, tour_meta_rows, gaps = [], [], []

    with phase(SCRIPT_NAME, "match_tour_edges", n_tours=len(tours)):
        for tour in tours:
            legs = build_tour_legs(tour)
            if not legs:
                continue
            hut_coords_in_order = [hut_coords[h] for h in tour["hutIndices"] if h != -1]
            paths = traces_by_tour_id.get(tour["tourId"], [])
            chains, oriented = _chain_for_tour(
                paths, args.fragment_break_m, hut_coords_in_order, tour["isLoop"],
            )
            all_points = [p for chain in chains for p in chain]

            for leg_index, from_hut, to_hut in legs:
                from_coord, to_coord = hut_coords[from_hut], hut_coords[to_hut]
                gap_ctx = {"tourId": tour["tourId"], "shortCode": tour["shortCode"], "legIndex": leg_index}

                if oriented is None:
                    gaps.append({**gap_ctx, "reason": "chain_not_reassembled", "detail": {"n_chains": len(chains)}})
                    continue

                from_pos = assign_hut_position(oriented, from_coord, args.max_hut_trace_m)
                to_pos = assign_hut_position(oriented, to_coord, args.max_hut_trace_m)
                if from_pos is None or to_pos is None:
                    gaps.append({**gap_ctx, "reason": "hut_far_from_trace",
                                 "detail": {"from_dist_m": from_pos and from_pos[1],
                                            "to_dist_m": to_pos and to_pos[1]}})
                    continue

                leg_points = leg_chain_slice(oriented, from_pos[0], to_pos[0])
                trace_length_m = sum(
                    _leg_segment_m(leg_points[i], leg_points[i + 1]) for i in range(len(leg_points) - 1)
                )
                bounds = corridor_bounds(leg_points or all_points, args.corridor_buffer_m, grid)
                subgraph = clip_subgraph_to_bounds(
                    gather_subgraph_for_bounds(base_graph_dir, grid, bounds), bounds,
                )

                src_key, tgt_key = (binfmt.TYPE_HUT, from_hut), (binfmt.TYPE_HUT, to_hut)
                result = match_leg(subgraph, src_key, tgt_key, persisted_snaps,
                                    trace_length_m, args.length_divergence_ratio)
                if not result["ok"]:
                    gaps.append({**gap_ctx, "reason": result["reason"], "detail": result["detail"]})
                    continue

                record = build_tour_record(
                    from_hut, to_hut, from_coord, to_coord,
                    result["path"], result["src_snap"], result["tgt_snap"],
                )
                all_records.append(record)
                tour_meta_rows.append((tour["tourId"], leg_index))

    print(f"tour legs matched: {len(all_records)}, gaps: {len(gaps)}")

    out_dir = Path(args.out_dir) / "tour_edges"
    write_edge_records(all_records, out_dir, write_edge_ids=True)
    tour_meta_arr = np.zeros(len(tour_meta_rows), dtype=binfmt.TOUR_META_DTYPE)
    for i, row in enumerate(tour_meta_rows):
        tour_meta_arr[i] = row
    binfmt.save_array(out_dir / "tour_meta.npy", tour_meta_arr)

    gaps_path = Path(args.out_dir) / "tour-match-gaps.json"
    with open(gaps_path, "w", encoding="utf-8") as fh:
        json.dump(gaps, fh)
    print(f"written {out_dir} and {gaps_path}")


if __name__ == "__main__":
    main()
