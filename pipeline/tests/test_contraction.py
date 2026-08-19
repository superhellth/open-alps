import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.contraction import contract_structural  # noqa: E402


def _chain_fixture():
    # 0 -- 1 -- 2 -- 3 -- 4 : a straight chain, nodes 1/2/3 are degree-2 (contractible),
    # 0 and 4 are degree-1 (dead-ends, keep-nodes).
    coords = np.array([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0), (4.0, 0.0)])
    edges_i = np.array([0, 1, 2, 3])
    edges_j = np.array([1, 2, 3, 4])
    edges_dist = np.array([100.0, 100.0, 100.0, 100.0])
    edges_weight = np.array([100.0, 100.0, 130.0, 100.0])  # segment 2-3 road-penalized
    edges_road = np.array([False, False, True, False])
    edges_sac_rank = np.array([1, 1, -1, 2], dtype=np.int8)
    edges_via_ferrata = np.array([False, False, False, True])
    return coords, edges_i, edges_j, edges_dist, edges_weight, edges_road, edges_sac_rank, \
        edges_via_ferrata


def test_straight_chain_collapses_to_one_edge():
    result = contract_structural(*_chain_fixture())
    assert len(result.coords) == 2  # only nodes 0 and 4 survive
    assert len(result.edges_u) == 1
    assert result.edges_dist[0] == 400.0


def test_contraction_sums_road_m_only_for_road_segments():
    result = contract_structural(*_chain_fixture())
    assert result.edges_road_m[0] == 100.0  # only the 2-3 segment was road-penalized


def test_contraction_takes_max_sac_rank_along_chain():
    result = contract_structural(*_chain_fixture())
    assert result.edges_sac_rank[0] == 2


def test_contraction_ors_via_ferrata_along_chain():
    result = contract_structural(*_chain_fixture())
    assert result.edges_via_ferrata[0] == True  # noqa: E712


def test_contraction_preserves_interior_polyline_in_order():
    result = contract_structural(*_chain_fixture())
    interior = result.interior_coords[0]
    assert [pt[0] for pt in interior] == [1.0, 2.0, 3.0]


def test_junction_node_is_not_contracted():
    # 0 -- 1 -- 2, plus a spur 1 -- 3: node 1 has degree 3, must stay a keep-node.
    coords = np.array([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (1.0, 1.0)])
    edges_i = np.array([0, 1, 1])
    edges_j = np.array([1, 2, 3])
    edges_dist = np.array([100.0, 100.0, 50.0])
    edges_weight = edges_dist.copy()
    edges_road = np.array([False, False, False])
    edges_sac_rank = np.array([-1, -1, -1], dtype=np.int8)
    edges_via_ferrata = np.array([False, False, False])

    result = contract_structural(
        coords, edges_i, edges_j, edges_dist, edges_weight, edges_road, edges_sac_rank,
        edges_via_ferrata,
    )

    assert len(result.coords) == 4  # nothing contracted away
    assert len(result.edges_u) == 3
