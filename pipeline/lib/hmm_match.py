"""HMM-style map matching for one tour leg's corridor (docs/superpowers/specs/
2026-09-01-corridor-hmm-map-matching-design.md). Builds a per-leg leuvenmapmatching InMemMap out
of the corridor subgraph's expanded interior polylines, decodes the leg's resampled GPX trace
against it via Viterbi (DistanceMatcher), and hands the winning node path back to
lib/hmm_reconstruct.py for accumulation into the same fields lib/cell_igraph.py's accumulate_path
produces.

Coordinate order: leuvenmapmatching wants (lat, lon); everything else in this pipeline (GPX
points, EDGE_DTYPE/COORD_DTYPE columns, PathResult) is (lon, lat). The swap happens at exactly two
boundaries in this module - _latlon() below - and nowhere else."""

import dataclasses
import math

from leuvenmapmatching.map.inmem import InMemMap
from leuvenmapmatching.matcher.distance import DistanceMatcher

from lib.edge_split import nearest_point_on_polyline
from lib.geo import haversine_m


def _latlon(lon_lat: tuple) -> tuple:
    """(lon, lat) -> (lat, lon) - the one place this module hands a coordinate to
    leuvenmapmatching."""
    lon, lat = lon_lat
    return (lat, lon)


def _lonlat(lat_lon: tuple) -> tuple:
    """(lat, lon) -> (lon, lat) - the one place this module reads a coordinate back out of
    leuvenmapmatching."""
    lat, lon = lat_lon
    return (lon, lat)


def resample_trace(points: list, resample_m: float) -> list:
    """Decimate-only normalization (spec §3): a run of points closer together than resample_m is
    thinned down to it; a sparse stretch is left alone - no point is ever interpolated into
    existence. Endpoints are always kept exactly. points/return value: [(lon, lat), ...]."""
    if len(points) <= 2:
        return list(points)
    out = [points[0]]
    last = points[0]
    for p in points[1:-1]:
        if haversine_m(last[0], last[1], p[0], p[1]) >= resample_m:
            out.append(p)
            last = p
    out.append(points[-1])
    return out


def build_inmem_map(nodes: dict) -> InMemMap:
    """nodes: {node_label: (lon, lat), ...}. Returns an InMemMap with every node added (no edges
    yet - Task 6's build_leg_map adds edges on top of this)."""
    m = InMemMap("leg", use_latlon=True, use_rtree=True, index_edges=True)
    for label, coord in nodes.items():
        m.add_node(label, _latlon(coord))
    return m


@dataclasses.dataclass
class SubEdge:
    from_node: int
    to_node: int
    base_edge_id: int
    direction: int  # +1 parent u->v, -1 parent v->u
    segment_index: int  # index into parent's [u, *interior, v] polyline at the FROM point
    dist_m: float
    road_m: float
    ungraded_m: float
    inferred_m: float
    ascent_m: float
    descent_m: float
    max_ele_m: float
    sac_rank: int
    via_ferrata: bool


