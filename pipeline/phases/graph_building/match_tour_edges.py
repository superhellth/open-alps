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
from lib.subgraph import gather_subgraph_for_bounds  # noqa: E402


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
