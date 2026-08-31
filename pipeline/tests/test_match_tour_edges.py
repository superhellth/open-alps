import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from graph_building.match_tour_edges import _chain_for_tour, build_tour_legs  # noqa: E402


def _tour(hut_indices, is_loop=False):
    return {"tourId": 0, "hutIndices": hut_indices, "isLoop": is_loop}


def test_chain_for_tour_falls_back_to_oa_when_reassembly_fails():
    # Two fragments 10km apart - reassemble_fragments (break_threshold_m=150) leaves them as 2
    # separate chains, so oriented is None on ArcGIS alone.
    paths = [[(0.0, 0.0), (0.001, 0.001)], [(1.0, 1.0), (1.001, 1.001)]]
    oa_points = [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)]
    chains, oriented = _chain_for_tour(
        paths, break_threshold_m=150.0, hut_coords_in_order=[(0.0, 0.0), (1.0, 1.0)],
        is_loop=False, oa_points=oa_points,
    )
    assert oriented == oa_points  # already starts at hut 0, no reversal needed


def test_chain_for_tour_prefers_arcgis_reassembly_when_it_succeeds():
    # Single fragment - reassembly already succeeds, so a DIFFERENT-looking oa_points must be
    # ignored (precedence: AV's own geometry wins when it's usable at all).
    paths = [[(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)]]
    oa_points = [(9.0, 9.0), (9.5, 9.5)]
    chains, oriented = _chain_for_tour(
        paths, break_threshold_m=150.0, hut_coords_in_order=[(0.0, 0.0), (1.0, 1.0)],
        is_loop=False, oa_points=oa_points,
    )
    assert oriented == paths[0]


def test_chain_for_tour_reports_gap_when_neither_source_works():
    chains, oriented = _chain_for_tour(
        [[(0.0, 0.0), (0.001, 0.001)], [(1.0, 1.0), (1.001, 1.001)]],
        break_threshold_m=150.0, hut_coords_in_order=[(0.0, 0.0), (1.0, 1.0)], is_loop=False,
        oa_points=None,
    )
    assert oriented is None


def test_open_tour_yields_n_minus_one_legs():
    legs = build_tour_legs(_tour([0, 1, 2, 3]))
    assert legs == [(0, 0, 1), (1, 1, 2), (2, 2, 3)]


def test_loop_tour_yields_n_legs_with_contiguous_leg_index():
    # spec §2.1 / Testing: a loop tour yields N legs, not N-1, and leg_index is contiguous -
    # the closing leg (last hut -> first hut) is appended.
    legs = build_tour_legs(_tour([0, 1, 2], is_loop=True))
    assert legs == [(0, 0, 1), (1, 1, 2), (2, 2, 0)]
    assert [leg[0] for leg in legs] == [0, 1, 2]


def test_unresolved_hut_sentinel_splits_the_chain():
    # -1 (fetch_tours.py's unresolved-GUID sentinel) drops BOTH legs touching it, not just one -
    # never silently fuses the two real stages on either side into one leg (spec §1).
    legs = build_tour_legs(_tour([0, 1, -1, 3, 4]))
    assert legs == [(0, 0, 1), (3, 3, 4)]


def test_empty_hut_list_yields_no_legs():
    assert build_tour_legs(_tour([])) == []


def test_single_hut_yields_no_legs():
    assert build_tour_legs(_tour([0])) == []


import numpy as np

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


def test_match_leg_routes_a_simple_corridor():
    subgraph = _line_subgraph_1000m()
    src_key, tgt_key = (binfmt.TYPE_HUT, 0), (binfmt.TYPE_HUT, 1)
    persisted = {src_key: _node_snap(100), tgt_key: _node_snap(101)}
    result = match_leg(subgraph, src_key, tgt_key, persisted, trace_length_m=1000.0,
                        length_divergence_ratio=2.0)
    assert result["ok"] is True
    assert result["path"].distance_m == 1000.0


def test_match_leg_reports_hut_unsnapped_when_src_missing():
    subgraph = _line_subgraph_1000m()
    src_key, tgt_key = (binfmt.TYPE_HUT, 0), (binfmt.TYPE_HUT, 1)
    persisted = {tgt_key: _node_snap(101)}  # src_key never snapped
    result = match_leg(subgraph, src_key, tgt_key, persisted, trace_length_m=1000.0,
                        length_divergence_ratio=2.0)
    assert result == {"ok": False, "reason": "hut_unsnapped", "detail": {"missing": [src_key]}}


def test_match_leg_reports_outside_extract_when_corridor_is_empty():
    empty = LocalSubgraph(
        global_node_ids=np.zeros(0, dtype=np.int64),
        local_nodes=np.zeros(0, dtype=binfmt.NODE_DTYPE),
        local_edges=np.zeros(0, dtype=binfmt.EDGE_DTYPE),
        interior=np.zeros(0, dtype=binfmt.COORD_DTYPE),
        local_node_ele=np.zeros(0, dtype=np.float32), interior_ele=np.zeros(0, dtype=np.float32),
    )
    src_key, tgt_key = (binfmt.TYPE_HUT, 0), (binfmt.TYPE_HUT, 1)
    result = match_leg(empty, src_key, tgt_key, {}, trace_length_m=1000.0,
                        length_divergence_ratio=2.0)
    assert result["reason"] == "outside_extract"


