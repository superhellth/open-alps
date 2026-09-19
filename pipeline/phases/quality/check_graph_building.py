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




# Vertices per chunk: bounds the temporaries the vectorized geometry checks allocate (~12 float64/
# int64 arrays of this length) while staying big enough that numpy call overhead is negligible.
CHUNK_VERTICES = 4_000_000
# rec id occupies the top 22 bits of check_self_retrace's packed sort key.
MAX_CHUNK_RECORDS = 1 << 21


class PolylineSet:
    """A ragged set of n polylines, served in chunks so the geometry checks can run vectorized
    without materializing every vertex at once (start_edges alone is hundreds of millions).

    chunks() yields (lo, lon, lat, starts, counts): the polylines lo..lo+len(counts)-1 flattened
    into lon/lat, polyline j occupying lon[starts[j]:starts[j] + counts[j]]. identity(i) is the
    report-row identity of polyline i."""

    def __init__(self, n: int, chunks, identity):
        self.n = n
        self.chunks = chunks
        self.identity = identity


def _chunk_bounds(counts: np.ndarray, max_vertices: int):
    """Yields (lo, hi) record ranges holding at most max_vertices vertices (a lone bigger record
    gets its own chunk) and MAX_CHUNK_RECORDS records."""
    cum = np.cumsum(counts)
    n = len(counts)
    lo = 0
    while lo < n:
        before = int(cum[lo - 1]) if lo else 0
        hi = int(np.searchsorted(cum, before + max_vertices, side="right"))
        hi = min(max(hi, lo + 1), lo + MAX_CHUNK_RECORDS, n)
        yield lo, hi
        lo = hi


def polylines_from_records(records: np.ndarray, geometry: np.ndarray,
                            max_vertices: int = CHUNK_VERTICES) -> PolylineSet:
    """Polylines of a hut-edges/start-edges layer: record i is geometry[geom_offset:+geom_count]."""
    offsets = records["geom_offset"].astype(np.int64)
    counts = records["geom_count"].astype(np.int64)

    def chunks():
        for lo, hi in _chunk_bounds(counts, max_vertices):
            cnt = counts[lo:hi]
            starts = np.cumsum(cnt) - cnt
            total = int(cnt.sum())
            off = offsets[lo:hi]
            if hi - lo == 1 or np.all(off[1:] == off[:-1] + cnt[:-1]):
                sl = geometry[int(off[0]):int(off[0]) + total]
            else:
                sl, _ = binfmt.gather_ragged(geometry, off, cnt)
            yield lo, np.ascontiguousarray(sl["lon"]), np.ascontiguousarray(sl["lat"]), starts, cnt

    def identity(i):
        variant = int(records[i]["variant"])
        return {"from_id": int(records[i]["from_id"]), "to_id": int(records[i]["to_id"]),
                "variant": binfmt.VARIANT_NAMES.get(variant, str(variant))}

    return PolylineSet(len(records), chunks, identity)


def polylines_from_base_edges(edges: np.ndarray, nodes: np.ndarray, interior: np.ndarray,
                               max_vertices: int = CHUNK_VERTICES) -> PolylineSet:
    """Polylines of base-graph/edges.npy: each edge's u node, interior polyline, then v node - the
    same concatenation build_base_graph.py's contraction reasons about, reconstructed for a check
    rather than for routing."""
    interior_counts = edges["interior_count"].astype(np.int64)
    counts = interior_counts + 2

    def chunks():
        for lo, hi in _chunk_bounds(counts, max_vertices):
            cnt = counts[lo:hi]
            ic = interior_counts[lo:hi]
            starts = np.cumsum(cnt) - cnt
            total = int(cnt.sum())
            lon = np.empty(total)
            lat = np.empty(total)
            u, v = edges["u"][lo:hi], edges["v"][lo:hi]
            lon[starts], lat[starts] = nodes["lon"][u], nodes["lat"][u]
            lon[starts + cnt - 1], lat[starts + cnt - 1] = nodes["lon"][v], nodes["lat"][v]
            if ic.sum():
                pts, group = binfmt.gather_ragged(interior, edges["interior_offset"][lo:hi], ic)
                dst = starts[group] + 1 + binfmt.ragged_positions(ic)
                lon[dst], lat[dst] = pts["lon"], pts["lat"]
            yield lo, lon, lat, starts, cnt

    def identity(i):
        return {"edge_id": int(edges[i]["edge_id"]), "u": int(edges[i]["u"]), "v": int(edges[i]["v"])}

    return PolylineSet(len(edges), chunks, identity)


