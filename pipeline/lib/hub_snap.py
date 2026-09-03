"""Hub-to-base-graph snapping (moved out of build_hub_edges.py so snap_hubs.py and
build_hub_edges.py can share it): finding the nearest graph node/mid-chain point to a hub, and
persisting/reconstructing that result across DIFFERENT LocalSubgraph gathers.

A SnapResult's node_index/edge_local_index are only meaningful within the ONE LocalSubgraph they
were computed against (they're positions into that gather's own local_nodes/local_edges arrays,
which differ gather to gather). To let snap_hubs.py compute a snap once (against a small,
max_snap_m-sized buffer) and build_hub_edges.py reuse it later (against its own, much larger,
max_edge_km-sized buffer, gathered independently), the snap is persisted keyed by GLOBAL ids that
are stable across any gather: LocalSubgraph.global_node_ids (a row index into base_graph/nodes.npy)
for a node snap, EDGE_DTYPE's own "edge_id" field (persisted on every edge, untouched by which
subgraph happens to include it) for a mid-chain split. reconstruct_local_snaps translates those
global ids back into whichever subgraph is asking, per docs/superpowers/plans/
2026-08-23-split-build-hub-edges.md."""

import math
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from lib import binfmt
from lib.edge_split import SplitResult, nearest_point_on_polyline, split_edge_at_point
from lib.geo import haversine_m as _haversine_m
from lib.geo import haversine_m_vec_pairs as _haversine_m_vec_pairs
from lib.grid import KM_PER_DEG_LAT, Grid
from lib.subgraph import LocalSubgraph


@dataclass
class SnapResult:
    node_index: int = None
    edge_local_index: int = None
    split: object = None  # lib.edge_split.SplitResult, only set when node_index is None
    # Straight-line hub-to-trail distance (spec E3: "the gap is currently free" - _path_for sums
    # only routed edges, so this contributes zero to distance/ascent/descent unless folded in by
    # the caller). gap_dz_m is hub_ele_m minus the snap point's own elevation (positive: hub sits
    # above the trail); it stays 0.0 - flat, not unknown - when the caller has no hub elevation.
    gap_m: float = 0.0
    gap_dz_m: float = 0.0


@dataclass
class SnapRejection:
    """A hub that could not be snapped (spec E3) - returned by snap_hub_to_subgraph instead of
    None, so it becomes a counted, reported fact (write_unsnapped_report) rather than a silent
    drop. hub_id/hub_type/name are filled in by the caller (snap_hub_to_subgraph only knows the
    hub's coordinate, not its identity); gap_m/dz_m/reason describe why it failed.

    reason:
      "no_trail_data"  - the padded cell around the hub has no trail data at all.
      "gap_too_far"    - trail data exists, but nothing is within max_snap_m.
      "vertical_offset" - a candidate is within max_snap_m, but |gap_dz_m| exceeds
                          max_snap_ascent_m (a hub joined to a trail it cannot physically reach,
                          e.g. across a gorge or up a face - not caught by a horizontal cap at
                          any setting, spec E3)."""
    gap_m: float
    dz_m: float
    reason: str
    hub_id: int = None
    hub_type: int = None
    name: str = ""


def _project_m(lon, lat, km_per_deg_lng: float):
    """Local equirectangular projection to meters, accurate enough at the scale of one padded
    cell (tens of km) - same simplification nearest_point_on_polyline already relies on."""
    return lon * km_per_deg_lng * 1000.0, lat * KM_PER_DEG_LAT * 1000.0


