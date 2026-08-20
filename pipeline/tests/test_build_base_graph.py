import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases" / "graph_building"))

import build_base_graph as bbg  # noqa: E402
from lib import binfmt  # noqa: E402
from lib.contraction import ContractedGraph  # noqa: E402


def test_module_exposes_callable_phases_without_running_them():
    # Importing must not parse argv or touch the filesystem - the module is imported by
    # pipeline/analysis/ harnesses that pass their own arguments.
    for name in ("stream_osm", "contract", "pack_and_write", "main"):
        assert callable(getattr(bbg, name)), f"{name} missing or not callable"


def _tiny_contracted():
    # Two chain edges sharing node 1: 0 --(one interior pt)-- 1 --(no interior)-- 2
    return ContractedGraph(
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


def test_pack_and_write_emits_the_seven_base_graph_files(tmp_path):
    bbox = {"minLng": 8.9, "maxLng": 17.2, "minLat": 46.3, "maxLat": 50.6}
    bbg.pack_and_write(_tiny_contracted(), bbox, 60.0, tmp_path)

    for fname in ("nodes.npy", "cell_index.npy", "node_edge_index.npy", "node_edge_ids.npy",
                  "edges.npy", "interior.npy", "manifest.json"):
        assert (tmp_path / fname).exists(), f"{fname} not written"

    nodes = binfmt.load_array(tmp_path / "nodes.npy")
    edges = binfmt.load_array(tmp_path / "edges.npy")
    interior = binfmt.load_array(tmp_path / "interior.npy")
    assert len(nodes) == 3
    assert len(edges) == 2
    assert len(interior) == 1
    # nodes are re-sorted by cell_id, so edge endpoints must be remapped, not raw indices
    assert set(edges["u"].tolist()) | set(edges["v"].tolist()) == {0, 1, 2}
    assert sorted(edges["dist"].tolist()) == [100.0, 200.0]
    assert interior["lon"][0] == pytest.approx(11.05)