def expand_edge_interiors(subgraph, next_node_id: int):
    """Expands every local edge's interior polyline into a chain of directed SubEdges, tagged
    with the disambiguated base_edge_id (edge_id*3, spec §2 / lib/cell_igraph.py:129-179) and
    added in both directions - trails are walkable either way. Returns (sub_edges,
    extra_node_coords, next_node_id): extra_node_coords maps a newly-minted interior-point node
    label to (lon, lat); the parent edge's own endpoints reuse subgraph.local_nodes' own indices
    (0..n-1) as node labels, so this function never mints a label below len(subgraph.local_nodes)."""
    sub_edges = []
    extra_nodes = {}
    node_lon = subgraph.local_nodes["lon"]
    node_lat = subgraph.local_nodes["lat"]

    for e in subgraph.local_edges:
        u, v = int(e["u"]), int(e["v"])
        interior = [
            (float(subgraph.interior[j]["lon"]), float(subgraph.interior[j]["lat"]))
            for j in range(e["interior_offset"], e["interior_offset"] + e["interior_count"])
        ]
        interior_ele = [
            float(subgraph.interior_ele[j])
            for j in range(e["interior_offset"], e["interior_offset"] + e["interior_count"])
        ]
        full_coords = [(float(node_lon[u]), float(node_lat[u])), *interior,
                        (float(node_lon[v]), float(node_lat[v]))]
        full_ele = [float(subgraph.local_node_ele[u]), *interior_ele,
                    float(subgraph.local_node_ele[v])]

        # Mint one new node label per interior point; endpoints reuse the existing u/v labels.
        labels = [u]
        for coord in interior:
            labels.append(next_node_id)
            extra_nodes[next_node_id] = coord
            next_node_id += 1
        labels.append(v)

        seg_lengths = [
            haversine_m(*full_coords[i], *full_coords[i + 1])
            for i in range(len(full_coords) - 1)
        ]
        total = sum(seg_lengths) or 1.0
        base_edge_id = int(e["edge_id"]) * 3
        n_seg = len(seg_lengths)

        for direction in (1, -1):
            seg_order = range(n_seg) if direction == 1 else range(n_seg - 1, -1, -1)
            for si in seg_order:
                ratio = seg_lengths[si] / total
                frm, to = (labels[si], labels[si + 1]) if direction == 1 else (labels[si + 1], labels[si])
                ascent = float(e["ascent_m"]) * ratio
                descent = float(e["descent_m"]) * ratio
                sub_edges.append(SubEdge(
                    from_node=frm, to_node=to, base_edge_id=base_edge_id, direction=direction,
                    segment_index=si,
                    dist_m=seg_lengths[si], road_m=float(e["road_m"]) * ratio,
                    ungraded_m=float(e["ungraded_m"]) * ratio,
                    inferred_m=float(e["inferred_m"]) * ratio,
                    ascent_m=ascent if direction == 1 else descent,
                    descent_m=descent if direction == 1 else ascent,
                    max_ele_m=max(full_ele[si], full_ele[si + 1]),
                    sac_rank=int(e["sac_rank"]), via_ferrata=bool(e["via_ferrata"]),
                ))

    return sub_edges, extra_nodes, next_node_id


def _min_dist_to_polyline_m(point: tuple, trace: list, lng_scale: float) -> float:
    seg_idx, frac = nearest_point_on_polyline(trace, point, lng_scale=lng_scale)
    ax, ay = trace[seg_idx]
    bx, by = trace[seg_idx + 1]
    px, py = ax + frac * (bx - ax), ay + frac * (by - ay)
    return haversine_m(point[0], point[1], px, py)


def filter_sub_edges_near_trace(sub_edges: list, extra_nodes: dict, trace: list,
                                 max_dist_m: float, node_coords: dict) -> tuple:
    """Drops any sub-edge whose closer endpoint is further than max_dist_m from `trace` - spec
    §2's "Bounding the map": no candidate outside the emission cutoff can ever win a Viterbi
    state. node_coords must map every from_node/to_node label used by sub_edges to (lon, lat)
    (parent endpoints + extra_nodes combined)."""
    lng_scale = math.cos(math.radians(sum(p[1] for p in trace) / len(trace)))
    kept = []
    used_labels = set()
    for se in sub_edges:
        from_coord = node_coords[se.from_node]
        to_coord = node_coords[se.to_node]
        d = min(
            _min_dist_to_polyline_m(from_coord, trace, lng_scale),
            _min_dist_to_polyline_m(to_coord, trace, lng_scale),
        )
        if d <= max_dist_m:
            kept.append(se)
            used_labels.add(se.from_node)
            used_labels.add(se.to_node)
    kept_extra_nodes = {label: coord for label, coord in extra_nodes.items() if label in used_labels}
    return kept, kept_extra_nodes