def _build_edge_spatial_index(subgraph: LocalSubgraph):
    """Indexes every polyline vertex (endpoints + interior points) of every local edge in a
    cKDTree, tagged with the owning edge_local_index, so snap_hub_to_subgraph's edge scan can
    query a small candidate set instead of looping every edge. Built once per cell (called once,
    then cached on the subgraph) rather than once per hub - this is what turns the old
    candidates * edges Python loop into edges (build) + candidates * log(edges) (query).

    Correctness: the true nearest point on a polyline segment can lie strictly between its two
    vertices, so a hub within max_snap_m of that point isn't necessarily within max_snap_m of a
    vertex - it can be up to max_snap_m + segment_length away from the nearest vertex (triangle
    inequality). Query radius therefore pads max_snap_m by this cell's longest single segment
    (max_seg_len_m), computed once here, not by max_snap_m alone.

    Vectorized (binfmt.gather_ragged/ragged_positions) rather than a per-edge Python loop with
    per-point scalar structured-array access - was the hot path on a 60km cell with thousands of
    edges * tens-hundreds of interior points each."""
    local_edges = subgraph.local_edges
    n_edges = len(local_edges)
    if n_edges == 0:
        return None
    ref_lat = float(np.mean(subgraph.local_nodes["lat"])) if len(subgraph.local_nodes) else 0.0
    km_per_deg_lng = KM_PER_DEG_LAT * math.cos(math.radians(ref_lat))

    u_lon = subgraph.local_nodes["lon"][local_edges["u"]]
    u_lat = subgraph.local_nodes["lat"][local_edges["u"]]
    v_lon = subgraph.local_nodes["lon"][local_edges["v"]]
    v_lat = subgraph.local_nodes["lat"][local_edges["v"]]

    # Every edge's interior points gathered in one pass; group_ids[k] is which local edge
    # interior_pts[k] belongs to, in original (offset) order within each edge.
    interior_pts, group_ids = binfmt.gather_ragged(
        subgraph.interior, local_edges["interior_offset"], local_edges["interior_count"],
    )
    interior_lon, interior_lat = interior_pts["lon"], interior_pts["lat"]

    # Point order doesn't matter for the KDTree itself (only the edge_id tag per point does) -
    # true polyline order is only needed below, for max_seg_len_m.
    all_lon = np.concatenate([u_lon, interior_lon, v_lon])
    all_lat = np.concatenate([u_lat, interior_lat, v_lat])
    edge_ids = np.concatenate([np.arange(n_edges), group_ids, np.arange(n_edges)])
    xs, ys = _project_m(all_lon, all_lat, km_per_deg_lng)

    # True per-edge polyline order (u -> interior in offset order -> v), reconstructed via a
    # position key + lexsort, needed only to compute real consecutive-segment lengths.
    counts = local_edges["interior_count"].astype(np.int64)
    pos = np.concatenate([np.zeros(n_edges, dtype=np.int64),
                           binfmt.ragged_positions(counts) + 1, counts + 1])
    order = np.lexsort((pos, edge_ids))
    ordered_edge_ids, ordered_lon, ordered_lat = edge_ids[order], all_lon[order], all_lat[order]
    max_seg_len_m = 0.0
    if len(ordered_edge_ids) > 1:
        same_next = ordered_edge_ids[:-1] == ordered_edge_ids[1:]
        if np.any(same_next):
            seg_lens = _haversine_m_vec_pairs(
                ordered_lon[:-1][same_next], ordered_lat[:-1][same_next],
                ordered_lon[1:][same_next], ordered_lat[1:][same_next],
            )
            max_seg_len_m = float(seg_lens.max())

    tree = cKDTree(np.column_stack([xs, ys]))
    return tree, edge_ids, max_seg_len_m, km_per_deg_lng


def _build_node_spatial_index(subgraph: LocalSubgraph):
    """cKDTree over every LOCAL node's projected (x, y) position, cached on the subgraph exactly
    the way _build_edge_spatial_index's edge index already is (D3: this used to be a full
    _haversine_m_vec scan over every node, once per hub - O(hubs x nodes) on a subgraph that can
    hold hundreds of thousands of nodes after A widens the candidate set)."""
    if len(subgraph.local_nodes) == 0:
        return None
    ref_lat = float(np.mean(subgraph.local_nodes["lat"]))
    km_per_deg_lng = KM_PER_DEG_LAT * math.cos(math.radians(ref_lat))
    xs, ys = _project_m(subgraph.local_nodes["lon"], subgraph.local_nodes["lat"], km_per_deg_lng)
    tree = cKDTree(np.column_stack([xs, ys]))
    return tree, km_per_deg_lng


