import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

import numpy as np
import pytest

from lib import binfmt  # noqa: E402
from lib.grid import Grid  # noqa: E402
from lib.hub_snap import PersistedSnap  # noqa: E402
from lib.subgraph import LocalSubgraph  # noqa: E402
from graph_building.match_tour_edges import corridor_bounds, match_leg  # noqa: E402

BBOX = {"minLng": 0.0, "maxLng": 1.0, "minLat": 0.0, "maxLat": 1.0}


def test_corridor_bounds_pads_the_points_bbox():
    grid = Grid(BBOX, tile_size_km=20.0)
    points = [(0.5, 0.5), (0.51, 0.5), (0.52, 0.5)]
    bounds = corridor_bounds(points, buffer_m=150.0, grid=grid)
    assert bounds["minLng"] < 0.5
    assert bounds["maxLng"] > 0.52
    assert bounds["minLat"] < 0.5
    assert bounds["maxLat"] > 0.5


def _line_subgraph_1000m():
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.009, 0.0, 0)  # ~1000m east at the equator
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 1000.0, 0.0, 0.0, 0.0, 1000.0, 30.0, 10.0, -1, False, True, 0, 0, 0)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    return LocalSubgraph(
        global_node_ids=np.array([100, 101]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.zeros(2, dtype=np.float32), interior_ele=np.zeros(0, dtype=np.float32),
    )


def _node_snap(global_node_id, gap_m=0.0, gap_dz_m=0.0):
    return PersistedSnap(kind=binfmt.SNAP_KIND_NODE, global_node_id=global_node_id,
                          gap_m=gap_m, gap_dz_m=gap_dz_m)


_HMM_KWARGS = dict(hmm_resample_m=25.0, hmm_obs_noise_m=25.0, hmm_max_dist_m=150.0,
                    hmm_dist_noise_m=25.0, endpoint_bridge_max_m=250.0)


def test_match_leg_routes_a_simple_corridor():
    subgraph = _line_subgraph_1000m()
    src_key, tgt_key = (binfmt.TYPE_HUT, 0), (binfmt.TYPE_HUT, 1)
    persisted = {src_key: _node_snap(100), tgt_key: _node_snap(101)}
    trace_points = [(0.0, 0.0), (0.009, 0.0)]  # ~1000m, matches _line_subgraph_1000m's own edge
    result = match_leg(subgraph, src_key, tgt_key, persisted, trace_points=trace_points,
                        length_divergence_ratio=2.0, **_HMM_KWARGS)
    assert result["ok"] is True
    # HMM matching computes distance from the actual node coordinates (haversine), not the
    # subgraph edge's own "dist" field - 0.009deg of longitude at the equator is ~1000.75m.
    assert result["path"].distance_m == pytest.approx(1000.7543398010286)


def test_match_leg_path_excludes_the_two_anchor_snap_points_themselves():
    # mirrors accumulate_path's existing contract: build_tour_record prepends/appends the hub
    # coordinate itself, so path.coords must NOT already contain the anchor snap points.
    subgraph = _line_subgraph_1000m()
    src_key, tgt_key = (binfmt.TYPE_HUT, 0), (binfmt.TYPE_HUT, 1)
    persisted = {src_key: _node_snap(100), tgt_key: _node_snap(101)}
    result = match_leg(subgraph, src_key, tgt_key, persisted,
                        trace_points=[(0.0, 0.0), (0.009, 0.0)], length_divergence_ratio=2.0,
                        **_HMM_KWARGS)
    assert result["ok"] is True
    # a 2-node line has no interior coords once its own two endpoints are excluded
    assert result["path"].coords == []


def test_match_leg_reports_hub_unsnapped_when_src_missing():
    subgraph = _line_subgraph_1000m()
    src_key, tgt_key = (binfmt.TYPE_HUT, 0), (binfmt.TYPE_HUT, 1)
    persisted = {tgt_key: _node_snap(101)}  # src_key never snapped
    result = match_leg(subgraph, src_key, tgt_key, persisted,
                        trace_points=[(0.0, 0.0), (0.009, 0.0)], length_divergence_ratio=2.0,
                        **_HMM_KWARGS)
    assert result == {"ok": False, "reason": "hub_unsnapped", "detail": {"missing": [src_key]}}


def test_match_leg_reports_outside_extract_when_corridor_is_empty():
    empty = LocalSubgraph(
        global_node_ids=np.zeros(0, dtype=np.int64),
        local_nodes=np.zeros(0, dtype=binfmt.NODE_DTYPE),
        local_edges=np.zeros(0, dtype=binfmt.EDGE_DTYPE),
        interior=np.zeros(0, dtype=binfmt.COORD_DTYPE),
        local_node_ele=np.zeros(0, dtype=np.float32), interior_ele=np.zeros(0, dtype=np.float32),
    )
    src_key, tgt_key = (binfmt.TYPE_HUT, 0), (binfmt.TYPE_HUT, 1)
    result = match_leg(empty, src_key, tgt_key, {}, trace_points=[(0.0, 0.0), (0.009, 0.0)],
                        length_divergence_ratio=2.0, **_HMM_KWARGS)
    assert result["reason"] == "outside_extract"


def test_match_leg_reports_length_divergent_when_routed_far_exceeds_trace():
    subgraph = _line_subgraph_1000m()
    src_key, tgt_key = (binfmt.TYPE_HUT, 0), (binfmt.TYPE_HUT, 1)
    persisted = {src_key: _node_snap(100), tgt_key: _node_snap(101)}
    # routed 1000m vs a trace of only 100m - ratio 10x, past the 2.0 divergence ratio.
    result = match_leg(subgraph, src_key, tgt_key, persisted,
                        trace_points=[(0.0, 0.0), (0.0009, 0.0)], length_divergence_ratio=2.0,
                        **_HMM_KWARGS)
    assert result["reason"] == "length_divergent"


from lib.cell_igraph import PathResult  # noqa: E402
from graph_building.match_tour_edges import build_tour_record  # noqa: E402


def test_build_tour_record_shape_matches_write_edge_records_expectations():
    path = PathResult(
        coords=[(0.003, 0.0)], distance_m=900.0, road_m=0.0, ungraded_m=0.0, inferred_m=0.0,
        ascent_m=30.0, descent_m=10.0, max_ele_m=1200.0, sac_rank=1, via_ferrata=False,
        base_edge_ids=[7],
    )
    src_snap = _node_snap(100, gap_m=5.0, gap_dz_m=0.0)
    tgt_snap = _node_snap(101, gap_m=3.0, gap_dz_m=0.0)
    # match_leg returns SnapResult (post-reconstruct_local_snaps), not PersistedSnap - build a
    # minimal stand-in with the same .gap_m/.gap_dz_m surface fold_endpoint_snaps reads.
    from dataclasses import dataclass

    @dataclass
    class _Snap:
        gap_m: float
        gap_dz_m: float

    record = build_tour_record(
        from_key=(binfmt.TYPE_HUT, 0), to_key=(binfmt.TYPE_HUT, 1),
        from_coord=(10.0, 47.0), to_coord=(10.01, 47.0),
        path=path, src_snap=_Snap(5.0, 0.0), tgt_snap=_Snap(3.0, 0.0),
    )
    assert record["from_id"] == 0 and record["to_id"] == 1
    assert record["from_type"] == binfmt.TYPE_HUT and record["to_type"] == binfmt.TYPE_HUT
    assert record["variant"] == binfmt.VARIANT_OFFICIAL
    assert record["distance_m"] == 900.0 + 5.0 + 3.0
    assert record["snap_m"] == 8.0
    assert record["geometry"][0] == (10.0, 47.0)
    assert record["geometry"][-1] == (10.01, 47.0)
    assert record["base_edge_ids"] == [7]


from lib.hub_snap import pack_hub_snaps, to_persisted  # noqa: E402
from lib.hub_snap import SnapResult  # noqa: E402


def _write_synthetic_base_graph(tmp_path, grid):
    """A single straight 4-node, 3-edge chain (~1km per edge) - LQR/WelserHöhenweg-shaped (single
    part, no unsnapped huts, spec Testing section) rather than Chiemgautour's 45-fragment geometry,
    which belongs in the §2.7 spike, not a golden test."""
    coords = [(0.0, 0.0), (0.009, 0.0), (0.018, 0.0), (0.027, 0.0)]  # ~1km apart at the equator
    nodes = np.zeros(4, dtype=binfmt.NODE_DTYPE)
    cell_ids = [grid.cell_id_for_point(*c) for c in coords]
    for i, (c, cid) in enumerate(zip(coords, cell_ids)):
        nodes[i] = (c[0], c[1], cid)
    _, cell_index = binfmt.build_csr_index(
        np.array(cell_ids, dtype=np.int32), n_groups=len(grid.all_cell_ids())
    )
    edges = np.zeros(3, dtype=binfmt.EDGE_DTYPE)
    for i in range(3):
        edges[i] = (i, i + 1, 1000.0, 0.0, 0.0, 0.0, 1000.0, 20.0, 5.0, -1, False, True, 0, 0, i)
    doubled_nodes = np.concatenate([edges["u"], edges["v"]])
    doubled_edge_ids = np.concatenate([edges["edge_id"], edges["edge_id"]])
    order, node_edge_index = binfmt.build_csr_index(doubled_nodes, n_groups=4)
    node_edge_ids = doubled_edge_ids[order]
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    node_ele = np.array([1000.0, 1020.0, 1040.0, 1060.0], dtype=np.float32)

    base_graph_dir = tmp_path / "base_graph"
    binfmt.save_array(base_graph_dir / "nodes.npy", nodes)
    binfmt.save_array(base_graph_dir / "cell_index.npy", cell_index)
    binfmt.save_array(base_graph_dir / "node_edge_index.npy", node_edge_index)
    binfmt.save_array(base_graph_dir / "node_edge_ids.npy", node_edge_ids)
    binfmt.save_array(base_graph_dir / "edges.npy", edges)
    binfmt.save_array(base_graph_dir / "interior.npy", interior)
    binfmt.save_array(base_graph_dir / "node_ele.npy", node_ele)
    binfmt.save_array(base_graph_dir / "interior_ele.npy", np.zeros(0, dtype=np.float32))
    binfmt.save_manifest(
        base_graph_dir / "manifest.json", {"bbox": BBOX, "tile_size_km": grid.tile_size_km},
    )
    return base_graph_dir, coords


def test_cached_gather_for_bounds_returns_same_object_for_same_cell_set(tmp_path):
    # Two different bounds that both overlap only cell 0 of a fine (1km) grid over the synthetic
    # chain's coords - a cache hit should return the identical LocalSubgraph object, not just an
    # equal one, proving the underlying gather_subgraph_for_bounds call was skipped.
    import graph_building.match_tour_edges as mte

    grid = Grid(BBOX, tile_size_km=1.0)
    base_graph_dir, _ = _write_synthetic_base_graph(tmp_path, grid)
    mte._subgraph_cache.clear()

    bounds_a = {"minLng": 0.0, "maxLng": 0.002, "minLat": -0.001, "maxLat": 0.001}
    bounds_b = {"minLng": 0.001, "maxLng": 0.003, "minLat": -0.001, "maxLat": 0.001}
    assert grid.cell_ids_overlapping(bounds_a) == grid.cell_ids_overlapping(bounds_b)

    first = mte._cached_gather_for_bounds(base_graph_dir, grid, bounds_a)
    second = mte._cached_gather_for_bounds(base_graph_dir, grid, bounds_b)
    assert first is second


def test_cached_gather_for_bounds_returns_different_object_for_different_cell_set(tmp_path):
    import graph_building.match_tour_edges as mte

    grid = Grid(BBOX, tile_size_km=1.0)
    base_graph_dir, _ = _write_synthetic_base_graph(tmp_path, grid)
    mte._subgraph_cache.clear()

    bounds_a = {"minLng": 0.0, "maxLng": 0.002, "minLat": -0.001, "maxLat": 0.001}
    bounds_c = {"minLng": 0.02, "maxLng": 0.025, "minLat": -0.001, "maxLat": 0.001}
    assert grid.cell_ids_overlapping(bounds_a) != grid.cell_ids_overlapping(bounds_c)

    first = mte._cached_gather_for_bounds(base_graph_dir, grid, bounds_a)
    third = mte._cached_gather_for_bounds(base_graph_dir, grid, bounds_c)
    assert first is not third


def test_golden_single_part_tour_matches_all_legs_end_to_end(tmp_path, monkeypatch):
    grid = Grid(BBOX, tile_size_km=60.0)
    base_graph_dir, node_coords = _write_synthetic_base_graph(tmp_path, grid)

    # 4 huts sitting exactly on the 4 graph nodes (single part, no unsnapped huts).
    hut_coords = node_coords
    huts_geojson = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"id": f"{{GUID-{i}}}"},
             "geometry": {"type": "Point", "coordinates": list(c)}}
            for i, c in enumerate(hut_coords)
        ],
    }
    (tmp_path / "huts.geojson").write_text(json.dumps(huts_geojson), encoding="utf-8")
    start_points = np.zeros(0, dtype=[("lon", "f8"), ("lat", "f8"), ("osm_id", "i8"), ("type", "u1")])
    binfmt.save_array(tmp_path / "start_points.npy", start_points)

    persisted_snaps = {}
    for i, node_idx in enumerate((0, 1, 2, 3)):
        result = SnapResult(node_index=node_idx, gap_m=0.0, gap_dz_m=0.0)
        stand_in_subgraph = LocalSubgraph(
            global_node_ids=np.arange(4), local_nodes=np.zeros(0, dtype=binfmt.NODE_DTYPE),
            local_edges=np.zeros(0, dtype=binfmt.EDGE_DTYPE),
            interior=np.zeros(0, dtype=binfmt.COORD_DTYPE),
            local_node_ele=np.zeros(0, dtype=np.float32), interior_ele=np.zeros(0, dtype=np.float32),
        )
        persisted_snaps[(binfmt.TYPE_HUT, i)] = to_persisted(stand_in_subgraph, result)
    pack_hub_snaps(persisted_snaps, tmp_path)

    tours_dir = tmp_path / "tours"
    tour_folder = tours_dir / "LQR"
    tour_folder.mkdir(parents=True)
    fixtures = Path(__file__).resolve().parent / "fixtures" / "tour_folder" / "LQR"
    for name in ("1.gpx", "2.gpx", "3.gpx"):
        (tour_folder / name).write_text((fixtures / name).read_text(encoding="utf-8"), encoding="utf-8")

    import graph_building.match_tour_edges as mte

    monkeypatch.setattr(mte, "OSM_DIR", tmp_path)
    monkeypatch.setattr(mte, "TOURS_DIR", tours_dir)
    monkeypatch.setattr(
        mte, "load_config",
        lambda: {"tourMatch": {
                      "corridorBufferM": 150.0, "lengthDivergenceRatio": 2.0,
                      "hmmResampleM": 25.0, "hmmObsNoiseM": 25.0, "hmmMaxDistM": 150.0,
                      "hmmDistNoiseM": 25.0, "endpointBridgeMaxM": 250.0,
                  },
                  "graph": {"maxSnapM": 100.0}},
    )
    mte.main(["--base-graph-dir", str(base_graph_dir), "--out-dir", str(tmp_path)])

    records = binfmt.load_array(tmp_path / "tour_edges" / "records.npy", mmap=False)
    tour_meta = binfmt.load_array(tmp_path / "tour_edges" / "tour_meta.npy", mmap=False)
    gaps = json.loads((tmp_path / "tour-match-gaps.json").read_text(encoding="utf-8"))
    tours_json = json.loads((tmp_path / "tours.json").read_text(encoding="utf-8"))

    assert len(records) == 3  # 3 legs, no gaps
    assert gaps == []
    assert list(tour_meta["leg_index"]) == [0, 1, 2]
    assert all(r == binfmt.VARIANT_OFFICIAL for r in records["variant"])
    assert (records["geom_offset"] >= 0).all()
    total_distance = records["distance_m"].sum()
    assert 2900.0 < total_distance < 3100.0  # ~3 x 1000m, order-of-magnitude sane

    assert tours_json == [{
        "tourId": 0, "name": "LQR",
        "legs": [
            {"legIndex": 0, "from": {"type": "hut", "id": 0}, "to": {"type": "hut", "id": 1}},
            {"legIndex": 1, "from": {"type": "hut", "id": 1}, "to": {"type": "hut", "id": 2}},
            {"legIndex": 2, "from": {"type": "hut", "id": 2}, "to": {"type": "hut", "id": 3}},
        ],
    }]