def _segment_lengths(lon: np.ndarray, lat: np.ndarray, starts: np.ndarray, counts: np.ndarray,
                      fill: float) -> np.ndarray:
    """seg[i] = metres from vertex i to vertex i+1 of the same polyline; `fill` at each
    polyline's last vertex (which has no next vertex within its polyline)."""
    seg = np.empty(len(lon))
    seg[:-1] = haversine_m_vec_pairs(lon[:-1], lat[:-1], lon[1:], lat[1:])
    seg[-1] = fill
    seg[(starts + counts - 1)[counts > 0]] = fill
    return seg


def check_vertex_gap(polylines: PolylineSet, layer_name: str, max_gap_m: float, max_flagged: int) -> dict:
    """§4.3.4: the longest gap between consecutive vertices of a record's polyline."""
    flagged = []
    for lo, lon, lat, starts, counts in polylines.chunks():
        long_enough = counts >= 2
        if not long_enough.any():
            continue
        seg = _segment_lengths(lon, lat, starts, counts, fill=-1.0)
        # Records under 2 vertices inside a reduceat range only contribute the -1 fill.
        worst = np.maximum.reduceat(seg, starts[long_enough])
        for j in np.nonzero(long_enough)[0][worst > max_gap_m]:
            rec_seg = seg[starts[j]:starts[j] + counts[j]]
            worst_idx = int(np.argmax(rec_seg))
            flagged.append({
                "layer": layer_name, **polylines.identity(lo + int(j)),
                "max_gap_m": float(rec_seg[worst_idx]), "gap_at_segment": worst_idx,
                "n_points": int(counts[j]),
            })
    baseline = {"hut_edges": 700, "base_graph": 3362}.get(layer_name, 0)
    return build_check(
        f"vertex_gap_{layer_name}", {"max_vertex_gap_m": max_gap_m}, checked=polylines.n,
        flagged_rows=flagged, baseline=baseline,
        max_flagged_rows=max_flagged, sort_key=lambda r: r["max_gap_m"],
    )


_CELL_BITS = 21
_CELL_HALF_RANGE = 1 << (_CELL_BITS - 1)


def _worst_retrace_separation(lon: np.ndarray, lat: np.ndarray, starts: np.ndarray,
                               counts: np.ndarray, snap_tolerance_m: float) -> np.ndarray:
    """Per polyline: the largest along-path distance between two vertices in the same
    snap_tolerance_m grid cell (0 if it never revisits a cell). Vertices are keyed by
    (polyline, cell relative to the polyline's first vertex) packed into one uint64, so one sort
    groups them."""
    n_rec = len(counts)
    rec = np.repeat(np.arange(n_rec), counts)
    lat0 = np.bincount(rec, weights=lat, minlength=n_rec) / np.maximum(counts, 1)
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = m_per_deg_lat * np.maximum(np.cos(np.radians(lat0)), 1e-6)
    cell_x = np.round(lon * m_per_deg_lon[rec] / snap_tolerance_m).astype(np.int64)
    cell_y = np.round(lat * m_per_deg_lat / snap_tolerance_m).astype(np.int64)
    first = np.minimum(starts, len(lon) - 1)[rec]
    dx = np.clip(cell_x - cell_x[first], -_CELL_HALF_RANGE, _CELL_HALF_RANGE - 1) + _CELL_HALF_RANGE
    dy = np.clip(cell_y - cell_y[first], -_CELL_HALF_RANGE, _CELL_HALF_RANGE - 1) + _CELL_HALF_RANGE
    key = ((rec.astype(np.uint64) << np.uint64(2 * _CELL_BITS))
           | (dx.astype(np.uint64) << np.uint64(_CELL_BITS)) | dy.astype(np.uint64))

    seg = _segment_lengths(lon, lat, starts, counts, fill=0.0)
    path_pos = np.cumsum(seg) - seg  # metres from the global chunk start; only differences within a polyline are used

    order = np.argsort(key)
    sorted_key, sorted_pos = key[order], path_pos[order]
    group_start = np.flatnonzero(np.concatenate([[True], sorted_key[1:] != sorted_key[:-1]]))
    span = np.maximum.reduceat(sorted_pos, group_start) - np.minimum.reduceat(sorted_pos, group_start)
    group_rec = (sorted_key[group_start] >> np.uint64(2 * _CELL_BITS)).astype(np.int64)
    rec_start = np.flatnonzero(np.concatenate([[True], group_rec[1:] != group_rec[:-1]]))
    worst = np.zeros(n_rec)
    worst[group_rec[rec_start]] = np.maximum.reduceat(span, rec_start)
    return worst


