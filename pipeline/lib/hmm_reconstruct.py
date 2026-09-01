"""Walks a decoded HMM node path (lib/hmm_match.py's match_trace output) back into the same
accumulated fields lib/cell_igraph.py's accumulate_path produces (spec §5's "Output - unchanged
shape, different internals"), plus spec §2's endpoint trim/bridge reconciliation. Kept separate
from hmm_match.py so the matching core (map construction + decoding) and the accumulation/
reconciliation logic can be tested and read independently."""

import dataclasses

from lib.cell_igraph import PathResult, build_igraph_with_snaps
from lib.hub_snap import SnapResult


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


@dataclasses.dataclass
class BridgeTooLong:
    endpoint: str
    bridge_m: float
    cap_m: float


def _bridge_node_path_and_length(subgraph, anchor_label: int, decoded_end_label: int):
    """Dijkstra INSIDE the corridor subgraph from the anchor to wherever the decode actually
    starts/ends (spec §2's bridge case: "between the hub and where the recorded track begins, the
    trace describes no shape at all, so shortest-path is the only defensible reconstruction").
    anchor_label/decoded_end_label are subgraph.local_nodes' own node indices (0..n-1) - the same
    label space leg_map's InMemMap uses for parent-edge endpoints (Task 5/7 never renumber those),
    so this is only ever called with a node-snap anchor and a decoded endpoint that is itself an
    original graph node (never a minted interior/split-point label)."""
    graph, hub_vertex, _ = build_igraph_with_snaps(
        subgraph,
        {"anchor": SnapResult(node_index=anchor_label),
         "decoded_end": SnapResult(node_index=decoded_end_label)},
    )
    src_v, tgt_v = hub_vertex["anchor"], hub_vertex["decoded_end"]
    if src_v == tgt_v:
        return [anchor_label], 0.0
    vpath = graph.get_shortest_paths(src_v, to=tgt_v, weights="weight", output="vpath")[0]
    length = graph.distances(src_v, tgt_v, weights="weight")[0][0]
    return vpath, length


def reconcile_endpoints(subgraph, leg_map, node_path: list, endpoint_bridge_max_m: float):
    """Spec §2's trim-or-bridge: reconciles a decoded node_path (never lied to about where the
    trace starts) to leg_map.src_anchor/tgt_anchor. Mirrored at both ends. Returns the reconciled
    node_path, or a BridgeTooLong if either end's bridge exceeds endpoint_bridge_max_m."""
    result = list(node_path)

    if result[0] != leg_map.src_anchor:
        if leg_map.src_anchor in result:
            idx = result.index(leg_map.src_anchor)
            result = result[idx:]
        else:
            bridge_nodes, bridge_len = _bridge_node_path_and_length(
                subgraph, leg_map.src_anchor, result[0],
            )
            if bridge_len > endpoint_bridge_max_m:
                return BridgeTooLong(endpoint="from", bridge_m=bridge_len,
                                      cap_m=endpoint_bridge_max_m)
            result = [*bridge_nodes[:-1], *result]

    if result[-1] != leg_map.tgt_anchor:
        if leg_map.tgt_anchor in result:
            idx = len(result) - 1 - result[::-1].index(leg_map.tgt_anchor)
            result = result[:idx + 1]
        else:
            bridge_nodes, bridge_len = _bridge_node_path_and_length(
                subgraph, leg_map.tgt_anchor, result[-1],
            )
            if bridge_len > endpoint_bridge_max_m:
                return BridgeTooLong(endpoint="to", bridge_m=bridge_len,
                                      cap_m=endpoint_bridge_max_m)
            result = [*result, *bridge_nodes[1:]]

    return result