def test_golden_tour_reports_leg_endpoint_unsnapped_when_endpoint_far_from_any_hub(tmp_path, monkeypatch):
    grid = Grid(BBOX, tile_size_km=60.0)
    base_graph_dir, node_coords = _write_synthetic_base_graph(tmp_path, grid)

    # Only 3 huts on nodes 0,1,2 - node 3 (leg 3's endpoint) has NOTHING within max_snap_m.
    huts_geojson = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"id": f"{{GUID-{i}}}"},
             "geometry": {"type": "Point", "coordinates": list(node_coords[i])}}
            for i in range(3)
        ],
    }
    (tmp_path / "huts.geojson").write_text(json.dumps(huts_geojson), encoding="utf-8")
    binfmt.save_array(tmp_path / "start_points.npy", np.zeros(
        0, dtype=[("lon", "f8"), ("lat", "f8"), ("osm_id", "i8"), ("type", "u1")],
    ))

    persisted_snaps = {}
    for i in range(3):
        result = SnapResult(node_index=i, gap_m=0.0, gap_dz_m=0.0)
        stand_in_subgraph = LocalSubgraph(
            global_node_ids=np.arange(4), local_nodes=np.zeros(0, dtype=binfmt.NODE_DTYPE),
            local_edges=np.zeros(0, dtype=binfmt.EDGE_DTYPE),
            interior=np.zeros(0, dtype=binfmt.COORD_DTYPE),
            local_node_ele=np.zeros(0, dtype=np.float32), interior_ele=np.zeros(0, dtype=np.float32),
        )
        persisted_snaps[(binfmt.TYPE_HUT, i)] = to_persisted(stand_in_subgraph, result)
    pack_hub_snaps(persisted_snaps, tmp_path)

    tours_dir = tmp_path / "tours"
    tour_folder = tours_dir / "LQR"
    tour_folder.mkdir(parents=True)
    fixtures = Path(__file__).resolve().parent / "fixtures" / "tour_folder" / "LQR"
    for name in ("1.gpx", "2.gpx", "3.gpx"):
        (tour_folder / name).write_text((fixtures / name).read_text(encoding="utf-8"), encoding="utf-8")

    import graph_building.match_tour_edges as mte

    monkeypatch.setattr(mte, "OSM_DIR", tmp_path)
    monkeypatch.setattr(mte, "TOURS_DIR", tours_dir)
    monkeypatch.setattr(
        mte, "load_config",
        lambda: {"tourMatch": {
                      "corridorBufferM": 150.0, "lengthDivergenceRatio": 2.0,
                      "hmmResampleM": 25.0, "hmmObsNoiseM": 25.0, "hmmMaxDistM": 150.0,
                      "hmmDistNoiseM": 25.0, "endpointBridgeMaxM": 250.0,
                  },
                  "graph": {"maxSnapM": 100.0}},
    )
    mte.main(["--base-graph-dir", str(base_graph_dir), "--out-dir", str(tmp_path)])

    records = binfmt.load_array(tmp_path / "tour_edges" / "records.npy", mmap=False)
    gaps = json.loads((tmp_path / "tour-match-gaps.json").read_text(encoding="utf-8"))
    tours_json = json.loads((tmp_path / "tours.json").read_text(encoding="utf-8"))

    assert len(records) == 2  # legs 1,2 route; leg 3 (node 2 -> node 3) gaps
    assert len(gaps) == 1
    assert gaps[0]["reason"] == "leg_endpoint_unsnapped"
    assert gaps[0]["legIndex"] == 2
    assert gaps[0]["detail"]["endpoint"] == "to"
    assert gaps[0]["detail"]["nearestDistM"] > 100.0
    assert tours_json[0]["legs"][2]["to"] is None


