import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import binfmt  # noqa: E402
from lib.grid import Grid  # noqa: E402
from lib.subgraph import gather_padded_subgraph  # noqa: E402

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
    edges[0] = (0, 1, 1000.0, 1000.0, 0.0, -1, False, 0, 0, 0)
    edges[1] = (0, 2, 1000.0, 1000.0, 0.0, -1, False, 0, 0, 1)
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


def _tmp_path_fixture():
    import tempfile
    return Path(tempfile.mkdtemp())