def test_match_leg_reports_length_divergent_when_routed_far_exceeds_trace():
    subgraph = _line_subgraph_1000m()
    src_key, tgt_key = (binfmt.TYPE_HUT, 0), (binfmt.TYPE_HUT, 1)
    persisted = {src_key: _node_snap(100), tgt_key: _node_snap(101)}
    # routed 1000m vs a trace of only 100m - ratio 10x, past the 2.0 divergence ratio.
    result = match_leg(subgraph, src_key, tgt_key, persisted, trace_length_m=100.0,
                        length_divergence_ratio=2.0)
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
        from_hut=0, to_hut=1, from_coord=(10.0, 47.0), to_coord=(10.01, 47.0),
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

    # 4 huts sitting exactly on the 4 graph nodes (LQR-shaped: single part, no unsnapped huts).
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

    persisted_snaps = {}
    for i, node_idx in enumerate((0, 1, 2, 3)):
        result = SnapResult(node_index=node_idx, gap_m=0.0, gap_dz_m=0.0)
        from lib.subgraph import LocalSubgraph

        stand_in_subgraph = LocalSubgraph(
            global_node_ids=np.arange(4), local_nodes=np.zeros(0, dtype=binfmt.NODE_DTYPE),
            local_edges=np.zeros(0, dtype=binfmt.EDGE_DTYPE),
            interior=np.zeros(0, dtype=binfmt.COORD_DTYPE),
            local_node_ele=np.zeros(0, dtype=np.float32), interior_ele=np.zeros(0, dtype=np.float32),
        )
        persisted_snaps[(binfmt.TYPE_HUT, i)] = to_persisted(stand_in_subgraph, result)
    pack_hub_snaps(persisted_snaps, tmp_path)

    tours = [{
        "tourId": 0, "globalId": "{TOUR-LQR}", "name": "LQR-shaped test tour",
        "shortCode": "LQRTEST", "isLoop": False, "homepage": None,
        "hutIndices": [0, 1, 2, 3],
    }]
    (tmp_path / "tours.json").write_text(json.dumps(tours), encoding="utf-8")
    traces = [{"tourId": 0, "paths": [[list(c) for c in node_coords]]}]  # single part
    (tmp_path / "tour_traces.json").write_text(json.dumps(traces), encoding="utf-8")

    import graph_building.match_tour_edges as mte

    monkeypatch.setattr(mte, "OSM_DIR", tmp_path)
    monkeypatch.setattr(
        mte, "load_config",
        lambda: {"tourMatch": {"fragmentBreakM": 150.0, "corridorBufferM": 150.0,
                                "maxHutTraceM": 250.0, "lengthDivergenceRatio": 2.0}},
    )
    mte.main(["--base-graph-dir", str(base_graph_dir), "--out-dir", str(tmp_path)])

    records = binfmt.load_array(tmp_path / "tour_edges" / "records.npy", mmap=False)
    tour_meta = binfmt.load_array(tmp_path / "tour_edges" / "tour_meta.npy", mmap=False)
    gaps = json.loads((tmp_path / "tour-match-gaps.json").read_text(encoding="utf-8"))

    assert len(records) == 3  # 3 legs, no gaps
    assert gaps == []
    assert list(tour_meta["leg_index"]) == [0, 1, 2]
    assert all(r == binfmt.VARIANT_OFFICIAL for r in records["variant"])
    # touches both huts' own coordinates at the geometry endpoints
    assert (records["geom_offset"] >= 0).all()
    total_distance = records["distance_m"].sum()
    assert 2900.0 < total_distance < 3100.0  # ~3 x 1000m, order-of-magnitude sane