def materialize_anchor(subgraph, snap, next_node_id: int):
    """Materializes one endpoint hub's snap into the leg map (spec §2's "Endpoint anchoring"),
    mirroring build_base_igraph_arrays' node-snap/mid-chain-snap split exactly:
    - node snap: the anchor IS an existing parent-edge endpoint label (0..n-1) - nothing to add.
    - mid-chain snap: mints one new node at split.split_coord, emits the two halves (tagged
      edge_id*3+1/+2, spec §2) as bidirectional SubEdges IN PLACE OF the whole parent edge - the
      caller (build_leg_map) is responsible for excluding the parent's own edge_id*3 sub-edges
      when an anchor claims that edge.
    Returns (anchor_label, extra_sub_edges, extra_node_coords, next_node_id)."""
    if snap.node_index is not None:
        return snap.node_index, [], {}, next_node_id

    ei = snap.edge_local_index
    e = subgraph.local_edges[ei]
    u, v = int(e["u"]), int(e["v"])
    split = snap.split
    anchor = next_node_id
    next_node_id += 1
    extra_nodes = {anchor: split.split_coord}

    node_lon, node_lat = subgraph.local_nodes["lon"], subgraph.local_nodes["lat"]
    u_coord = (float(node_lon[u]), float(node_lat[u]))
    v_coord = (float(node_lon[v]), float(node_lat[v]))
    base_edge_id = int(e["edge_id"]) * 3

    halves = [
        # (from_label, to_label, from_coord, to_coord, interior, dist, road, ungraded, inferred, tag)
        (u, anchor, u_coord, split.split_coord, list(split.interior_to_u),
         split.dist_to_u, split.road_m_to_u, split.ungraded_m_to_u, split.inferred_m_to_u,
         base_edge_id + 1),
        (anchor, v, split.split_coord, v_coord, list(split.interior_to_v),
         split.dist_to_v, split.road_m_to_v, split.ungraded_m_to_v, split.inferred_m_to_v,
         base_edge_id + 2),
    ]

    extra_edges = []
    for from_lbl, to_lbl, from_c, to_c, interior, dist_m, road_m, ungraded_m, inferred_m, tag in halves:
        full_coords = [from_c, *interior, to_c]
        seg_lengths = [
            haversine_m(*full_coords[i], *full_coords[i + 1]) for i in range(len(full_coords) - 1)
        ]
        total = sum(seg_lengths) or 1.0
        labels = [from_lbl, *[None] * len(interior), to_lbl]
        # interior points of a split half are not shared with anything else, so they get fresh
        # labels of their own too (a hub snap on a leg with >1 interior point per half).
        for i in range(1, len(labels) - 1):
            labels[i] = next_node_id
            extra_nodes[next_node_id] = interior[i - 1]
            next_node_id += 1
        n_seg = len(seg_lengths)
        for direction in (1, -1):
            seg_order = range(n_seg) if direction == 1 else range(n_seg - 1, -1, -1)
            for si in seg_order:
                ratio = seg_lengths[si] / total
                frm, to = (labels[si], labels[si + 1]) if direction == 1 else (labels[si + 1], labels[si])
                extra_edges.append(SubEdge(
                    from_node=frm, to_node=to, base_edge_id=tag, direction=direction,
                    segment_index=si, dist_m=seg_lengths[si], road_m=road_m * ratio,
                    ungraded_m=ungraded_m * ratio, inferred_m=inferred_m * ratio,
                    ascent_m=0.0, descent_m=0.0,  # split halves inherit, don't divide - lib/cell_igraph.py:110-113
                    max_ele_m=max(
                        float(subgraph.local_node_ele[u]), float(subgraph.local_node_ele[v])
                    ),
                    sac_rank=int(e["sac_rank"]), via_ferrata=bool(e["via_ferrata"]),
                ))

    return anchor, extra_edges, extra_nodes, next_node_id


@dataclasses.dataclass
class LegMap:
    inmem_map: object
    sub_edges: list  # every kept SubEdge actually added to inmem_map
    src_anchor: int
    tgt_anchor: int


