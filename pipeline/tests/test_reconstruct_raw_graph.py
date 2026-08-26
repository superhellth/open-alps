import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))

from lib import binfmt  # noqa: E402
from lib.contraction import contract_structural  # noqa: E402
from reconstruct_raw_graph import _haversine_m_vec, reconstruct_raw, select_edges_in_cells  # noqa: E402


def _chain_dist(lons, lats):
    """Real haversine length of a polyline, so the fixture's persisted chain `dist` is what
    build_base_graph.py would actually have stored for these coordinates - otherwise the
    distance-identity test would compare against a made-up number."""
    lons, lats = np.asarray(lons), np.asarray(lats)
    return float(_haversine_m_vec(lons[:-1], lats[:-1], lons[1:], lats[1:]).sum())


def _fixture():
    """Three chain edges meeting at a REAL junction (node 1, degree 3):

         0 --[p0, p1]-- 1 --[]-- 2
                        |
                        3

    so the raw graph is 5 edges over 6 nodes. Node 1 must have degree >= 3, otherwise
    re-contracting the reconstruction legitimately merges its chains into one and the round-trip
    test would be asserting the wrong thing."""
    nodes = np.zeros(4, dtype=binfmt.NODE_DTYPE)
    nodes["lon"] = [11.0, 11.3, 11.4, 11.3]
    nodes["lat"] = [47.0, 47.0, 47.0, 47.1]
    nodes["cell_id"] = [0, 0, 1, 0]

    interior = np.zeros(2, dtype=binfmt.COORD_DTYPE)
    interior["lon"] = [11.1, 11.2]
    interior["lat"] = [47.0, 47.0]

    # chain 0: 11.0 -> 11.1 -> 11.2 -> 11.3 ; chain 1: 11.3 -> 11.4 ; chain 2: node 1 -> node 3
    d0 = _chain_dist([11.0, 11.1, 11.2, 11.3], [47.0] * 4)
    d1 = _chain_dist([11.3, 11.4], [47.0, 47.0])
    d2 = _chain_dist([11.3, 11.3], [47.0, 47.1])

    edges = np.zeros(3, dtype=binfmt.EDGE_DTYPE)
    edges["u"] = [0, 1, 1]
    edges["v"] = [1, 2, 3]
    edges["dist"] = [d0, d1, d2]
    edges["road_m"] = [d0, 0.0, 0.0]
    edges["ungraded_m"] = [0.0, d1, 0.0]
    edges["inferred_m"] = [0.0, 0.0, 0.0]
    edges["sac_rank"] = [3, -1, 0]
    edges["via_ferrata"] = [False, True, False]
    edges["constrained_ok"] = [True, False, True]
    edges["interior_offset"] = [0, 2, 2]
    edges["interior_count"] = [2, 0, 0]
    edges["edge_id"] = [0, 1, 2]
    return nodes, edges, interior


def test_reconstruct_expands_chains_into_per_segment_raw_edges():
    nodes, edges, interior = _fixture()
    raw = reconstruct_raw(nodes, edges, interior, np.arange(3))

    assert len(raw.coords) == 6          # 4 junctions + 2 interior points
    assert len(raw.edges_i) == 5         # (2+1) + (0+1) + (0+1) segments

    deg = np.bincount(np.concatenate([raw.edges_i, raw.edges_j]), minlength=6)
    assert sorted(deg.tolist()) == [1, 1, 1, 2, 2, 3]  # 3 dead-ends, 2 interior, 1 junction


def test_reconstruct_preserves_node_ordering_along_the_chain():
    nodes, edges, interior = _fixture()
    raw = reconstruct_raw(nodes, edges, interior, np.arange(3))
    # walking the reconstruction must recover the original left-to-right longitudes
    lons = sorted(raw.coords[:, 0].tolist())
    assert lons == pytest.approx([11.0, 11.1, 11.2, 11.3, 11.3, 11.4])


def test_recontracting_the_reconstruction_reproduces_the_original_chains():
    nodes, edges, interior = _fixture()
    raw = reconstruct_raw(nodes, edges, interior, np.arange(3))
    out = contract_structural(*raw.as_args())
    assert len(out.edges_u) == 3
    assert sorted(out.edges_sac_rank.tolist()) == [-1, 0, 3]
    assert sorted(int(len(p)) for p in out.interior_coords) == [0, 0, 2]
    assert sorted(out.edges_dist.tolist()) == pytest.approx(sorted(edges["dist"].tolist()))


def test_reconstructed_distances_sum_to_the_original_chain_distances():
    nodes, edges, interior = _fixture()
    raw = reconstruct_raw(nodes, edges, interior, np.arange(3))
    # segment haversines are recomputed from the same coords with the same formula, so the total
    # must match the persisted chain totals - this is what proves interior ordering is right
    assert raw.edges_dist.sum() == pytest.approx(float(edges["dist"].sum()), rel=1e-6)


def test_select_edges_in_cells_filters_by_the_u_endpoints_cell():
    nodes, edges, interior = _fixture()
    assert select_edges_in_cells(nodes, edges, {0}).tolist() == [0, 1, 2]
    assert select_edges_in_cells(nodes, edges, {1}).tolist() == []
