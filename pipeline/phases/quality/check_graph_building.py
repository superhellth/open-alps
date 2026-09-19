#!/usr/bin/env python3
"""Read-only checks over phases/graph_building/ output (spec docs/superpowers/specs/
2026-09-02-data-quality-monitoring-design.md §4.3): hub snap health, per-variant hut-hut
connectivity, range-cap violations and geometry sanity (check_vertex_gap/check_self_retrace/
check_scalar_sanity). Tour matching is checked by check_tour_matching.py. Never mutates its inputs; always exits 0 (spec §3).

Usage: python pipeline/phases/quality/check_graph_building.py
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import binfmt  # noqa: E402
from lib.geo import haversine_m_vec_pairs  # noqa: E402
from lib.pipeline import (  # noqa: E402
    BUILD_DIR, EDGE_LAYER_DIRNAMES, QUALITY_DIR, RAW_DEM_DIR, RAW_DIR, load_config,
)  # noqa: E402
from lib.quality_report import build_check, write_report  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "check_graph_building.py"

EDGE_LAYERS = ["hut_edges", "start_edges"]


def union_find_components(n_nodes: int, edge_pairs: list) -> list:
    """Plain union-find (path compression, union by rank) - n_nodes is the hut count (~846), so a
    Python implementation is fine; no need for scipy/igraph here. Returns a component id per node
    index (0..n_nodes-1), not necessarily contiguous."""
    parent = list(range(n_nodes))
    rank = [0] * n_nodes

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if rank[ra] < rank[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        if rank[ra] == rank[rb]:
            rank[ra] += 1

    for a, b in edge_pairs:
        union(a, b)
    return [find(i) for i in range(n_nodes)]


def check_snap_health(unsnapped: list, max_flagged: int) -> dict:
    """§4.3.1: unsnapped-huts.json has one entry per rejection reason - count distinct
    (hub_type, hub_id) pairs, not entries."""
    by_hub = defaultdict(list)
    for entry in unsnapped:
        by_hub[(int(entry["hub_type"]), int(entry["hub_id"]))].append(entry["reason"])

    flagged = [
        {"hub_type": hub_type, "hub_id": hub_id, "reasons": reasons}
        for (hub_type, hub_id), reasons in by_hub.items()
    ]
    return build_check(
        "snap_health", {}, checked=len(unsnapped), flagged_rows=flagged, baseline=725,
        max_flagged_rows=max_flagged,
    )


def check_connectivity(records: np.ndarray, n_huts: int, max_flagged: int) -> dict:
    """§4.3.2: union-find over each variant's (from_id, to_id) pairs, separately per variant -
    merging variants would hide exactly the "loses its last T2/T3 connection" structure this
    check exists to surface. Every variant row is included regardless of max_flagged (there are
    at most len(binfmt.VARIANT_NAMES) of them, never capped in practice)."""
    flagged = []
    for variant, name in sorted(binfmt.VARIANT_NAMES.items()):
        mask = records["variant"] == variant
        pairs = list(zip(records["from_id"][mask].tolist(), records["to_id"][mask].tolist()))
        components = union_find_components(n_huts, pairs)
        huts_with_edges = {node for pair in pairs for node in pair}
        isolated = n_huts - len(huts_with_edges)
        n_components = len(set(components))
        if huts_with_edges:
            largest = max(
                sum(1 for c in components if c == comp) for comp in {components[h] for h in huts_with_edges}
            )
        else:
            largest = 0
        flagged.append({
            "variant": name, "rows": int(mask.sum()), "huts_with_edges": len(huts_with_edges),
            "isolated_huts": isolated, "components": n_components,
            "huts_outside_largest": len(huts_with_edges) - largest,
        })
    return build_check(
        "connectivity", {}, checked=n_huts, flagged_rows=flagged, baseline=0,
        max_flagged_rows=max_flagged,
    )


def check_range_cap(records: np.ndarray, layer_name: str, max_edge_km: float,
                     max_flagged: int) -> dict:
    """§4.3.3: distance_m > graph.maxEdgeKm * 1000."""
    cap_m = max_edge_km * 1000.0
    bad = records["distance_m"] > cap_m
    flagged = [
        {"layer": layer_name, "from_id": int(records[i]["from_id"]), "to_id": int(records[i]["to_id"]),
         "distance_m": float(records[i]["distance_m"])}
        for i in np.nonzero(bad)[0]
    ]
    return build_check(
        f"range_cap_{layer_name}", {"max_edge_km": max_edge_km}, checked=len(records),
        flagged_rows=flagged, baseline=25 if layer_name == "hut_edges" else 100_592,
        max_flagged_rows=max_flagged, sort_key=lambda r: r["distance_m"],
    )




def polyline_for_record(record, geometry: np.ndarray) -> np.ndarray:
    """Returns a (n, 2) lon/lat array for one hut-edges/start-edges record, sliced out
    of that layer's flat geometry.npy by geom_offset/geom_count."""
    offset, count = int(record["geom_offset"]), int(record["geom_count"])
    sl = geometry[offset:offset + count]
    return np.column_stack([sl["lon"], sl["lat"]]).astype(np.float64)


