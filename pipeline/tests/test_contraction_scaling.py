import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases" / "graph_building"))

import build_base_graph as bbg  # noqa: E402
from lib import binfmt  # noqa: E402
from lib.contraction import ContractedGraph  # noqa: E402
from contraction_scaling import cells_by_density, pick_cell_sets, profile_one  # noqa: E402


def _nodes(cell_ids):
    nodes = np.zeros(len(cell_ids), dtype=binfmt.NODE_DTYPE)
    nodes["cell_id"] = cell_ids
    return nodes


def test_cells_by_density_orders_densest_first_and_drops_empty_cells():
    # cell 2 has 4 nodes, cell 0 has 2, cell 1 has 1, cell 3 has none
    nodes = _nodes([0, 0, 1, 2, 2, 2, 2])
    assert cells_by_density(nodes, n_cells=4) == [2, 0, 1]


def test_pick_cell_sets_returns_nested_prefixes_reaching_each_fraction():
    nodes = _nodes([0, 0, 1, 2, 2, 2, 2])  # 7 nodes total
    sets = pick_cell_sets(nodes, n_cells=4, fractions=[0.5, 1.0])

    assert [f for f, _ in sets] == [0.5, 1.0]
    half, whole = sets[0][1], sets[1][1]
    assert half == [2]                 # 4/7 >= 0.5 with the densest cell alone
    assert half == whole[:len(half)]   # nested: every step is a superset of the last
    assert set(whole) == {0, 1, 2}


def test_pick_cell_sets_never_returns_an_empty_set():
    nodes = _nodes([0, 0, 1, 2, 2, 2, 2])
    sets = pick_cell_sets(nodes, n_cells=4, fractions=[0.001])
    assert len(sets[0][1]) == 1


def test_profile_one_writes_a_prof_file_and_returns_a_table(tmp_path):
    # build a minimal on-disk base_graph so profile_one has something real to read
    contracted = ContractedGraph(
        coords=np.array([(11.0, 47.0), (11.1, 47.1), (11.2, 47.2)]),
        edges_u=np.array([0, 1], dtype=np.int64),
        edges_v=np.array([1, 2], dtype=np.int64),
        edges_dist=np.array([100.0, 200.0]),
        edges_weight=np.array([130.0, 200.0]),
        edges_road_m=np.array([100.0, 0.0]),
        edges_sac_rank=np.array([2, -1], dtype=np.int8),
        edges_via_ferrata=np.array([False, True]),
        interior_coords=[[(11.05, 47.05)], []],
    )
    graph_dir = tmp_path / "base_graph"
    bbg.pack_and_write(contracted, {"minLng": 8.9, "maxLng": 17.2,
                                    "minLat": 46.3, "maxLat": 50.6}, 60.0, graph_dir)

    prof_path = tmp_path / "contraction.prof"
    table = profile_one(graph_dir, fraction=1.0, out_path=prof_path)

    assert prof_path.exists()
    assert "contract_structural" in table