def _nearest_node(subgraph: LocalSubgraph, hub_lon: float, hub_lat: float) -> tuple:
    """(local_node_index, distance_m) for the nearest existing graph node to (hub_lon, hub_lat),
    via the cached cKDTree above. distance_m is in the same local equirectangular-projected-metres
    space _build_edge_spatial_index already uses for its own candidate search, not exact
    haversine - close enough at cell scale (tens of km), and the tie-break between two nodes
    equidistant to within projection error can differ from the old exact-haversine argmin (D3);
    irrelevant to output quality. Returns (None, inf) when the subgraph has no nodes at all."""
    index = getattr(subgraph, "_node_spatial_index", "unset")
    if index == "unset":
        index = _build_node_spatial_index(subgraph)
        subgraph._node_spatial_index = index
    if index is None:
        return None, float("inf")
    tree, km_per_deg_lng = index
    x, y = _project_m(hub_lon, hub_lat, km_per_deg_lng)
    dist, idx = tree.query([x, y], k=1)
    return int(idx), float(dist)


def _candidate_edges_near(subgraph: LocalSubgraph, hub_lon: float, hub_lat: float,
                           max_snap_m: float) -> list:
    index = getattr(subgraph, "_edge_spatial_index", "unset")
    if index == "unset":
        index = _build_edge_spatial_index(subgraph)
        subgraph._edge_spatial_index = index
    if index is None:
        return []
    tree, edge_ids, max_seg_len_m, km_per_deg_lng = index
    x, y = _project_m(hub_lon, hub_lat, km_per_deg_lng)
    point_idxs = tree.query_ball_point([x, y], r=max_snap_m + max_seg_len_m)
    return sorted(set(edge_ids[point_idxs].tolist()))