def check_self_retrace(polylines: PolylineSet, layer_name: str, snap_tolerance_m: float,
                        min_separation_m: float, max_flagged: int) -> dict:
    """§4.3.5: a record's own polyline revisiting a snap_tolerance_m grid cell where the two
    visits are more than min_separation_m apart along the path. The separation term is what keeps
    ordinary switchback geometry from flagging (spec: naive 5m-only rule hits 98.5% of records)."""
    flagged = []
    for lo, lon, lat, starts, counts in polylines.chunks():
        if len(lon) == 0:
            continue
        worst = _worst_retrace_separation(lon, lat, starts, counts, snap_tolerance_m)
        worst[counts < 3] = 0.0
        for j in np.nonzero(worst > min_separation_m)[0]:
            flagged.append({
                "layer": layer_name, **polylines.identity(lo + int(j)),
                "retrace_separation_m": float(worst[j]), "n_points": int(counts[j]),
            })
    return build_check(
        f"self_retrace_{layer_name}",
        {"snap_tolerance_m": snap_tolerance_m, "min_retrace_separation_m": min_separation_m},
        checked=polylines.n, flagged_rows=flagged, baseline=270 if layer_name == "hut_edges" else 0,
        max_flagged_rows=max_flagged, sort_key=lambda r: r["retrace_separation_m"],
    )


def check_scalar_sanity(records: np.ndarray, layer_name: str, ascent_cap_m: float,
                         dem_min_ele_m: float, max_flagged: int) -> dict:
    """§4.3.6: max_ele_m below the DEM's lowest sampled node, ascent_m over ascent_cap_m, and any
    negative distance/ascent/descent."""
    reason_masks = [
        ("max_ele_below_dem_minimum", records["max_ele_m"] < dem_min_ele_m),
        ("ascent_over_cap", records["ascent_m"] > ascent_cap_m),
        ("negative_distance", records["distance_m"] < 0),
        ("negative_ascent", records["ascent_m"] < 0),
        ("negative_descent", records["descent_m"] < 0),
    ]
    any_reason = np.logical_or.reduce([mask for _, mask in reason_masks])
    flagged = []
    for i in np.nonzero(any_reason)[0]:
        r = records[i]
        for reason, mask in reason_masks:
            if mask[i]:
                flagged.append({
                    "layer": layer_name, "row": int(i), "from_id": int(r["from_id"]),
                    "to_id": int(r["to_id"]), "max_ele_m": float(r["max_ele_m"]),
                    "ascent_m": float(r["ascent_m"]), "distance_m": float(r["distance_m"]),
                    "reason": reason,
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
        interior = binfmt.load_array(base_graph_dir / "interior.npy")
        node_ele = binfmt.load_array(base_graph_dir / "node-ele.npy", mmap=False)
        dem_min_ele_m = float(np.min(node_ele)) if len(node_ele) else 0.0

        base_polylines = polylines_from_base_edges(base_edges, nodes, interior)
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
            geometry = binfmt.load_array(geometry_path)
            polylines = polylines_from_records(records, geometry)

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
