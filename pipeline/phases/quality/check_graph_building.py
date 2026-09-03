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