def snap_hub_to_subgraph(subgraph: LocalSubgraph, hub_lon: float, hub_lat: float,
                          max_snap_m: float, hub_ele_m: float = None,
                          max_snap_ascent_m: float = None) -> "SnapResult | SnapRejection":
    """hub_ele_m: the hub's own elevation (spec E3), sampled from the SAME DEM as
    local_node_ele/interior_ele so gap_dz_m measures real terrain rather than the offset between
    two independently-sourced elevation datasets. None (the default) means unknown - gap_dz_m
    stays 0.0 rather than guessing, and no vertical check is possible.

    max_snap_ascent_m: reject a within-range candidate whose |gap_dz_m| exceeds it - only
    enforced when hub_ele_m is also given (spec E3: a horizontal cap alone cannot tell "18m
    across a terrace" from "18m up a wall", but it can't check what it doesn't know either).

    Never returns bare None: a hub that cannot snap - at any distance, or past the vertical cap -
    comes back as a SnapRejection instead, so it's counted rather than silently vanishing."""
    no_trail_data = len(subgraph.local_nodes) == 0 and len(subgraph.local_edges) == 0
    best_node_i, best_node_d = None, float("inf")
    # Both a node candidate and a mid-edge candidate are always found (when in range) and
    # compared on distance alone - a hut can sit right next to a through-trail while its nearest
    # actual graph node is a much farther dead-end spur (real case: hub_snap picking a 57m spur
    # over a 0.7m-away through-trail forced every route out of that hut to detour to the spur and
    # back, showing up as a spurious self-retrace in the routed geometry). Preferring the node
    # unconditionally traded that off against only avoiding a near-duplicate virtual vertex a few
    # metres from an existing one - not worth it once the gap between the two candidates can be
    # tens of metres.
    if len(subgraph.local_nodes) > 0:
        best_node_i, best_node_d = _nearest_node(subgraph, hub_lon, hub_lat)

    best_edge = None  # (dist_m, edge_local_index, split)
    for ei in _candidate_edges_near(subgraph, hub_lon, hub_lat, max_snap_m):
        e = subgraph.local_edges[ei]
        interior = [
            (subgraph.interior[j]["lon"], subgraph.interior[j]["lat"])
            for j in range(e["interior_offset"], e["interior_offset"] + e["interior_count"])
        ]
        u = subgraph.local_nodes[e["u"]]
        v = subgraph.local_nodes[e["v"]]
        polyline = [(u["lon"], u["lat"]), *interior, (v["lon"], v["lat"])]
        lng_scale = math.cos(math.radians(hub_lat))
        seg_idx, frac = nearest_point_on_polyline(polyline, (hub_lon, hub_lat), lng_scale)
        px = polyline[seg_idx][0] + frac * (polyline[seg_idx + 1][0] - polyline[seg_idx][0])
        py = polyline[seg_idx][1] + frac * (polyline[seg_idx + 1][1] - polyline[seg_idx][1])
        d = _haversine_m(hub_lon, hub_lat, px, py)
        if d <= max_snap_m and (best_edge is None or d < best_edge[0]):
            split = split_edge_at_point(
                (u["lon"], u["lat"]), (v["lon"], v["lat"]), interior,
                float(e["dist"]), float(e["road_m"]), float(e["ungraded_m"]),
                float(e["inferred_m"]), seg_idx, frac,
            )
            best_edge = (d, ei, split, e["u"], e["v"])

    best_edge_d = best_edge[0] if best_edge is not None else float("inf")
    node_in_range = best_node_d <= max_snap_m
    edge_in_range = best_edge_d <= max_snap_m

    if not node_in_range and not edge_in_range:
        # The nearer of the two misses (if any candidates exist at all) is the most informative
        # distance to report even though neither qualified - it tells the report how far away the
        # nearest trail data actually was, not just that nothing qualified.
        reason = "no_trail_data" if no_trail_data else "gap_too_far"
        return SnapRejection(gap_m=min(best_node_d, best_edge_d), dz_m=0.0, reason=reason)

    # best_node_d comes from _nearest_node's projected-equirectangular cKDTree query, best_edge_d
    # from exact haversine - two different approximations of the same real-world distance, which
    # can disagree by well under a metre even when the node and the edge's nearest point are the
    # SAME physical location (e.g. the node sits exactly at that edge's own endpoint). Without
    # slack, that measurement noise alone could flip the pick and spawn a redundant virtual vertex
    # a hair from an existing node - tiny next to the tens-of-metres gaps this comparison exists
    # to catch.
    _TIE_EPSILON_M = 1.0
    if node_in_range and (not edge_in_range or best_node_d <= best_edge_d + _TIE_EPSILON_M):
        gap_m = best_node_d
        gap_dz_m = (0.0 if hub_ele_m is None
                    else float(hub_ele_m) - float(subgraph.local_node_ele[best_node_i]))
        if (max_snap_ascent_m is not None and hub_ele_m is not None
                and abs(gap_dz_m) > max_snap_ascent_m):
            return SnapRejection(gap_m=gap_m, dz_m=gap_dz_m, reason="vertical_offset")
        return SnapResult(node_index=best_node_i, gap_m=gap_m, gap_dz_m=gap_dz_m)

    d, edge_local_index, split, u_idx, v_idx = best_edge
    gap_dz_m = 0.0
    if hub_ele_m is not None:
        # Snap-point elevation: the same distance-ratio blend split_edge_at_point already uses to
        # apportion ungraded_m/inferred_m across the two synthetic halves - not either endpoint's
        # raw value, since the split point usually sits strictly between them.
        u_ele = float(subgraph.local_node_ele[u_idx])
        v_ele = float(subgraph.local_node_ele[v_idx])
        total = split.dist_to_u + split.dist_to_v
        ratio = split.dist_to_u / total if total > 0 else 0.0
        snap_ele = u_ele + (v_ele - u_ele) * ratio
        gap_dz_m = float(hub_ele_m) - snap_ele
    if (max_snap_ascent_m is not None and hub_ele_m is not None
            and abs(gap_dz_m) > max_snap_ascent_m):
        return SnapRejection(gap_m=float(d), dz_m=gap_dz_m, reason="vertical_offset")
    return SnapResult(edge_local_index=edge_local_index, split=split, gap_m=float(d), gap_dz_m=gap_dz_m)