def test_golden_tour_uses_hmm_config_and_still_matches_all_legs(tmp_path, monkeypatch):
    # Same fixture as test_golden_single_part_tour_matches_all_legs_end_to_end, but asserts the
    # five new config keys are actually threaded through main() -> match_leg (spec §7's
    # "changing hmmObsNoiseM would not invalidate the task" concern, exercised at the config-
    # plumbing level here; the DAG cli_param/TaskOptionsChanged wiring itself is doit-level and
    # not unit-testable from this file).
    grid = Grid(BBOX, tile_size_km=60.0)
    base_graph_dir, node_coords = _write_synthetic_base_graph(tmp_path, grid)
    hut_coords = node_coords
    huts_geojson = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"id": f"{{GUID-{i}}}"},
             "geometry": {"type": "Point", "coordinates": list(c)}}
            for i, c in enumerate(hut_coords)
        ],
    }
    (tmp_path / "huts.geojson").write_text(json.dumps(huts_geojson), encoding="utf-8")
    start_points = np.zeros(0, dtype=[("lon", "f8"), ("lat", "f8"), ("osm_id", "i8"), ("type", "u1")])
    binfmt.save_array(tmp_path / "start_points.npy", start_points)

    persisted_snaps = {}
    for i, node_idx in enumerate((0, 1, 2, 3)):
        result = SnapResult(node_index=node_idx, gap_m=0.0, gap_dz_m=0.0)
        stand_in_subgraph = LocalSubgraph(
            global_node_ids=np.arange(4), local_nodes=np.zeros(0, dtype=binfmt.NODE_DTYPE),
            local_edges=np.zeros(0, dtype=binfmt.EDGE_DTYPE),
            interior=np.zeros(0, dtype=binfmt.COORD_DTYPE),
            local_node_ele=np.zeros(0, dtype=np.float32), interior_ele=np.zeros(0, dtype=np.float32),
        )
        persisted_snaps[(binfmt.TYPE_HUT, i)] = to_persisted(stand_in_subgraph, result)
    pack_hub_snaps(persisted_snaps, tmp_path)

    tours_dir = tmp_path / "tours"
    tour_folder = tours_dir / "LQR"
    tour_folder.mkdir(parents=True)
    fixtures = Path(__file__).resolve().parent / "fixtures" / "tour_folder" / "LQR"
    for name in ("1.gpx", "2.gpx", "3.gpx"):
        (tour_folder / name).write_text((fixtures / name).read_text(encoding="utf-8"), encoding="utf-8")

    import graph_building.match_tour_edges as mte

    monkeypatch.setattr(mte, "OSM_DIR", tmp_path)
    monkeypatch.setattr(mte, "TOURS_DIR", tours_dir)
    monkeypatch.setattr(
        mte, "load_config",
        lambda: {
            "tourMatch": {
                "corridorBufferM": 150.0, "lengthDivergenceRatio": 2.0,
                "hmmResampleM": 25.0, "hmmObsNoiseM": 25.0, "hmmMaxDistM": 150.0,
                "hmmDistNoiseM": 25.0, "endpointBridgeMaxM": 250.0,
            },
            "graph": {"maxSnapM": 100.0},
        },
    )
    mte.main(["--base-graph-dir", str(base_graph_dir), "--out-dir", str(tmp_path)])

    records = binfmt.load_array(tmp_path / "tour_edges" / "records.npy", mmap=False)
    gaps = json.loads((tmp_path / "tour-match-gaps.json").read_text(encoding="utf-8"))
    assert len(records) == 3
    assert gaps == []


def test_length_divergent_still_reachable_after_hmm_decode_succeeds():
    # spec §8's "length_divergent still reachable": a fixture where the decode succeeds
    # end-to-end but the winning path's total length still exceeds lengthDivergenceRatio.
    subgraph = _line_subgraph_1000m()
    src_key, tgt_key = (binfmt.TYPE_HUT, 0), (binfmt.TYPE_HUT, 1)
    persisted = {src_key: _node_snap(100), tgt_key: _node_snap(101)}
    # a trace only 100m long, but the only routable path is the 1000m edge - decode succeeds
    # (it's the only candidate within hmmMaxDistM of a 100m trace sitting on top of its start),
    # length check must still catch the 10x divergence.
    trace_points = [(0.0, 0.0), (0.0009, 0.0)]
    result = match_leg(subgraph, src_key, tgt_key, persisted, trace_points=trace_points,
                        length_divergence_ratio=2.0, **_HMM_KWARGS)
    assert result["reason"] == "length_divergent"
