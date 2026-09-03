#!/usr/bin/env python3
"""Read-only checks over phases/graph_building/ output (spec docs/superpowers/specs/
2026-09-02-data-quality-monitoring-design.md §4.3): hub snap health, per-variant hut-hut
connectivity, range-cap violations, geometry sanity (added in a second pass over this file - see
check_vertex_gap/check_self_retrace/check_scalar_sanity below the connectivity checks), and
tour-ingestion gap counts. Never mutates its inputs; always exits 0 (spec §3).

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
from lib.pipeline import DEM_DIR, OSM_DIR, QUALITY_DIR, load_config  # noqa: E402
from lib.quality_report import build_check, write_report  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "check_graph_building.py"

EDGE_LAYERS = ["hut_edges", "start_edges", "tour_edges"]


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
    """§4.3.1: unsnapped_huts.json has one entry per rejection reason - count distinct
    (hub_type, hub_id) pairs, not entries."""
    by_hub = defaultdict(list)
    for entry in unsnapped:
        by_hub[(int(entry["hub_type"]), int(entry["hub_id"]))].append(entry["reason"])

    flagged = [
        {"hub_type": hub_type, "hub_id": hub_id, "reasons": reasons}
        for (hub_type, hub_id), reasons in by_hub.items()
    ]
    return build_check(
        "snap_health", {}, checked=len(unsnapped), flagged_rows=flagged, baseline=225,
        max_flagged_rows=max_flagged,
    )


def check_connectivity(records: np.ndarray, n_huts: int, max_flagged: int) -> dict:
    """§4.3.2: union-find over each variant's (from_id, to_id) pairs, separately per variant -
    merging variants would hide exactly the "loses its last T2/T3 connection" structure this
    check exists to surface. Every variant row is included regardless of max_flagged (there are
    at most len(binfmt.VARIANT_NAMES) of them, never capped in practice)."""
    flagged = []
    for variant, name in sorted(binfmt.VARIANT_NAMES.items()):
        if variant == binfmt.VARIANT_OFFICIAL:
            continue  # not a member of the search grid (spec §5 of the tour-integration design)
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


def check_tour_gaps(gaps: list, max_flagged: int) -> dict:
    """§4.3.7: reshapes match_tour_edges.py's tour-match-gaps.json entries into the envelope's
    flagged list - no new detection logic, this only makes the existing count visible."""
    flagged = [
        {"tourId": g["tourId"], "tourName": g["tourName"], "legIndex": g["legIndex"],
         "reason": g["reason"], "detail": g.get("detail")}
        for g in gaps
    ]
    return build_check(
        "tour_ingestion_gaps", {}, checked=len(gaps), flagged_rows=flagged, baseline=len(gaps),
        max_flagged_rows=max_flagged,
    )


def polyline_for_record(record, geometry: np.ndarray) -> np.ndarray:
    """Returns a (n, 2) lon/lat array for one hut_edges/start_edges/tour_edges record, sliced out
    of that layer's flat geometry.npy by geom_offset/geom_count."""
    offset, count = int(record["geom_offset"]), int(record["geom_count"])
    sl = geometry[offset:offset + count]
    return np.column_stack([sl["lon"], sl["lat"]]).astype(np.float64)


def polyline_for_base_edge(edge, nodes: np.ndarray, interior: np.ndarray) -> np.ndarray:
    """Returns a (n, 2) lon/lat array for one base_graph/edges.npy row: its u node, interior
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
    return build_check(
        f"vertex_gap_{layer_name}", {"max_vertex_gap_m": max_gap_m}, checked=checked,
        flagged_rows=flagged, baseline=700 if layer_name == "hut_edges" else 0,
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
    parser.add_argument("--osm-dir", default=str(OSM_DIR))
    parser.add_argument("--dem-dir", default=str(DEM_DIR))
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

    osm_dir = Path(args.osm_dir)

    with phase(SCRIPT_NAME, "check_graph_building"):
        checks = []

        with open(osm_dir / "unsnapped_huts.json", encoding="utf-8") as f:
            unsnapped = json.load(f)
        c = check_snap_health(unsnapped, args.max_flagged_rows)
        print(f"snap_health: {c['summary']['flagged']:,} distinct hubs unsnapped", flush=True)
        checks.append(c)

        with open(osm_dir / "huts.geojson", encoding="utf-8") as f:
            n_huts = len(json.load(f)["features"])
        hut_records = binfmt.load_array(osm_dir / "hut_edges" / "records.npy", mmap=False)
        c = check_connectivity(hut_records, n_huts, args.max_flagged_rows)
        print(f"connectivity: {c['summary']['checked']:,} huts checked across "
              f"{len(c['flagged'])} variants", flush=True)
        checks.append(c)

        for layer_name in ("hut_edges", "start_edges"):
            records = binfmt.load_array(osm_dir / layer_name / "records.npy", mmap=False)
            c = check_range_cap(records, layer_name, args.max_edge_km, args.max_flagged_rows)
            print(f"range_cap[{layer_name}]: {c['summary']['flagged']:,} / "
                  f"{c['summary']['checked']:,} flagged", flush=True)
            checks.append(c)

        base_graph_dir = osm_dir / "base_graph"
        nodes = binfmt.load_array(base_graph_dir / "nodes.npy", mmap=False)
        base_edges = binfmt.load_array(base_graph_dir / "edges.npy", mmap=False)
        interior = binfmt.load_array(base_graph_dir / "interior.npy", mmap=False)
        node_ele = binfmt.load_array(base_graph_dir / "node_ele.npy", mmap=False)
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
            records_path = osm_dir / layer_name / "records.npy"
            geometry_path = osm_dir / layer_name / "geometry.npy"
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

        gaps_path = osm_dir / "tour-match-gaps.json"
        if gaps_path.exists():
            with open(gaps_path, encoding="utf-8") as f:
                gaps = json.load(f)
            c = check_tour_gaps(gaps, args.max_flagged_rows)
            print(f"tour_ingestion_gaps: {c['summary']['flagged']:,} gaps", flush=True)
            checks.append(c)

        write_report(Path(args.out), "graph_building", checks)
        print(f"written {args.out}", flush=True)


if __name__ == "__main__":
    main()
