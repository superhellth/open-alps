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
    edges_road = np.array([False, False, True, False])
    edges_ungraded = np.array([100.0, 0.0, 0.0, 0.0])
    edges_inferred = np.array([0.0, 100.0, 0.0, 100.0])
    edges_sac_rank = np.array([1, 1, -1, 2], dtype=np.int8)
    edges_via_ferrata = np.array([False, False, False, True])
    edges_constrained_ok = np.array([False, True, True, True])
    return coords, edges_i, edges_j, edges_dist, edges_road, edges_ungraded, edges_inferred, \
        edges_sac_rank, edges_via_ferrata, edges_constrained_ok


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
    edges_road = np.array([False, False, False])
    edges_ungraded = np.array([100.0, 100.0, 50.0])
    edges_inferred = np.array([0.0, 0.0, 0.0])
    edges_sac_rank = np.array([-1, -1, -1], dtype=np.int8)
    edges_via_ferrata = np.array([False, False, False])
    edges_constrained_ok = np.array([False, False, False])

    result = contract_structural(
        coords, edges_i, edges_j, edges_dist, edges_road, edges_ungraded, edges_inferred,
        edges_sac_rank, edges_via_ferrata, edges_constrained_ok,
    )

    assert len(result.coords) == 4  # nothing contracted away
    assert len(result.edges_u) == 3


def test_contract_sums_grading_metres_along_a_chain():
    # 3-node chain, middle node degree 2 -> one contracted edge carrying the sums
    contracted = contract_structural(
        coords=np.array([[0.0, 0.0], [0.001, 0.0], [0.002, 0.0]]),
        edges_i=np.array([0, 1]), edges_j=np.array([1, 2]),
        edges_dist=np.array([100.0, 150.0]),
        edges_road=np.array([False, False]),
        edges_ungraded=np.array([100.0, 0.0]),
        edges_inferred=np.array([0.0, 150.0]),
        edges_sac_rank=np.array([-1, 1], dtype=np.int8),
        edges_via_ferrata=np.array([False, False]),
        edges_constrained_ok=np.array([False, True]),
        progress_every=0,
    )
    assert contracted.edges_ungraded_m[0] == 100.0
    assert contracted.edges_inferred_m[0] == 150.0
    # one ungraded segment poisons the whole contracted edge for every constrained row
    assert bool(contracted.edges_constrained_ok[0]) is False


def test_isolated_cycle_with_no_junction_is_not_silently_dropped():
    # A closed triangle: 0 -- 1 -- 2 -- 0. Every node has degree 2 (two incident edges each), so
    # there is no keep-node (degree != 2) anywhere on this ring - the case CORRECT-01 describes.
    coords = np.array([(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)])
    edges_i = np.array([0, 1, 2])
    edges_j = np.array([1, 2, 0])
    edges_dist = np.array([100.0, 100.0, 100.0])
    edges_road = np.array([False, False, False])
    edges_ungraded = np.array([0.0, 0.0, 0.0])
    edges_inferred = np.array([0.0, 0.0, 0.0])
    edges_sac_rank = np.array([1, 1, 1], dtype=np.int8)
    edges_via_ferrata = np.array([False, False, False])
    edges_constrained_ok = np.array([True, True, True])

    result = contract_structural(
        coords, edges_i, edges_j, edges_dist, edges_road, edges_ungraded, edges_inferred,
        edges_sac_rank, edges_via_ferrata, edges_constrained_ok,
    )

    # Today (before the fix): result.coords has 0 rows, result.edges_u has 0 entries - the whole
    # triangle vanished with no signal. After the fix, exactly one self-loop edge should be
    # emitted (one node kept as the loop's anchor, u == v, distance = 300.0, interior holding the
    # other two nodes' coordinates in ring order) - see contraction.py's isolated-cycle handling.
    assert len(result.coords) == 1
    assert len(result.edges_u) == 1
    assert result.edges_u[0] == result.edges_v[0]  # self-loop
    assert abs(result.edges_dist[0] - 300.0) < 1e-6
    assert len(result.interior_coords[0]) == 2  # the other two ring nodes