def polyline_for_base_edge(edge, nodes: np.ndarray, interior: np.ndarray) -> np.ndarray:
    """Returns a (n, 2) lon/lat array for one base-graph/edges.npy row: its u node, interior
    polyline, then its v node - the same concatenation build_base_graph.py's contraction reasons
    about, reconstructed for a check rather than for routing."""
    u, v = int(edge["u"]), int(edge["v"])
    offset, count = int(edge["interior_offset"]), int(edge["interior_count"])
    interior_slice = interior[offset:offset + count]
    lons = np.concatenate([[nodes[u]["lon"]], interior_slice["lon"], [nodes[v]["lon"]]])
    lats = np.concatenate([[nodes[u]["lat"]], interior_slice["lat"], [nodes[v]["lat"]]])
    return np.column_stack([lons, lats]).astype(np.float64)


def check_vertex_gap(polylines: list, layer_name: str, max_gap_m: float, max_flagged: int) -> dict:
    """§4.3.4: the longest gap between consecutive vertices of a record's polyline. Vectorized
    per record (haversine over the whole coords array at once via slicing), not per point."""
    flagged = []
    checked = 0
    for identity, coords in polylines:
        checked += 1
        if len(coords) < 2:
            continue
        seg_dist = haversine_m_vec_pairs(
            coords[:-1, 0], coords[:-1, 1], coords[1:, 0], coords[1:, 1],
        )
        worst_idx = int(np.argmax(seg_dist))
        max_gap = float(seg_dist[worst_idx])
        if max_gap > max_gap_m:
            flagged.append({
                "layer": layer_name, **identity, "max_gap_m": max_gap,
                "gap_at_segment": worst_idx, "n_points": len(coords),
            })
    baseline = {"hut_edges": 700, "base_graph": 3362}.get(layer_name, 0)
    return build_check(
        f"vertex_gap_{layer_name}", {"max_vertex_gap_m": max_gap_m}, checked=checked,
        flagged_rows=flagged, baseline=baseline,
        max_flagged_rows=max_flagged, sort_key=lambda r: r["max_gap_m"],
    )