def test_rundtour_closing_leg_is_matched(tmp_path, monkeypatch):
    # A 4-hut Rundtour on the same synthetic straight chain: the closing leg's corridor bbox (huts
    # 3 and 0, the chain's own endpoints) spans the WHOLE chain, and the base graph is undirected,
    # so the router legitimately finds a path back through nodes 2 and 1 (distance ~3000m, not
    # gapped) - this fixture can't exercise a "closing leg has no real geometry" gap (that needs a
    # true loop shape, out of scope for this synthetic straight-chain fixture); what it does prove
    # is that isLoop=True actually appends the N-th leg and it gets matched like any other leg.
    grid = Grid(BBOX, tile_size_km=60.0)
    base_graph_dir, node_coords = _write_synthetic_base_graph(tmp_path, grid)
    huts_geojson = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"id": f"{{GUID-{i}}}"},
             "geometry": {"type": "Point", "coordinates": list(c)}}
            for i, c in enumerate(node_coords)
        ],
    }
    (tmp_path / "huts.geojson").write_text(json.dumps(huts_geojson), encoding="utf-8")

    persisted_snaps = {}
    from lib.subgraph import LocalSubgraph
    stand_in_subgraph = LocalSubgraph(
        global_node_ids=np.arange(4), local_nodes=np.zeros(0, dtype=binfmt.NODE_DTYPE),
        local_edges=np.zeros(0, dtype=binfmt.EDGE_DTYPE), interior=np.zeros(0, dtype=binfmt.COORD_DTYPE),
        local_node_ele=np.zeros(0, dtype=np.float32), interior_ele=np.zeros(0, dtype=np.float32),
    )
    for i, node_idx in enumerate((0, 1, 2, 3)):
        result = SnapResult(node_index=node_idx, gap_m=0.0, gap_dz_m=0.0)
        persisted_snaps[(binfmt.TYPE_HUT, i)] = to_persisted(stand_in_subgraph, result)
    pack_hub_snaps(persisted_snaps, tmp_path)

    tours = [{
        "tourId": 0, "globalId": "{TOUR-LOOP}", "name": "Loop test tour", "shortCode": "LOOPTEST",
        "isLoop": True, "homepage": None, "hutIndices": [0, 1, 2, 3],
    }]
    (tmp_path / "tours.json").write_text(json.dumps(tours), encoding="utf-8")
    traces = [{"tourId": 0, "paths": [[list(c) for c in node_coords]]}]
    (tmp_path / "tour_traces.json").write_text(json.dumps(traces), encoding="utf-8")

    import graph_building.match_tour_edges as mte
    monkeypatch.setattr(mte, "OSM_DIR", tmp_path)
    monkeypatch.setattr(
        mte, "load_config",
        lambda: {"tourMatch": {"fragmentBreakM": 150.0, "corridorBufferM": 150.0,
                                "maxHutTraceM": 250.0, "lengthDivergenceRatio": 2.0}},
    )
    mte.main(["--base-graph-dir", str(base_graph_dir), "--out-dir", str(tmp_path)])

    records = binfmt.load_array(tmp_path / "tour_edges" / "records.npy", mmap=False)
    tour_meta = binfmt.load_array(tmp_path / "tour_edges" / "tour_meta.npy", mmap=False)
    gaps = json.loads((tmp_path / "tour-match-gaps.json").read_text(encoding="utf-8"))

    # 4 legs total (loop yields N legs, not N-1), and all 4 are matched - the closing leg (index 3,
    # hut 3 -> hut 0) routes back through nodes 2 and 1 since the base graph is undirected and its
    # own corridor bbox spans the whole chain.
    assert len(records) == 4
    assert gaps == []
    assert list(tour_meta["leg_index"]) == [0, 1, 2, 3]
    closing_leg = records[tour_meta["leg_index"] == 3][0]
    assert 2900.0 < closing_leg["distance_m"] < 3100.0


def test_golden_tour_falls_back_to_oa_when_arcgis_fragments_dont_reassemble(tmp_path, monkeypatch):
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

    tours = [{
        "tourId": 0, "globalId": "{TOUR-OATEST}", "name": "OA-fallback test tour",
        "shortCode": "OATEST", "isLoop": False, "homepage": None, "oaId": "1",
        "hutIndices": [0, 1, 2, 3],
    }]
    (tmp_path / "tours.json").write_text(json.dumps(tours), encoding="utf-8")
    # Deliberately broken into 2 far-apart fragments - reassemble_fragments will NOT rejoin them
    # (default fragmentBreakM=150.0 in this test's config below).
    traces = [{"tourId": 0, "paths": [[list(node_coords[0]), list(node_coords[1])],
                                       [list(node_coords[2]), list(node_coords[3])]]}]
    (tmp_path / "tour_traces.json").write_text(json.dumps(traces), encoding="utf-8")
    (tmp_path / "tour_oa_traces.json").write_text(
        json.dumps([{"tourId": 0, "points": [list(c) for c in node_coords]}]), encoding="utf-8",
    )

    import graph_building.match_tour_edges as mte

    monkeypatch.setattr(mte, "OSM_DIR", tmp_path)
    monkeypatch.setattr(
        mte, "load_config",
        lambda: {"tourMatch": {"fragmentBreakM": 150.0, "corridorBufferM": 150.0,
                                "maxHutTraceM": 250.0, "lengthDivergenceRatio": 2.0}},
    )
    mte.main(["--base-graph-dir", str(base_graph_dir), "--out-dir", str(tmp_path)])

    records = binfmt.load_array(tmp_path / "tour_edges" / "records.npy", mmap=False)
    gaps = json.loads((tmp_path / "tour-match-gaps.json").read_text(encoding="utf-8"))
    assert len(records) == 3  # all 3 legs matched via the OA fallback, no chain_not_reassembled
    assert gaps == []
