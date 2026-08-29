import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import binfmt  # noqa: E402
from lib.grid import Grid  # noqa: E402
from lib.subgraph import gather_padded_subgraph, load_local_subgraph, save_local_subgraph  # noqa: E402

BBOX = {"minLng": 0.0, "maxLng": 1.0, "minLat": 0.0, "maxLat": 1.0}


def _write_fixture_base_graph(tmp_path, grid):
    # 3 nodes spread across different cells of a fine grid, one edge each connecting neighbors.
    coords = [(0.05, 0.05), (0.95, 0.05), (0.05, 0.95)]
    cell_ids = [grid.cell_id_for_point(lon, lat) for lon, lat in coords]
    nodes = np.zeros(3, dtype=binfmt.NODE_DTYPE)
    for i, (c, cid) in enumerate(zip(coords, cell_ids)):
        nodes[i] = (c[0], c[1], cid)

    _, cell_index = binfmt.build_csr_index(
        np.array(cell_ids, dtype=np.int32), n_groups=len(grid.all_cell_ids())
    )
    # node_edge_index/ids built directly since nodes weren't reordered by build_csr_index's
    # `order` here (fixture already sorted node array to match cell_id ascending order below)
    edges = np.zeros(2, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 1000.0, 0.0, 0.0, 0.0, 1000.0, binfmt.UNSET, binfmt.UNSET, -1, False, True,
                0, 0, 0)
    edges[1] = (0, 2, 1000.0, 0.0, 0.0, 0.0, 1000.0, binfmt.UNSET, binfmt.UNSET, -1, False, True,
                0, 0, 1)
    doubled_nodes = np.concatenate([edges["u"], edges["v"]])
    doubled_edge_ids = np.concatenate([edges["edge_id"], edges["edge_id"]])
    order, node_edge_index = binfmt.build_csr_index(doubled_nodes, n_groups=3)
    node_edge_ids = doubled_edge_ids[order]
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)

    out_dir = tmp_path / "base_graph"
    binfmt.save_array(out_dir / "nodes.npy", nodes)
    binfmt.save_array(out_dir / "cell_index.npy", cell_index)
    binfmt.save_array(out_dir / "node_edge_index.npy", node_edge_index)
    binfmt.save_array(out_dir / "node_edge_ids.npy", node_edge_ids)
    binfmt.save_array(out_dir / "edges.npy", edges)
    binfmt.save_array(out_dir / "interior.npy", interior)
    return out_dir


def test_gather_includes_frontier_node_via_one_hop_closure():
    fine_grid = Grid(BBOX, tile_size_km=20.0)
    out_dir = _write_fixture_base_graph(_tmp_path_fixture(), fine_grid)
    cell_id = fine_grid.cell_id_for_point(0.05, 0.05)
    result = gather_padded_subgraph(out_dir, fine_grid, cell_id, buffer_km=1.0)
    # node 0's own cell alone wouldn't contain nodes 1/2 (far corners), but the edge-incidence
    # closure must still pull them in since edges from node 0 reach them directly.
    assert set(result.global_node_ids.tolist()) == {0, 1, 2}
    assert len(result.local_edges) == 2


def _write_fixture_base_graph_with_interior(tmp_path, grid):
    # Same 3-node/2-edge layout as _write_fixture_base_graph, but edge 0 (node 0 -> node 1) gets a
    # 2-point interior polyline - exercises the vectorized ragged-gather path in
    # _build_edge_spatial_index (build_hub_edges.py), which the zero-interior fixture above never
    # touches.
    coords = [(0.05, 0.05), (0.95, 0.05), (0.05, 0.95)]
    cell_ids = [grid.cell_id_for_point(lon, lat) for lon, lat in coords]
    nodes = np.zeros(3, dtype=binfmt.NODE_DTYPE)
    for i, (c, cid) in enumerate(zip(coords, cell_ids)):
        nodes[i] = (c[0], c[1], cid)

    _, cell_index = binfmt.build_csr_index(
        np.array(cell_ids, dtype=np.int32), n_groups=len(grid.all_cell_ids())
    )
    interior = np.zeros(2, dtype=binfmt.COORD_DTYPE)
    interior[0] = (0.35, 0.05)
    interior[1] = (0.65, 0.05)
    edges = np.zeros(2, dtype=binfmt.EDGE_DTYPE)
    # interior_offset=0, count=2
    edges[0] = (0, 1, 1000.0, 0.0, 0.0, 0.0, 1000.0, binfmt.UNSET, binfmt.UNSET, -1, False, True,
                0, 2, 0)
    edges[1] = (0, 2, 1000.0, 0.0, 0.0, 0.0, 1000.0, binfmt.UNSET, binfmt.UNSET, -1, False, True,
                0, 0, 1)
    doubled_nodes = np.concatenate([edges["u"], edges["v"]])
    doubled_edge_ids = np.concatenate([edges["edge_id"], edges["edge_id"]])
    order, node_edge_index = binfmt.build_csr_index(doubled_nodes, n_groups=3)
    node_edge_ids = doubled_edge_ids[order]

    out_dir = tmp_path / "base_graph"
    binfmt.save_array(out_dir / "nodes.npy", nodes)
    binfmt.save_array(out_dir / "cell_index.npy", cell_index)
    binfmt.save_array(out_dir / "node_edge_index.npy", node_edge_index)
    binfmt.save_array(out_dir / "node_edge_ids.npy", node_edge_ids)
    binfmt.save_array(out_dir / "edges.npy", edges)
    binfmt.save_array(out_dir / "interior.npy", interior)
    return out_dir