def check_self_retrace(polylines: list, layer_name: str, snap_tolerance_m: float,
                        min_separation_m: float, max_flagged: int) -> dict:
    """§4.3.5: a record's own polyline revisiting a snap_tolerance_m grid cell where the two
    visits are more than min_separation_m apart along the path. The separation term is what keeps
    ordinary switchback geometry from flagging (spec: naive 5m-only rule hits 98.5% of records)."""
    flagged = []
    checked = 0
    for identity, coords in polylines:
        checked += 1
        if len(coords) < 3:
            continue
        lat0 = float(np.mean(coords[:, 1]))
        m_per_deg_lat = 111_320.0
        m_per_deg_lon = 111_320.0 * max(np.cos(np.radians(lat0)), 1e-6)
        cell_x = np.round(coords[:, 0] * m_per_deg_lon / snap_tolerance_m).astype(np.int64)
        cell_y = np.round(coords[:, 1] * m_per_deg_lat / snap_tolerance_m).astype(np.int64)

        seg_dist = haversine_m_vec_pairs(coords[:-1, 0], coords[:-1, 1], coords[1:, 0], coords[1:, 1])
        cum_dist = np.concatenate([[0.0], np.cumsum(seg_dist)])

        by_cell = defaultdict(list)
        for i in range(len(coords)):
            by_cell[(int(cell_x[i]), int(cell_y[i]))].append(i)

        worst_separation_m = 0.0
        for indices in by_cell.values():
            if len(indices) < 2:
                continue
            span = float(cum_dist[max(indices)] - cum_dist[min(indices)])
            worst_separation_m = max(worst_separation_m, span)

        if worst_separation_m > min_separation_m:
            flagged.append({
                "layer": layer_name, **identity, "retrace_separation_m": worst_separation_m,
                "n_points": len(coords),
            })
    return build_check(
        f"self_retrace_{layer_name}",
        {"snap_tolerance_m": snap_tolerance_m, "min_retrace_separation_m": min_separation_m},
        checked=checked, flagged_rows=flagged, baseline=270 if layer_name == "hut_edges" else 0,
        max_flagged_rows=max_flagged, sort_key=lambda r: r["retrace_separation_m"],
    )


def check_scalar_sanity(records: np.ndarray, layer_name: str, ascent_cap_m: float,
                         dem_min_ele_m: float, max_flagged: int) -> dict:
    """§4.3.6: max_ele_m below the DEM's lowest sampled node, ascent_m over ascent_cap_m, and any
    negative distance/ascent/descent."""
    flagged = []
    for i in range(len(records)):
        r = records[i]
        reasons = []
        if float(r["max_ele_m"]) < dem_min_ele_m:
            reasons.append("max_ele_below_dem_minimum")
        if float(r["ascent_m"]) > ascent_cap_m:
            reasons.append("ascent_over_cap")
        if float(r["distance_m"]) < 0:
            reasons.append("negative_distance")
        if float(r["ascent_m"]) < 0:
            reasons.append("negative_ascent")
        if float(r["descent_m"]) < 0:
            reasons.append("negative_descent")
        for reason in reasons:
            flagged.append({
                "layer": layer_name, "row": i, "from_id": int(r["from_id"]), "to_id": int(r["to_id"]),
                "max_ele_m": float(r["max_ele_m"]), "ascent_m": float(r["ascent_m"]),
                "distance_m": float(r["distance_m"]), "reason": reason,
            })
    return build_check(
        f"scalar_sanity_{layer_name}", {"ascent_cap_m": ascent_cap_m, "dem_min_ele_m": dem_min_ele_m},
        checked=len(records), flagged_rows=flagged,
        baseline=82_017 if layer_name == "start_edges" else (24 if layer_name == "hut_edges" else 0),
        max_flagged_rows=max_flagged,
    )


