import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import binfmt  # noqa: E402
from lib import hub_snap  # noqa: E402
from lib.subgraph import LocalSubgraph  # noqa: E402

TYPE_HUT = binfmt.TYPE_HUT


def _line_subgraph(global_node_ids, edge_id):
    # Two nodes 1000m apart (roughly, at these latitudes), one edge - a hub snapping anywhere on
    # it lands mid-chain (segment_index=0). edge_id is the STABLE global id (EDGE_DTYPE's own
    # field), independent of this subgraph's local ordering.
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.009, 0.0, 0)
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 1000.0, 0.0, 0.0, 0.0, 1000.0, binfmt.UNSET, binfmt.UNSET, -1, False, True,
                False, 0, 0, edge_id)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    return LocalSubgraph(
        global_node_ids=np.array(global_node_ids), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.zeros(len(nodes), dtype=np.float32),
        interior_ele=np.zeros(len(interior), dtype=np.float32),
    )


def test_edge_snap_dz_uses_the_real_interior_elevation_not_an_endpoint_blend():
    # Both endpoints sit at 0m, but the trail climbs to 1000m at its midpoint (a real ridge the
    # chain-contracted edge crosses) - a distance-ratio blend of the two endpoints would predict
    # ~0m at the midpoint and wrongly report a huge gap_dz_m for a hub that actually sits right at
    # the ridge's real elevation.
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.009, 0.0, 0)
    interior = np.zeros(1, dtype=binfmt.COORD_DTYPE)
    interior[0] = (0.0045, 0.0)
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 1000.0, 0.0, 0.0, 0.0, 1000.0, binfmt.UNSET, binfmt.UNSET, -1, False, True,
                False, 0, 1, 7)
    subgraph = LocalSubgraph(
        global_node_ids=np.array([100, 101]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.zeros(2, dtype=np.float32),
        interior_ele=np.array([1000.0], dtype=np.float32),
    )

    result = hub_snap.snap_hub_to_subgraph(
        subgraph, hub_lon=0.0045, hub_lat=0.0002, max_snap_m=50.0,
        hub_ele_m=998.0, max_snap_ascent_m=25.0,
    )

    assert isinstance(result, hub_snap.SnapResult)
    assert result.gap_dz_m == pytest.approx(-2.0, abs=0.5)


def test_node_snap_round_trips_through_pack_and_load(tmp_path):
    # Coincides exactly with node 0 (also edge0's own u endpoint), so the node and mid-edge
    # candidates tie on distance - snap_hub_to_subgraph has no node preference, only a tie-break
    # toward the node so an exact coincidence doesn't spawn a redundant virtual vertex.
    subgraph = _line_subgraph([100, 101], edge_id=7)
    result = hub_snap.snap_hub_to_subgraph(subgraph, hub_lon=0.0, hub_lat=0.0, max_snap_m=50.0)
    assert result.node_index == 0

    persisted = hub_snap.to_persisted(subgraph, result)
    assert persisted.kind == binfmt.SNAP_KIND_NODE
    assert persisted.global_node_id == 100   # global_node_ids[0]

    hub_snap.pack_hub_snaps({(TYPE_HUT, 1): persisted}, tmp_path)
    arr = binfmt.load_array(tmp_path / "hub-snaps.npy", mmap=False)
    interior_arr = binfmt.load_array(tmp_path / "hub-snap-interior.npy", mmap=False)
    reloaded = hub_snap.load_persisted_snaps(arr, interior_arr)
    assert reloaded[(TYPE_HUT, 1)].global_node_id == 100


def test_edge_split_snap_round_trips_through_pack_and_load(tmp_path):
    subgraph = _line_subgraph([100, 101], edge_id=7)
    result = hub_snap.snap_hub_to_subgraph(subgraph, hub_lon=0.0045, hub_lat=0.0002, max_snap_m=50.0)
    assert result.split is not None

    persisted = hub_snap.to_persisted(subgraph, result)
    assert persisted.kind == binfmt.SNAP_KIND_EDGE
    assert persisted.global_edge_id == 7   # local_edges["edge_id"][0], NOT the local index 0

    hub_snap.pack_hub_snaps({(TYPE_HUT, 2): persisted}, tmp_path)
    arr = binfmt.load_array(tmp_path / "hub-snaps.npy", mmap=False)
    interior_arr = binfmt.load_array(tmp_path / "hub-snap-interior.npy", mmap=False)
    reloaded = hub_snap.load_persisted_snaps(arr, interior_arr)
    got = reloaded[(TYPE_HUT, 2)]
    assert got.global_edge_id == 7
    assert got.split_coord == result.split.split_coord
    assert got.dist_to_u == result.split.dist_to_u


def test_reconstruct_local_snaps_survives_a_different_subgraph_ordering():
    # The whole point of persisting by GLOBAL id: a node snap computed against one gather (small
    # buffer, node landing at LOCAL index 0) must still resolve correctly against a totally
    # different gather (large buffer) where the same GLOBAL node sits at a different local index
    # (here: index 1, with an extra unrelated node inserted before it).
    small_subgraph = _line_subgraph([100, 101], edge_id=7)
    result = hub_snap.snap_hub_to_subgraph(small_subgraph, hub_lon=0.0, hub_lat=0.0, max_snap_m=50.0)
    assert result.node_index == 0
    persisted = {(TYPE_HUT, 1): hub_snap.to_persisted(small_subgraph, result)}

    # A "larger" gather with an extra node (global id 99) inserted before global id 100 - global
    # id 100 now sits at local index 1, not 0.
    nodes = np.zeros(3, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (5.0, 5.0, 0)     # unrelated extra node, global id 99
    nodes[1] = (0.0, 0.0, 0)     # global id 100 - same node the small gather snapped to
    nodes[2] = (0.009, 0.0, 0)   # global id 101
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (1, 2, 1000.0, 0.0, 0.0, 0.0, 1000.0, binfmt.UNSET, binfmt.UNSET, -1, False, True,
                False, 0, 0, 7)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    large_subgraph = LocalSubgraph(
        global_node_ids=np.array([99, 100, 101]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.zeros(3, dtype=np.float32),
        interior_ele=np.zeros(0, dtype=np.float32),
    )

    local_snaps = hub_snap.reconstruct_local_snaps(large_subgraph, [(TYPE_HUT, 1)], persisted)
    assert local_snaps[(TYPE_HUT, 1)].node_index == 1  # NOT 0 - correctly re-resolved


def test_reconstruct_local_snaps_omits_a_key_missing_from_persisted():
    # A hub that snap_hubs.py rejected (SnapRejection) never gets a PersistedSnap entry - a
    # route-task cell asking for it must just skip it, not raise.
    subgraph = _line_subgraph([100, 101], edge_id=7)
    out = hub_snap.reconstruct_local_snaps(subgraph, [(TYPE_HUT, 999)], {})
    assert out == {}


def test_node_index_is_built_once_and_cached(monkeypatch):
    # D3: the KD-tree build (O(nodes log nodes)) must happen once per subgraph, not once per hub -
    # same caching contract _build_edge_spatial_index already has for the edge index.
    subgraph = _line_subgraph([100, 101], edge_id=7)
    calls = []
    real_build = hub_snap._build_node_spatial_index

    def _counting_build(sg):
        calls.append(1)
        return real_build(sg)

    monkeypatch.setattr(hub_snap, "_build_node_spatial_index", _counting_build)

    hub_snap.snap_hub_to_subgraph(subgraph, hub_lon=0.0001, hub_lat=0.0, max_snap_m=50.0)
    hub_snap.snap_hub_to_subgraph(subgraph, hub_lon=0.0002, hub_lat=0.0, max_snap_m=50.0)

    assert len(calls) == 1


def test_nearest_node_matches_the_closest_node_by_projected_distance():
    subgraph = _line_subgraph([100, 101], edge_id=7)
    idx, dist_m = hub_snap._nearest_node(subgraph, hub_lon=0.0001, hub_lat=0.0)
    assert idx == 0
    assert dist_m == pytest.approx(11.1, rel=0.05)  # 0.0001 deg lon at the equator


def test_nearest_node_on_an_empty_subgraph_reports_no_candidate():
    empty = LocalSubgraph(
        global_node_ids=np.zeros(0, dtype=np.int64),
        local_nodes=np.zeros(0, dtype=binfmt.NODE_DTYPE),
        local_edges=np.zeros(0, dtype=binfmt.EDGE_DTYPE),
        interior=np.zeros(0, dtype=binfmt.COORD_DTYPE),
        local_node_ele=np.zeros(0, dtype=np.float32),
        interior_ele=np.zeros(0, dtype=np.float32),
    )
    idx, dist_m = hub_snap._nearest_node(empty, hub_lon=0.0, hub_lat=0.0)
    assert idx is None
    assert dist_m == float("inf")


def _random_subgraph(rng, n_nodes=60, n_edges=120, span_deg=0.06):
    # Mix of short wiggly edges and a few very long straight ones (one segment >1km), so the
    # index's per-segment subdivision is exercised, not just vertex proximity.
    nodes = np.zeros(n_nodes, dtype=binfmt.NODE_DTYPE)
    nodes["lon"] = 11.0 + rng.uniform(0, span_deg, n_nodes)
    nodes["lat"] = 47.0 + rng.uniform(0, span_deg, n_nodes)
    edges = np.zeros(n_edges, dtype=binfmt.EDGE_DTYPE)
    interior_pts = []
    for i in range(n_edges):
        u, v = rng.choice(n_nodes, 2, replace=False)
        n_int = 0 if i % 5 == 0 else int(rng.integers(1, 12))
        lon0, lat0 = nodes["lon"][u], nodes["lat"][u]
        lon1, lat1 = nodes["lon"][v], nodes["lat"][v]
        ts = np.sort(rng.uniform(0, 1, n_int))
        for t in ts:
            interior_pts.append((lon0 + t * (lon1 - lon0) + rng.normal(0, 3e-4),
                                 lat0 + t * (lat1 - lat0) + rng.normal(0, 3e-4)))
        edges[i]["u"], edges[i]["v"] = u, v
        edges[i]["dist"] = 500.0
        edges[i]["interior_offset"] = len(interior_pts) - n_int
        edges[i]["interior_count"] = n_int
        edges[i]["edge_id"] = 1000 + i
    interior = np.zeros(len(interior_pts), dtype=binfmt.COORD_DTYPE)
    if interior_pts:
        interior["lon"] = [p[0] for p in interior_pts]
        interior["lat"] = [p[1] for p in interior_pts]
    return LocalSubgraph(
        global_node_ids=np.arange(n_nodes), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=rng.uniform(1000, 1100, n_nodes).astype(np.float32),
        interior_ele=rng.uniform(1000, 1100, len(interior)).astype(np.float32),
    )


def _outcome(r):
    if isinstance(r, hub_snap.SnapRejection):
        return ("rej", r.reason, round(r.gap_m, 6), round(r.dz_m, 6))
    if r.node_index is not None:
        return ("node", r.node_index, round(r.gap_m, 6), round(r.gap_dz_m, 6))
    return ("edge", r.edge_local_index, r.split.split_coord, round(r.gap_m, 6),
            round(r.gap_dz_m, 6))


def test_candidate_index_snaps_identically_to_scanning_every_edge(monkeypatch):
    rng = np.random.default_rng(0)
    subgraph = _random_subgraph(rng)
    hubs = [(11.0 + rng.uniform(-0.005, 0.065), 47.0 + rng.uniform(-0.005, 0.065),
             float(rng.uniform(1000, 1100))) for _ in range(400)]
    # Include hubs sitting exactly on / very near an existing edge's midpoint.
    for e in subgraph.local_edges[:40]:
        u, v = subgraph.local_nodes[e["u"]], subgraph.local_nodes[e["v"]]
        hubs.append(((u["lon"] + v["lon"]) / 2 + 1e-5, (u["lat"] + v["lat"]) / 2 + 1e-5, 1050.0))

    for max_snap_m in (30.0, 100.0, 400.0):
        indexed = [_outcome(hub_snap.snap_hub_to_subgraph(
            subgraph, lon, lat, max_snap_m, hub_ele_m=ele, max_snap_ascent_m=25.0))
            for lon, lat, ele in hubs]
        with monkeypatch.context() as m:
            m.setattr(hub_snap, "_candidate_edges_near",
                      lambda sg, lon, lat, r: list(range(len(sg.local_edges))))
            brute = [_outcome(hub_snap.snap_hub_to_subgraph(
                subgraph, lon, lat, max_snap_m, hub_ele_m=ele, max_snap_ascent_m=25.0))
                for lon, lat, ele in hubs]
        assert indexed == brute
        assert any(o[0] == "edge" for o in indexed)


def test_candidate_index_finds_a_hub_beside_the_middle_of_a_very_long_segment():
    # One 4.5km straight edge, no interior vertices: the hub is ~2km from either endpoint, so a
    # vertex-only index would need a ~2km search radius to find it.
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.04, 0.0, 0)
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    edges[0]["u"], edges[0]["v"], edges[0]["edge_id"] = 0, 1, 5
    subgraph = LocalSubgraph(
        global_node_ids=np.array([0, 1]), local_nodes=nodes, local_edges=edges,
        interior=np.zeros(0, dtype=binfmt.COORD_DTYPE),
        local_node_ele=np.zeros(2, dtype=np.float32),
        interior_ele=np.zeros(0, dtype=np.float32),
    )
    assert hub_snap._candidate_edges_near(subgraph, 0.02, 0.0004, 100.0) == [0]
    assert hub_snap._candidate_edges_near(subgraph, 0.02, 0.0030, 100.0) == []


def test_candidate_set_stays_small_when_a_long_segment_exists_elsewhere():
    rng = np.random.default_rng(1)
    subgraph = _random_subgraph(rng)
    n = len(hub_snap._candidate_edges_near(subgraph, 11.03, 47.03, 100.0))
    assert n < len(subgraph.local_edges) // 4
