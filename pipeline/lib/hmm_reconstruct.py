"""Walks a decoded HMM node path (lib/hmm_match.py's match_trace output) back into the same
accumulated fields lib/cell_igraph.py's accumulate_path produces (spec §5's "Output - unchanged
shape, different internals"), plus spec §2's endpoint trim/bridge reconciliation. Kept separate
from hmm_match.py so the matching core (map construction + decoding) and the accumulation/
reconciliation logic can be tested and read independently."""

import dataclasses

from lib.cell_igraph import PathResult, build_igraph_with_snaps
from lib.hmm_match import SubEdge
from lib.hub_snap import SnapRejection, SnapResult, snap_hub_to_subgraph


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


def _snap_leg_map_label(subgraph, leg_map, label: int):
    """Resolves any leg_map node label (real subgraph node, or a synthetic interior/split-point
    label lib/hmm_match.py minted) to a SnapResult against `subgraph`, by coordinate - never by
    assuming the label is itself a valid subgraph vertex index, which it need not be."""
    lon, lat = leg_map.node_coords[label]
    snap = snap_hub_to_subgraph(subgraph, lon, lat, max_snap_m=1.0)
    if isinstance(snap, SnapRejection):
        # This label's own coordinate came from this exact subgraph in the first place
        # (Task 5/7's expansion never invents geometry) - failing to re-locate it within 1m only
        # happens if the corridor gather itself changed between building leg_map and calling
        # this, which never happens within one match_leg call.
        raise AssertionError(f"could not re-locate leg_map label {label} on its own subgraph")
    return snap


def _bridge_into_leg_map(subgraph, leg_map, from_label: int, to_label: int):
    """Routes INSIDE the corridor subgraph from from_label to to_label, in that exact traversal
    direction (spec §2's bridge case: "between the hub and where the recorded track begins, the
    trace describes no shape at all, so shortest-path is the only defensible reconstruction").
    Unlike leg_map's own graph, `subgraph` was never filtered to hmmMaxDistM of the trace, so it
    can reach an anchor whose own edges got filtered out entirely for sitting off-corridor.

    Both endpoints are looked up by their own COORDINATE (leg_map.node_coords) via
    _snap_leg_map_label, not assumed to already be subgraph node indices - match_trace's decode
    can land on an interior/split-point label lib/hmm_match.py minted, which does not exist as a
    vertex in `subgraph`'s own igraph at all.

    Mutates leg_map.sub_edges/leg_map.node_coords in place: any bridge-traversed edge that
    build_leg_map's own hmmMaxDistM filter dropped, or any real subgraph node leg_map never kept,
    is added back (in the from_label -> to_label direction actually walked) so
    reconstruct_matched_path's (from_node, to_node) lookup and match_leg's coordinate fill-in both
    still work against the reconciled path. Returns (bridge_node_labels, bridge_length_m) -
    bridge_node_labels starts at from_label and ends at to_label, both already leg_map-compatible."""
    from_snap = _snap_leg_map_label(subgraph, leg_map, from_label)
    to_snap = _snap_leg_map_label(subgraph, leg_map, to_label)

    graph, hub_vertex, _ = build_igraph_with_snaps(subgraph, {"from": from_snap, "to": to_snap})
    src_v, tgt_v = hub_vertex["from"], hub_vertex["to"]
    if src_v == tgt_v:
        return [from_label], 0.0

    epath = graph.get_shortest_paths(src_v, to=tgt_v, weights="weight", output="epath")[0]
    if not epath:
        return [from_label], float("inf")

    # Walk the edge path into a vertex path ourselves (rather than a second get_shortest_paths
    # call for vpath) so the vertex/edge sequences can never disagree on a tie-broken alternate
    # shortest path - mirrors accumulate_path's own cur-pointer walk.
    node_lon, node_lat = subgraph.local_nodes["lon"], subgraph.local_nodes["lat"]
    existing_pairs = {(se.from_node, se.to_node) for se in leg_map.sub_edges}
    cur = src_v
    translated = [from_label]
    length = 0.0
    for eid in epath:
        e = graph.es[eid]
        forward = e.source == cur
        nxt = e.target if forward else e.source
        length += e["weight"]
        label = to_label if nxt == tgt_v else nxt
        if label not in leg_map.node_coords:
            leg_map.node_coords[label] = (float(node_lon[nxt]), float(node_lat[nxt]))
        from_node_label = translated[-1]
        if (from_node_label, label) not in existing_pairs:
            leg_map.sub_edges.append(SubEdge(
                from_node=from_node_label, to_node=label, base_edge_id=e["base_edge_id"],
                direction=1 if forward else -1, segment_index=0,
                dist_m=e["dist"], road_m=e["road_m"], ungraded_m=e["ungraded_m"],
                inferred_m=e["inferred_m"],
                ascent_m=e["ascent_m"] if forward else e["descent_m"],
                descent_m=e["descent_m"] if forward else e["ascent_m"],
                max_ele_m=e["max_ele_m"], sac_rank=e["sac_rank"], via_ferrata=e["via_ferrata"],
            ))
            existing_pairs.add((from_node_label, label))
        translated.append(label)
        cur = nxt

    return translated, length


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
            bridge_nodes, bridge_len = _bridge_into_leg_map(
                subgraph, leg_map, leg_map.src_anchor, result[0],
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
            bridge_nodes, bridge_len = _bridge_into_leg_map(
                subgraph, leg_map, result[-1], leg_map.tgt_anchor,
            )
            if bridge_len > endpoint_bridge_max_m:
                return BridgeTooLong(endpoint="to", bridge_m=bridge_len,
                                      cap_m=endpoint_bridge_max_m)
            result = [*result, *bridge_nodes[1:]]

    return result
