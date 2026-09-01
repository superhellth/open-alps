"""Walks a decoded HMM node path (lib/hmm_match.py's match_trace output) back into the same
accumulated fields lib/cell_igraph.py's accumulate_path produces (spec §5's "Output - unchanged
shape, different internals"), plus spec §2's endpoint trim/bridge reconciliation. Kept separate
from hmm_match.py so the matching core (map construction + decoding) and the accumulation/
reconciliation logic can be tested and read independently."""

from lib.cell_igraph import PathResult


def reconstruct_matched_path(leg_map, node_path: list) -> PathResult:
    """Walks node_path (a list of leg_map's own InMemMap node labels) as a sequence of directed
    sub-edge traversals, looked up from leg_map.sub_edges by (from_node, to_node) - NOT by
    re-deriving an undirected shortest path between consecutive nodes, which would collapse an
    out-and-back spur at its turnaround (spec §2). Repeated sub-edges (an out-and-back) are
    accumulated once per traversal, never deduped - write_edge_records' own base_edge_ids ->
    edge_ids.npy reduction is a separate, already-correct dedup step (spec §2) this function must
    not anticipate."""
    by_pair = {}
    for se in leg_map.sub_edges:
        by_pair.setdefault((se.from_node, se.to_node), se)

    if len(node_path) < 2:
        return PathResult([], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1, False, [])

    trail_coords = []
    distance_m = road_m = ungraded_m = inferred_m = ascent_m = descent_m = 0.0
    max_ele_m = float("-inf")
    max_sac_rank = -1
    has_via_ferrata = False
    base_edge_ids = []

    for a, b in zip(node_path, node_path[1:]):
        se = by_pair.get((a, b))
        if se is None:
            raise ValueError(
                f"decoded path uses edge ({a}, {b}) not present in leg_map.sub_edges - "
                "match_trace returned a node path build_leg_map did not build the map from."
            )
        distance_m += se.dist_m
        road_m += se.road_m
        ungraded_m += se.ungraded_m
        inferred_m += se.inferred_m
        ascent_m += se.ascent_m
        descent_m += se.descent_m
        if se.max_ele_m > max_ele_m:
            max_ele_m = se.max_ele_m
        if se.sac_rank > max_sac_rank:
            max_sac_rank = se.sac_rank
        if se.via_ferrata:
            has_via_ferrata = True
        base_edge_ids.append(se.base_edge_id)

    return PathResult(
        trail_coords, distance_m, road_m, ungraded_m, inferred_m, ascent_m, descent_m,
        max_ele_m, max_sac_rank, has_via_ferrata, base_edge_ids,
    )