def test_gather_preserves_interior_offsets_for_downstream_lookup():
    # interior stays a lazy view over the full global array (not remapped per-subgraph), so
    # local_edges' interior_offset/interior_count must still address the *original* interior.npy
    # positions correctly after gather.
    fine_grid = Grid(BBOX, tile_size_km=20.0)
    out_dir = _write_fixture_base_graph_with_interior(_tmp_path_fixture(), fine_grid)
    cell_id = fine_grid.cell_id_for_point(0.05, 0.05)
    result = gather_padded_subgraph(out_dir, fine_grid, cell_id, buffer_km=1.0)

    assert set(result.global_node_ids.tolist()) == {0, 1, 2}
    edge0 = result.local_edges[result.local_edges["edge_id"] == 0][0]
    offset, count = int(edge0["interior_offset"]), int(edge0["interior_count"])
    pts = result.interior[offset:offset + count]
    assert list(zip(pts["lon"].tolist(), pts["lat"].tolist())) == [(0.35, 0.05), (0.65, 0.05)]
    # u/v were remapped to local indices via searchsorted over global_node_ids
    assert int(edge0["u"]) == int(np.searchsorted(result.global_node_ids, 0))
    assert int(edge0["v"]) == int(np.searchsorted(result.global_node_ids, 1))


def test_save_and_load_local_subgraph_round_trips():
    # gather_route_subgraphs.py's whole premise: a cached gather must reload identically to the
    # freshly-gathered one, including interior/interior_ele - which are deliberately NOT persisted
    # per-cell (save_local_subgraph's docstring) and must still resolve via the shared global
    # arrays reopened from base_graph_dir.
    fine_grid = Grid(BBOX, tile_size_km=20.0)
    base_graph_dir = _write_fixture_base_graph_with_interior(_tmp_path_fixture(), fine_grid)
    cell_id = fine_grid.cell_id_for_point(0.05, 0.05)
    original = gather_padded_subgraph(base_graph_dir, fine_grid, cell_id, buffer_km=1.0)

    cell_dir = _tmp_path_fixture() / "cell_cache"
    save_local_subgraph(original, cell_dir)
    reloaded = load_local_subgraph(cell_dir, base_graph_dir)

    assert reloaded.global_node_ids.tolist() == original.global_node_ids.tolist()
    assert reloaded.local_edges.tolist() == original.local_edges.tolist()
    assert reloaded.local_node_ele.tolist() == original.local_node_ele.tolist()
    # interior wasn't copied per-cell - reloaded via the shared base_graph_dir instead - but must
    # still resolve to the same points through the (unchanged) interior_offset/count on edge 0.
    edge0 = reloaded.local_edges[reloaded.local_edges["edge_id"] == 0][0]
    offset, count = int(edge0["interior_offset"]), int(edge0["interior_count"])
    pts = reloaded.interior[offset:offset + count]
    assert list(zip(pts["lon"].tolist(), pts["lat"].tolist())) == [(0.35, 0.05), (0.65, 0.05)]


def _tmp_path_fixture():
    import tempfile
    return Path(tempfile.mkdtemp())


from lib.subgraph import gather_subgraph_for_bounds  # noqa: E402


def test_gather_subgraph_for_bounds_excludes_far_away_nodes(tmp_path):
    fine_grid = Grid(BBOX, tile_size_km=20.0)
    base_graph_dir = _write_fixture_base_graph(tmp_path, fine_grid)
    # Tight bbox around only node 1's cell (0.95, 0.05) - node 0 gets pulled in by the one-hop
    # edge closure (edge 0-1), but node 2 at (0.05, 0.95) sits in a cell this bbox doesn't
    # overlap AND isn't the far endpoint of any edge incident to node 1, so it must stay excluded.
    # (A bbox that also overlaps node 0's cell would pull node 2 in too, via edge 0-2 - that's
    # the one-hop closure working as designed, not a bounds-filtering bug.)
    bounds = {"minLng": 0.9, "maxLng": 1.0, "minLat": 0.0, "maxLat": 0.1}
    subgraph = gather_subgraph_for_bounds(base_graph_dir, fine_grid, bounds)
    assert len(subgraph.local_nodes) == 2


def test_gather_subgraph_for_bounds_equals_padded_gather_on_same_effective_bounds(tmp_path):
    fine_grid = Grid(BBOX, tile_size_km=20.0)
    base_graph_dir = _write_fixture_base_graph(tmp_path, fine_grid)
    padded = fine_grid.padded_bounds(cell_id=fine_grid.cell_id_for_point(0.05, 0.05), buffer_km=5.0)
    direct = gather_subgraph_for_bounds(base_graph_dir, fine_grid, padded)
    via_wrapper = gather_padded_subgraph(
        base_graph_dir, fine_grid, fine_grid.cell_id_for_point(0.05, 0.05), buffer_km=5.0
    )
    assert list(direct.global_node_ids) == list(via_wrapper.global_node_ids)
    assert len(direct.local_edges) == len(via_wrapper.local_edges)