def build_leg_map(subgraph, src_snap, tgt_snap, trace: list, max_dist_m: float) -> LegMap:
    """Assembles one leg's per-leg InMemMap (spec §2): expand every corridor edge's interior into
    tagged bidirectional sub-edges, materialize both endpoint anchors (replacing the whole parent
    edge for a mid-chain anchor so its plain edge_id*3 form never coexists with the split halves),
    filter to hmmMaxDistM of the trace, then build the map. Never touches the whole base graph -
    only `subgraph` (the leg's own corridor gather, unchanged from today's match_leg)."""
    next_id = len(subgraph.local_nodes)
    sub_edges, extra_nodes, next_id = expand_edge_interiors(subgraph, next_node_id=next_id)

    replaced_parent_edge_ids = set()
    for snap in (src_snap, tgt_snap):
        if snap.node_index is None:
            replaced_parent_edge_ids.add(int(subgraph.local_edges[snap.edge_local_index]["edge_id"]) * 3)

    sub_edges = [se for se in sub_edges if se.base_edge_id not in replaced_parent_edge_ids]

    src_anchor, src_extra_edges, src_extra_nodes, next_id = materialize_anchor(subgraph, src_snap, next_id)
    tgt_anchor, tgt_extra_edges, tgt_extra_nodes, next_id = materialize_anchor(subgraph, tgt_snap, next_id)

    sub_edges = [*sub_edges, *src_extra_edges, *tgt_extra_edges]
    extra_nodes = {**extra_nodes, **src_extra_nodes, **tgt_extra_nodes}

    node_lon, node_lat = subgraph.local_nodes["lon"], subgraph.local_nodes["lat"]
    node_coords = {i: (float(node_lon[i]), float(node_lat[i])) for i in range(len(subgraph.local_nodes))}
    node_coords.update(extra_nodes)

    kept, kept_extra_nodes = filter_sub_edges_near_trace(
        sub_edges, extra_nodes, trace, max_dist_m, node_coords,
    )
    # The two anchors must always survive filtering, even if geometrically borderline - a
    # dropped anchor breaks the invariant Task 9's reconcile_endpoints relies on.
    kept_labels = {se.from_node for se in kept} | {se.to_node for se in kept}
    for anchor in (src_anchor, tgt_anchor):
        if anchor not in kept_labels and anchor in node_coords:
            kept_extra_nodes.setdefault(anchor, node_coords[anchor])

    parent_node_labels = {
        lbl for se in kept for lbl in (se.from_node, se.to_node) if lbl < len(subgraph.local_nodes)
    }
    all_nodes = {lbl: node_coords[lbl] for lbl in parent_node_labels}
    all_nodes.update(kept_extra_nodes)
    if src_anchor not in all_nodes:
        all_nodes[src_anchor] = node_coords[src_anchor]
    if tgt_anchor not in all_nodes:
        all_nodes[tgt_anchor] = node_coords[tgt_anchor]

    inmem_map = build_inmem_map(all_nodes)
    for se in kept:
        inmem_map.add_edge(se.from_node, se.to_node)

    return LegMap(inmem_map=inmem_map, sub_edges=kept, src_anchor=src_anchor, tgt_anchor=tgt_anchor)


@dataclasses.dataclass
class DecodeFailure:
    trace_index: int
    lon: float
    lat: float
    nearest_candidate_dist_m: float


def match_trace(leg_map: LegMap, trace: list, obs_noise_m: float, max_dist_m: float,
                 dist_noise_m: float):
    """Viterbi-decodes `trace` (resampled, (lon, lat)) against leg_map.inmem_map (spec §3).
    non_emitting_states=True lets the decode traverse intermediate edges between two distant
    observations without demanding an observation for each - the mechanism that also performs
    spec §2's "shortest sub-path between consecutive Viterbi-selected states" concatenation
    internally, so this function does not re-derive that itself.

    Returns the ordered list of InMemMap node labels the winning path visits (including every
    intermediate node from non-emitting stretches), or a DecodeFailure if the decode could not
    cover the whole trace (spec §4).

    Note: DistanceMatcher.node_path is a plain attribute (a list of visited (from, to) state
    pairs), not a method - matcher.node_path_to_only_nodes() flattens it to the ordered node-label
    list this function returns. Confirmed against the installed leuvenmapmatching 1.1.4; the
    installed InMemMap also has no all_node_coordinates()-style accessor, so DecodeFailure's
    nearest-candidate distance is computed from leg_map.inmem_map.all_nodes() instead."""
    latlon_trace = [_latlon(p) for p in trace]
    matcher = DistanceMatcher(
        leg_map.inmem_map, max_dist=max_dist_m, obs_noise=obs_noise_m, dist_noise=dist_noise_m,
        non_emitting_states=True,
    )
    _, last_idx = matcher.match(latlon_trace, unique=False)

    if last_idx is None or last_idx < len(latlon_trace) - 1:
        failed_at = 0 if last_idx is None else last_idx + 1
        lat, lon = latlon_trace[failed_at]
        nearest = min(
            (haversine_m(lon, lat, *_lonlat(coord))
             for _, coord in leg_map.inmem_map.all_nodes()),
            default=float("inf"),
        )
        return DecodeFailure(trace_index=failed_at, lon=lon, lat=lat,
                              nearest_candidate_dist_m=nearest)

    node_path = matcher.node_path_to_only_nodes(matcher.node_path)
    if not node_path:
        lat, lon = latlon_trace[0]
        return DecodeFailure(trace_index=0, lon=lon, lat=lat, nearest_candidate_dist_m=float("inf"))
    return node_path