def main(argv=None):
    config = load_config()
    q = config.get("quality", {})
    max_flagged_default = q.get("maxFlaggedRows", 500)

    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default=str(RAW_DIR))
    parser.add_argument("--build-dir", default=str(BUILD_DIR))
    parser.add_argument("--dem-dir", default=str(RAW_DEM_DIR))
    parser.add_argument("--out", default=str(QUALITY_DIR / "graph_building.json"))
    parser.add_argument("--max-flagged-rows", type=int, default=max_flagged_default)
    parser.add_argument("--max-edge-km", type=float, default=config["graph"]["maxEdgeKm"])
    graph_building_cfg = q.get("graphBuilding", {})
    parser.add_argument("--max-vertex-gap-m", type=float,
                         default=graph_building_cfg.get("maxVertexGapM", 500))
    parser.add_argument("--snap-tolerance-m", type=float,
                         default=graph_building_cfg.get("snapToleranceM", 5))
    parser.add_argument("--min-retrace-separation-m", type=float,
                         default=graph_building_cfg.get("minRetraceSeparationM", 200))
    parser.add_argument("--ascent-cap-m", type=float,
                         default=graph_building_cfg.get("ascentCapM", 5000))
    args = parser.parse_args(argv)

    raw_dir, build_dir = Path(args.raw_dir), Path(args.build_dir)

    with phase(SCRIPT_NAME, "check_graph_building"):
        checks = []

        with open(build_dir / "snapping" / "unsnapped-huts.json", encoding="utf-8") as f:
            unsnapped = json.load(f)
        c = check_snap_health(unsnapped, args.max_flagged_rows)
        print(f"snap_health: {c['summary']['flagged']:,} distinct hubs unsnapped", flush=True)
        checks.append(c)

        with open(raw_dir / "huts.geojson", encoding="utf-8") as f:
            n_huts = len(json.load(f)["features"])
        hut_records = binfmt.load_array(build_dir / "hut-edges" / "records.npy", mmap=False)
        c = check_connectivity(hut_records, n_huts, args.max_flagged_rows)
        print(f"connectivity: {c['summary']['checked']:,} huts checked across "
              f"{len(c['flagged'])} variants", flush=True)
        checks.append(c)

        for layer_name in ("hut_edges", "start_edges"):
            records = binfmt.load_array(build_dir / EDGE_LAYER_DIRNAMES[layer_name] / "records.npy", mmap=False)
            c = check_range_cap(records, layer_name, args.max_edge_km, args.max_flagged_rows)
            print(f"range_cap[{layer_name}]: {c['summary']['flagged']:,} / "
                  f"{c['summary']['checked']:,} flagged", flush=True)
            checks.append(c)

        base_graph_dir = build_dir / "base-graph"
        nodes = binfmt.load_array(base_graph_dir / "nodes.npy", mmap=False)
        base_edges = binfmt.load_array(base_graph_dir / "edges.npy", mmap=False)
        interior = binfmt.load_array(base_graph_dir / "interior.npy", mmap=False)
        node_ele = binfmt.load_array(base_graph_dir / "node-ele.npy", mmap=False)
        dem_min_ele_m = float(np.min(node_ele)) if len(node_ele) else 0.0

        base_polylines = [
            ({"edge_id": int(base_edges[i]["edge_id"]), "u": int(base_edges[i]["u"]),
              "v": int(base_edges[i]["v"])}, polyline_for_base_edge(base_edges[i], nodes, interior))
            for i in range(len(base_edges))
        ]
        c = check_vertex_gap(base_polylines, "base_graph", args.max_vertex_gap_m, args.max_flagged_rows)
        print(f"vertex_gap[base_graph]: {c['summary']['flagged']:,} / {c['summary']['checked']:,} flagged",
              flush=True)
        checks.append(c)

        for layer_name in EDGE_LAYERS:
            layer_dir = build_dir / EDGE_LAYER_DIRNAMES[layer_name]
            records_path = layer_dir / "records.npy"
            geometry_path = layer_dir / "geometry.npy"
            if not records_path.exists() or not geometry_path.exists():
                continue
            records = binfmt.load_array(records_path, mmap=False)
            geometry = binfmt.load_array(geometry_path, mmap=False)
            polylines = [
                ({"from_id": int(records[i]["from_id"]), "to_id": int(records[i]["to_id"]),
                  "variant": binfmt.VARIANT_NAMES.get(int(records[i]["variant"]), str(int(records[i]["variant"])))},
                 polyline_for_record(records[i], geometry))
                for i in range(len(records))
            ]

            c = check_vertex_gap(polylines, layer_name, args.max_vertex_gap_m, args.max_flagged_rows)
            print(f"vertex_gap[{layer_name}]: {c['summary']['flagged']:,} / {c['summary']['checked']:,} flagged",
                  flush=True)
            checks.append(c)

            c = check_self_retrace(polylines, layer_name, args.snap_tolerance_m,
                                    args.min_retrace_separation_m, args.max_flagged_rows)
            print(f"self_retrace[{layer_name}]: {c['summary']['flagged']:,} / {c['summary']['checked']:,} flagged",
                  flush=True)
            checks.append(c)

            c = check_scalar_sanity(records, layer_name, args.ascent_cap_m, dem_min_ele_m,
                                     args.max_flagged_rows)
            print(f"scalar_sanity[{layer_name}]: {c['summary']['flagged']:,} / {c['summary']['checked']:,} flagged",
                  flush=True)
            checks.append(c)

        write_report(Path(args.out), "graph_building", checks)
        print(f"written {args.out}", flush=True)


if __name__ == "__main__":
    main()