def write_unsnapped_report(path, rejections: list) -> None:
    """Emits data/osm/unsnapped_huts.json (spec E3) - the report that turns a hub failing to
    snap into a countable, visible fact instead of a silent drop (956 hubs measured, 205
    unsnapped, data/analysis/snap_stats.json - before any vertical cap even applied). Sorted by
    |dz_m| descending so the worst vertical outliers (bivouac boxes on walls) surface first."""
    import json

    rows = sorted(rejections, key=lambda r: abs(r.dz_m), reverse=True)
    payload = [
        {"hub_id": r.hub_id, "hub_type": r.hub_type, "name": r.name,
         "gap_m": r.gap_m, "dz_m": r.dz_m, "reason": r.reason}
        for r in rows
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")


def sample_hub_elevations(dem_path, hubs: list, grid: Grid, buffer_km: float = 0.2) -> None:
    """Fills each hub dict's "ele" key in place by sampling data/dem/dem.tif at the hub's own
    coordinate (spec E3), bilinear, per grid cell - same sampler and windowing strategy as
    elevation/sample_base_elevation.py's node/interior pass, so a hub's elevation and its snap
    point's elevation (node_ele.npy/interior_ele.npy, sampled from the same raster) agree on
    terrain rather than on two independently-sourced elevation datasets. Measured 2026-08-23
    against the ArcGIS hut layer's own `meereshoehe` field: median disagreement 3.9 m, but the
    tail (p99 265 m) is ArcGIS's own field being missing or wrong for entries that aren't real
    Alpine Club huts, not DEM error - and this project's snap point is already on this DEM, so
    sampling the hub from anywhere else would just import a second dataset's noise into gap_dz_m.

    Left at None when a hub falls outside DEM coverage - snap_hub_to_subgraph already treats
    hub_ele_m=None as "unknown" (gap_dz_m stays 0.0), not "flat"."""
    import rasterio
    import rasterio.windows

    from elevation.sample_base_elevation import sample_bilinear

    by_cell = {}
    for h in hubs:
        by_cell.setdefault(grid.cell_id_for_point(h["lon"], h["lat"]), []).append(h)

    with rasterio.open(dem_path) as dem:
        nodata = dem.nodata
        for cell_id, cell_hubs in by_cell.items():
            bounds = grid.padded_bounds(cell_id, buffer_km)
            window = rasterio.windows.from_bounds(
                bounds["minLng"], bounds["minLat"], bounds["maxLng"], bounds["maxLat"],
                transform=dem.transform,
            ).round_offsets().round_lengths()
            window = window.intersection(rasterio.windows.Window(0, 0, dem.width, dem.height))
            if window.width <= 0 or window.height <= 0:
                continue
            band = dem.read(1, window=window)
            window_transform = rasterio.windows.transform(window, dem.transform)
            lons = np.array([h["lon"] for h in cell_hubs])
            lats = np.array([h["lat"] for h in cell_hubs])
            eles = sample_bilinear(band, window_transform, lons, lats)
            for h, ele in zip(cell_hubs, eles.tolist()):
                h["ele"] = None if (nodata is not None and ele == nodata) else float(ele)


@dataclass
class PersistedSnap:
    """A SnapResult translated into subgraph-independent, globally-stable ids (see this module's
    docstring) - what actually gets packed into hub_snaps.npy."""
    kind: int  # binfmt.SNAP_KIND_NODE or SNAP_KIND_EDGE
    global_node_id: int = -1
    global_edge_id: int = -1
    split_coord: tuple = None
    dist_to_u: float = 0.0
    dist_to_v: float = 0.0
    road_m_to_u: float = 0.0
    road_m_to_v: float = 0.0
    ungraded_m_to_u: float = 0.0
    ungraded_m_to_v: float = 0.0
    inferred_m_to_u: float = 0.0
    inferred_m_to_v: float = 0.0
    interior_to_u: list = None
    interior_to_v: list = None
    gap_m: float = 0.0
    gap_dz_m: float = 0.0


def to_persisted(subgraph: LocalSubgraph, snap: SnapResult) -> PersistedSnap:
    """Reads off the global id (node row in nodes.npy, or EDGE_DTYPE's edge_id) that makes `snap`
    - computed against `subgraph` - reconstructible against a completely different gather."""
    if snap.node_index is not None:
        return PersistedSnap(
            kind=binfmt.SNAP_KIND_NODE,
            global_node_id=int(subgraph.global_node_ids[snap.node_index]),
            gap_m=snap.gap_m, gap_dz_m=snap.gap_dz_m,
        )
    split = snap.split
    return PersistedSnap(
        kind=binfmt.SNAP_KIND_EDGE,
        global_edge_id=int(subgraph.local_edges["edge_id"][snap.edge_local_index]),
        split_coord=split.split_coord,
        dist_to_u=split.dist_to_u, dist_to_v=split.dist_to_v,
        road_m_to_u=split.road_m_to_u, road_m_to_v=split.road_m_to_v,
        ungraded_m_to_u=split.ungraded_m_to_u, ungraded_m_to_v=split.ungraded_m_to_v,
        inferred_m_to_u=split.inferred_m_to_u, inferred_m_to_v=split.inferred_m_to_v,
        interior_to_u=list(split.interior_to_u), interior_to_v=list(split.interior_to_v),
        gap_m=snap.gap_m, gap_dz_m=snap.gap_dz_m,
    )


def pack_hub_snaps(snaps: dict, out_dir) -> None:
    """snaps: {(hub_type, hub_id): PersistedSnap}. Mirrors build_hub_edges.py's
    _write_edge_output flat-geometry packing: one growing COORD_DTYPE array for every split's
    interior_to_u/interior_to_v points, each row's *_offset/*_count pointing into it."""
    records = np.zeros(len(snaps), dtype=binfmt.HUB_SNAP_DTYPE)
    flat_interior = []
    cursor = 0
    for i, ((hub_type, hub_id), p) in enumerate(snaps.items()):
        if p.kind == binfmt.SNAP_KIND_NODE:
            records[i] = (
                hub_type, hub_id, p.kind, p.global_node_id, -1,
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                0, 0, 0, 0, p.gap_m, p.gap_dz_m,
            )
            continue
        u_off = cursor
        flat_interior.extend(p.interior_to_u)
        cursor += len(p.interior_to_u)
        v_off = cursor
        flat_interior.extend(p.interior_to_v)
        cursor += len(p.interior_to_v)
        records[i] = (
            hub_type, hub_id, p.kind, -1, p.global_edge_id,
            p.split_coord[0], p.split_coord[1],
            p.dist_to_u, p.dist_to_v, p.road_m_to_u, p.road_m_to_v,
            p.ungraded_m_to_u, p.ungraded_m_to_v, p.inferred_m_to_u, p.inferred_m_to_v,
            u_off, len(p.interior_to_u), v_off, len(p.interior_to_v),
            p.gap_m, p.gap_dz_m,
        )

    interior_arr = np.zeros(len(flat_interior), dtype=binfmt.COORD_DTYPE)
    if flat_interior:
        interior_arr["lon"] = [c[0] for c in flat_interior]
        interior_arr["lat"] = [c[1] for c in flat_interior]

    binfmt.save_array(out_dir / "hub_snaps.npy", records)
    binfmt.save_array(out_dir / "hub_snap_interior.npy", interior_arr)


def load_persisted_snaps(hub_snaps_arr: np.ndarray, interior_arr: np.ndarray) -> dict:
    """Inverse of pack_hub_snaps - returns {(hub_type, hub_id): PersistedSnap}."""
    out = {}
    for r in hub_snaps_arr:
        key = (int(r["hub_type"]), int(r["hub_id"]))
        if int(r["kind"]) == binfmt.SNAP_KIND_NODE:
            out[key] = PersistedSnap(
                kind=binfmt.SNAP_KIND_NODE, global_node_id=int(r["global_node_id"]),
                gap_m=float(r["gap_m"]), gap_dz_m=float(r["gap_dz_m"]),
            )
            continue
        u_off, u_cnt = int(r["interior_to_u_offset"]), int(r["interior_to_u_count"])
        v_off, v_cnt = int(r["interior_to_v_offset"]), int(r["interior_to_v_count"])
        interior_to_u = list(zip(
            interior_arr["lon"][u_off:u_off + u_cnt].tolist(),
            interior_arr["lat"][u_off:u_off + u_cnt].tolist(),
        ))
        interior_to_v = list(zip(
            interior_arr["lon"][v_off:v_off + v_cnt].tolist(),
            interior_arr["lat"][v_off:v_off + v_cnt].tolist(),
        ))
        out[key] = PersistedSnap(
            kind=binfmt.SNAP_KIND_EDGE, global_edge_id=int(r["global_edge_id"]),
            split_coord=(float(r["split_lon"]), float(r["split_lat"])),
            dist_to_u=float(r["dist_to_u"]), dist_to_v=float(r["dist_to_v"]),
            road_m_to_u=float(r["road_m_to_u"]), road_m_to_v=float(r["road_m_to_v"]),
            ungraded_m_to_u=float(r["ungraded_m_to_u"]), ungraded_m_to_v=float(r["ungraded_m_to_v"]),
            inferred_m_to_u=float(r["inferred_m_to_u"]), inferred_m_to_v=float(r["inferred_m_to_v"]),
            interior_to_u=interior_to_u, interior_to_v=interior_to_v,
            gap_m=float(r["gap_m"]), gap_dz_m=float(r["gap_dz_m"]),
        )
    return out


def reconstruct_local_snaps(subgraph: LocalSubgraph, keys, persisted: dict) -> dict:
    """Translates persisted (global-id) snaps back into subgraph-local SnapResult objects, for
    exactly the hub `keys` a cell's routing pass needs. A key missing from `persisted` (rejected
    at snap time, already reported by snap_hubs.py's own unsnapped_huts.json) or whose global
    node/edge id isn't present in THIS subgraph is simply omitted - the latter should not happen
    in practice (this subgraph's buffer_km is max_edge_km-sized, snap_hubs.py's buffer_km is
    max_snap_m-sized and max_snap_m << max_edge_km*1000 operationally, so any snap point - within
    max_snap_m of its hub - sits comfortably inside any padded region that already had to reach
    the hub itself to consider it a routing candidate), but is handled defensively rather than
    asserted, since a pathological config (max_snap_m close to max_edge_km*1000) could violate it."""
    out = {}
    node_id_to_local = None
    edge_id_to_local = None
    for key in keys:
        p = persisted.get(key)
        if p is None:
            continue
        if p.kind == binfmt.SNAP_KIND_NODE:
            if node_id_to_local is None:
                node_id_to_local = {int(g): i for i, g in enumerate(subgraph.global_node_ids)}
            local_i = node_id_to_local.get(p.global_node_id)
            if local_i is None:
                continue
            out[key] = SnapResult(node_index=local_i, gap_m=p.gap_m, gap_dz_m=p.gap_dz_m)
        else:
            if edge_id_to_local is None:
                edge_id_to_local = {
                    int(e): i for i, e in enumerate(subgraph.local_edges["edge_id"])
                }
            local_i = edge_id_to_local.get(p.global_edge_id)
            if local_i is None:
                continue
            split = SplitResult(
                split_coord=p.split_coord,
                dist_to_u=p.dist_to_u, dist_to_v=p.dist_to_v,
                road_m_to_u=p.road_m_to_u, road_m_to_v=p.road_m_to_v,
                ungraded_m_to_u=p.ungraded_m_to_u, ungraded_m_to_v=p.ungraded_m_to_v,
                inferred_m_to_u=p.inferred_m_to_u, inferred_m_to_v=p.inferred_m_to_v,
                interior_to_u=p.interior_to_u, interior_to_v=p.interior_to_v,
            )
            out[key] = SnapResult(
                edge_local_index=local_i, split=split, gap_m=p.gap_m, gap_dz_m=p.gap_dz_m,
            )
    return out
