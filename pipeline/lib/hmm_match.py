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

from leuvenmapmatching.map.inmem import InMemMap

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
