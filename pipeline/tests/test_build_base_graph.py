import sys
from collections import namedtuple
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases" / "graph_building"))

import build_base_graph as bbg  # noqa: E402
from lib import binfmt  # noqa: E402
from lib.contraction import ContractedGraph  # noqa: E402

# namedtuple("W", "nodes tags"): nodes expose .ref and .location.lon/.lat/.valid(), mirroring
# osmium's Way/WayNode/Location API closely enough for WayGraphHandler.way() to run unmodified.
_FakeLocation = namedtuple("_FakeLocation", "lon lat")
_FakeLocation.valid = lambda self: True
_FakeNode = namedtuple("_FakeNode", "ref location")


def _fake_way(coords, tags):
    nodes = [_FakeNode(ref=i, location=_FakeLocation(lon=lon, lat=lat))
             for i, (lon, lat) in enumerate(coords)]
    return namedtuple("W", "nodes tags")(nodes=nodes, tags=tags)


def test_module_exposes_callable_phases_without_running_them():
    # Importing must not parse argv or touch the filesystem - the module is imported by
    # pipeline/analysis/ harnesses that pass their own arguments.
    for name in ("stream_osm", "handler_to_arrays", "contract", "pack_and_write", "main"):
        assert callable(getattr(bbg, name)), f"{name} missing or not callable"


def test_way_handler_accumulates_ungraded_metres():
    h = bbg.WayGraphHandler(road_tags=["service"], progress_every=0)
    h.way(_fake_way(coords=[(0.0, 0.0), (0.001, 0.0), (0.002, 0.0)], tags={"highway": "path"}))
    assert sum(h.edges_ungraded) > 0
    assert sum(h.edges_inferred) == 0
    assert all(rank == -1 for rank in h.edges_sac_rank)
    assert not any(h.edges_constrained_ok)


def test_way_handler_marks_implied_grade_as_inferred_and_passable():
    h = bbg.WayGraphHandler(road_tags=["service"], progress_every=0)
    h.way(_fake_way(coords=[(0.0, 0.0), (0.001, 0.0)], tags={"highway": "track"}))
    assert sum(h.edges_inferred) > 0
    assert sum(h.edges_ungraded) == 0
    assert h.edges_sac_rank == [1]
    assert h.edges_constrained_ok == [True]


def test_via_ferrata_is_never_constrained_passable():
    h = bbg.WayGraphHandler(road_tags=["service"], progress_every=0)
    h.way(_fake_way(coords=[(0.0, 0.0), (0.001, 0.0)],
                    tags={"highway": "path", "sac_scale": "hiking", "via_ferrata_scale": "A"}))
    assert h.edges_constrained_ok == [False]


def test_way_handler_no_longer_takes_a_road_penalty_factor():
    import inspect
    assert "road_penalty_factor" not in inspect.signature(bbg.WayGraphHandler.__init__).parameters


def test_contract_takes_the_ten_raw_arrays_so_main_can_free_the_handler_first(tmp_path,
                                                                              monkeypatch):
    # contract() must accept the already-converted arrays rather than the handler - that is what
    # lets main() drop the handler's ~12 GB of raw Python lists before contraction starts.
    import lib.timing as timing
    monkeypatch.setattr(timing, "TIMINGS_PATH", tmp_path / "timings.jsonl")

    # 0 -- 1 -- 2 : node 1 is degree-2, so this contracts to a single chain edge
    out = bbg.contract(
        np.array([(11.0, 47.0), (11.1, 47.0), (11.2, 47.0)]),
        np.array([0, 1], dtype=np.int64),
        np.array([1, 2], dtype=np.int64),
        np.array([100.0, 200.0]),
        np.array([False, False]),
        np.array([0.0, 0.0]),
        np.array([100.0, 200.0]),
        np.array([1, 2], dtype=np.int8),
        np.array([False, False]),
        np.array([True, True]),
    )
    assert len(out.edges_u) == 1
    assert out.edges_dist[0] == 300.0


def _tiny_contracted():
    # Two chain edges sharing node 1: 0 --(one interior pt)-- 1 --(no interior)-- 2
    return ContractedGraph(
        coords=np.array([(11.0, 47.0), (11.1, 47.1), (11.2, 47.2)]),
        edges_u=np.array([0, 1], dtype=np.int64),
        edges_v=np.array([1, 2], dtype=np.int64),
        edges_dist=np.array([100.0, 200.0]),
        edges_road_m=np.array([100.0, 0.0]),
        edges_ungraded_m=np.array([0.0, 200.0]),
        edges_inferred_m=np.array([100.0, 0.0]),
        edges_sac_rank=np.array([2, -1], dtype=np.int8),
        edges_via_ferrata=np.array([False, True]),
        edges_constrained_ok=np.array([True, False]),
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
    # time_s/ascent_m/descent_m are UNSET here - add_base_elevation.py fills them in a later pass
    assert (edges["time_s"] == binfmt.UNSET).all()


def test_main_drops_the_handler_before_contraction_starts(tmp_path, monkeypatch):
    # The ordering IS the optimization: with the handler still live through contraction, its raw
    # Python lists (~40M coord tuples, 41M-element int/float lists, and the 40M-entry
    # node_id_to_idx dict) sit alongside the numpy copies for the whole phase and push a 16 GiB
    # box into swap - that is what made the recorded run 3963s instead of ~150s. A later reorder
    # of main() would reintroduce it silently, since nothing about the OUTPUT changes.
    import weakref

    import lib.timing as timing
    monkeypatch.setattr(timing, "TIMINGS_PATH", tmp_path / "timings.jsonl")

    class FakeHandler:
        def __init__(self):
            # 0 -- 1 -- 2, same tiny chain as the contract() test above
            self.coords = [(11.0, 47.0), (11.1, 47.0), (11.2, 47.0)]
            self.edges_i, self.edges_j = [0, 1], [1, 2]
            self.edges_dist = [100.0, 200.0]
            self.edges_road = [False, False]
            self.edges_ungraded = [0.0, 0.0]
            self.edges_inferred = [100.0, 200.0]
            self.edges_sac_rank = [1, 2]
            self.edges_via_ferrata = [False, False]
            self.edges_constrained_ok = [True, True]

    # the weakref is the only handle the test keeps - a strong ref here would defeat the check
    handler_ref = {}

    def fake_stream_osm(trails_path, config):
        handler = FakeHandler()
        handler_ref["r"] = weakref.ref(handler)
        return handler

    real_contract = bbg.contract
    observed = {}

    def spying_contract(*raw_args, **kwargs):
        observed["handler_alive"] = handler_ref["r"]() is not None
        return real_contract(*raw_args, **kwargs)

    monkeypatch.setattr(bbg, "stream_osm", fake_stream_osm)
    monkeypatch.setattr(bbg, "contract", spying_contract)
    monkeypatch.setattr(bbg, "pack_and_write", lambda *a, **k: None)

    bbg.main(["--out-dir", str(tmp_path)])

    assert observed["handler_alive"] is False, (
        "handler was still referenced when contract() started - main() must convert to arrays "
        "and drop the handler first"
    )
