import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from lib.grid import Grid  # noqa: E402
from lib.subgraph import LocalSubgraph  # noqa: E402
from lib.timing import StepTimer  # noqa: E402
from lib import variants  # noqa: E402
from graph_building.build_hub_edges import (  # noqa: E402
    SnapRejection, SnapResult, _build_base_igraph_arrays, _build_igraph_from_base,
    _build_igraph_with_snaps, _cell_workload_score, _path_for, _write_edge_output,
    compute_hub_edges_for_cell, merge_and_dedup, snap_hub_to_subgraph, write_unsnapped_report,
)
from graph_building.gather_route_subgraphs import cell_dir_for  # noqa: E402

BBOX = {"minLng": 0.0, "maxLng": 1.0, "minLat": 0.0, "maxLat": 1.0}
FAST_ANY_ONLY = [variants.VARIANTS[binfmt.VARIANT_FAST_ANY]]


def _line_subgraph():
    # Two nodes 1000m apart (roughly, at these latitudes), one edge, no interior points -
    # a hub snapping anywhere on it lands mid-chain (segment_index=0).
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.009, 0.0, 0)  # ~1000m east at the equator
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    # u, v, dist, road_m, ungraded_m, inferred_m, time_s, ascent_m, descent_m, sac_rank,
    # via_ferrata, constrained_ok, interior_offset, interior_count, edge_id
    edges[0] = (0, 1, 1000.0, 0.0, 0.0, 0.0, 1000.0, binfmt.UNSET, binfmt.UNSET, -1, False, True,
                0, 0, 0)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    return LocalSubgraph(
        global_node_ids=np.array([100, 101]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.zeros(len(nodes), dtype=np.float32),
        interior_ele=np.zeros(len(interior), dtype=np.float32),
    )


def test_snap_hub_to_existing_node():
    subgraph = _line_subgraph()
    result = snap_hub_to_subgraph(subgraph, hub_lon=0.0001, hub_lat=0.0, max_snap_m=50.0)
    assert result is not None
    assert result.node_index == 0


def test_snap_hub_mid_chain_returns_split():
    subgraph = _line_subgraph()
    result = snap_hub_to_subgraph(subgraph, hub_lon=0.0045, hub_lat=0.0002, max_snap_m=50.0)
    assert result is not None
    assert result.split is not None
    assert result.edge_local_index == 0


def _line_subgraph_with_interior():
    # Same two nodes ~1000m apart as _line_subgraph, but the edge now has a 2-point interior
    # polyline - _line_subgraph's zero-interior edge never exercises
    # _build_edge_spatial_index's ragged-gather/lexsort path for real polyline order.
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.009, 0.0, 0)
    interior = np.zeros(2, dtype=binfmt.COORD_DTYPE)
    interior[0] = (0.003, 0.0)
    interior[1] = (0.006, 0.0)
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 1000.0, 0.0, 0.0, 0.0, 1000.0, binfmt.UNSET, binfmt.UNSET, -1, False, True,
                0, 2, 0)  # interior_offset=0, count=2
    return LocalSubgraph(
        global_node_ids=np.array([100, 101]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.zeros(len(nodes), dtype=np.float32),
        interior_ele=np.zeros(len(interior), dtype=np.float32),
    )


def test_snap_hub_mid_chain_with_interior_polyline_picks_nearest_segment():
    # Hub sits just past the second interior point (0.006, 0.0), close to the segment between it
    # and node 1 - exercises the vectorized interior-point gather + true-polyline-order
    # reconstruction in _build_edge_spatial_index, not just the two-endpoint case.
    subgraph = _line_subgraph_with_interior()
    result = snap_hub_to_subgraph(subgraph, hub_lon=0.0065, hub_lat=0.0002, max_snap_m=50.0)
    assert result is not None
    assert result.split is not None
    assert result.edge_local_index == 0


def test_far_hub_is_rejected_with_the_distance_reason():
    # Supersedes the old "returns None when out of range" behaviour (spec E3): a hub that cannot
    # snap is now a counted, reported SnapRejection, never a silent None.
    subgraph = _line_subgraph()
    result = snap_hub_to_subgraph(subgraph, hub_lon=0.5, hub_lat=0.5, max_snap_m=50.0,
                                   max_snap_ascent_m=25.0)
    assert isinstance(result, SnapRejection)
    assert result.reason == "gap_too_far"


def test_no_trail_data_at_all_gets_its_own_reason():
    # Distinct from gap_too_far: this hub's padded cell has no trail data whatsoever, not just
    # trail data that happens to be farther away than max_snap_m.
    empty = LocalSubgraph(
        global_node_ids=np.zeros(0, dtype=np.int64),
        local_nodes=np.zeros(0, dtype=binfmt.NODE_DTYPE),
        local_edges=np.zeros(0, dtype=binfmt.EDGE_DTYPE),
        interior=np.zeros(0, dtype=binfmt.COORD_DTYPE),
        local_node_ele=np.zeros(0, dtype=np.float32),
        interior_ele=np.zeros(0, dtype=np.float32),
    )
    result = snap_hub_to_subgraph(empty, hub_lon=0.0, hub_lat=0.0, max_snap_m=50.0)
    assert isinstance(result, SnapRejection)
    assert result.reason == "no_trail_data"


def test_snap_result_reports_the_gap():
    # hub sits ~55.6m north of node 0 (0.0005 deg lat at the equator) - within max_snap_m, so the
    # node branch wins and the gap is the straight-line hub-to-node distance (spec E3).
    subgraph = _line_subgraph()
    result = snap_hub_to_subgraph(subgraph, hub_lon=0.0, hub_lat=0.0005, max_snap_m=100.0)
    assert result.gap_m == pytest.approx(55.6, rel=0.05)


def test_snap_gap_dz_is_zero_when_hub_elevation_is_not_given():
    # gap_dz_m defaults to 0.0 (not unknown -> treated as flat) when the caller has no elevation
    # for the hub - callers that don't pass hub_ele_m keep working unchanged.
    subgraph = _line_subgraph()
    result = snap_hub_to_subgraph(subgraph, hub_lon=0.0, hub_lat=0.0005, max_snap_m=100.0)
    assert result.gap_dz_m == 0.0


def test_snap_gap_dz_is_hub_minus_snap_point_elevation():
    subgraph = _line_subgraph()  # local_node_ele defaults to [0.0, 0.0]
    result = snap_hub_to_subgraph(
        subgraph, hub_lon=0.0, hub_lat=0.0005, max_snap_m=100.0, hub_ele_m=940.0
    )
    assert result.node_index == 0
    assert result.gap_dz_m == pytest.approx(940.0)


def test_vertical_offset_rejects_a_wall_bivouac():
    # spec E3, Watzmann-Ostwand-Biwak shape - a hub whose gap is well inside max_snap_m but whose
    # vertical offset (30m here, chosen > the 25m cap; the real hut's measured 17m sits under the
    # cap and only motivates why a horizontal-only check would have missed it) exceeds
    # max_snap_ascent_m must be rejected even though the horizontal check alone would pass it.
    subgraph = _line_subgraph()  # local_node_ele defaults to [0.0, 0.0]
    result = snap_hub_to_subgraph(
        subgraph, hub_lon=0.0, hub_lat=0.0005, max_snap_m=100.0, max_snap_ascent_m=25.0,
        hub_ele_m=30.0,
    )
    assert isinstance(result, SnapRejection)
    assert result.reason == "vertical_offset"


def test_ordinary_hut_on_steep_ground_still_snaps():
    # Staufner Haus shape: steep terrain but only ~8m of vertical offset - under the cap.
    subgraph = _line_subgraph()
    result = snap_hub_to_subgraph(
        subgraph, hub_lon=0.0, hub_lat=0.0005, max_snap_m=100.0, max_snap_ascent_m=25.0,
        hub_ele_m=8.0,
    )
    assert isinstance(result, SnapResult)


def test_vertical_check_is_skipped_without_a_hub_elevation():
    # hub_ele_m=None means "unknown", not "flat" - it must not be treated as a 0m offset that
    # trivially passes, nor block snapping outright (spec E3 only asks to validate offsets it can
    # actually measure).
    subgraph = _line_subgraph()
    result = snap_hub_to_subgraph(
        subgraph, hub_lon=0.0, hub_lat=0.0005, max_snap_m=100.0, max_snap_ascent_m=25.0,
    )
    assert isinstance(result, SnapResult)


def test_unsnapped_report_records_every_rejection(tmp_path):
    write_unsnapped_report(tmp_path / "unsnapped_huts.json", [
        SnapRejection(hub_id=7, name="Schuesselkar-Biwak", gap_m=250.0, dz_m=258.0,
                      reason="vertical_offset"),
    ])
    got = json.loads((tmp_path / "unsnapped_huts.json").read_text(encoding="utf-8"))
    assert got[0]["reason"] == "vertical_offset"
    assert got[0]["dz_m"] == 258.0


def test_snap_gap_dz_mid_chain_interpolates_along_the_edge():
    # hub snaps mid-chain, past max_snap_m of either node - snap-point elevation is the
    # distance-ratio blend of the two endpoint elevations (same ratio split_edge_at_point already
    # uses to apportion ungraded_m/inferred_m), not either endpoint's raw value.
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.009, 0.0, 0)
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 1000.0, 0.0, 0.0, 0.0, 1000.0, binfmt.UNSET, binfmt.UNSET, -1, False, True,
                0, 0, 0)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    subgraph = LocalSubgraph(
        global_node_ids=np.array([100, 101]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.array([1000.0, 2000.0], dtype=np.float32),
        interior_ele=np.zeros(len(interior), dtype=np.float32),
    )
    # hub sits opposite the midpoint (~0.0045 lon), out of node-snap range of either endpoint
    result = snap_hub_to_subgraph(
        subgraph, hub_lon=0.0045, hub_lat=0.0002, max_snap_m=50.0, hub_ele_m=1600.0
    )
    assert result.split is not None
    # midpoint snap elevation ~= 1500.0 (halfway between 1000 and 2000)
    assert result.gap_dz_m == pytest.approx(100.0, abs=5.0)


def test_compute_hub_edges_for_cell_connects_two_huts_on_the_line():
    subgraph = _line_subgraph()
    core_hubs = [
        {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0},
        {"id": 2, "type": binfmt.TYPE_HUT, "lon": 0.0089, "lat": 0.0},
    ]
    records = compute_hub_edges_for_cell(
        subgraph, core_hubs, all_hubs=core_hubs, max_edge_km=5.0, max_snap_m=50.0,
        variants=FAST_ANY_ONLY,
    )
    assert len(records) == 1
    assert records[0]["distance_m"] < 5000


def test_compute_hub_edges_for_cell_returns_full_path_geometry():
    subgraph = _line_subgraph()
    core_hubs = [
        {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0},
        {"id": 2, "type": binfmt.TYPE_HUT, "lon": 0.0089, "lat": 0.0},
    ]
    records = compute_hub_edges_for_cell(
        subgraph, core_hubs, all_hubs=core_hubs, max_edge_km=5.0, max_snap_m=50.0,
        variants=FAST_ANY_ONLY,
    )
    assert len(records) == 1
    geometry = records[0]["geometry"]
    assert len(geometry) >= 2
    assert geometry[0] == (core_hubs[0]["lon"], core_hubs[0]["lat"])
    assert geometry[-1] == (core_hubs[1]["lon"], core_hubs[1]["lat"])


def test_record_distance_includes_both_snap_gaps():
    # both huts sit off the trail line - the shipped distance_m must be the routed trail distance
    # (the edge's explicit dist=1000.0) PLUS both ends' hub-to-trail gaps, not just the trail leg
    # (spec E3: "the gap is currently free").
    subgraph = _line_subgraph()
    core_hubs = [
        {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0, "lat": 0.0004},
        {"id": 2, "type": binfmt.TYPE_HUT, "lon": 0.009, "lat": 0.0003},
    ]
    records = compute_hub_edges_for_cell(
        subgraph, core_hubs, all_hubs=core_hubs, max_edge_km=5.0, max_snap_m=50.0,
        variants=FAST_ANY_ONLY,
    )
    assert len(records) == 1
    r = records[0]
    assert r["snap_m"] > 0
    assert r["distance_m"] == pytest.approx(1000.0 + r["snap_m"], rel=1e-3)


def test_snap_gap_climb_lands_in_ascent_not_only_distance():
    # hub 1 sits 40m below its own snap point (a valley hut reached by climbing UP to the trail),
    # hub 2 sits exactly at its snap point's elevation (isolates the effect to one end).
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.009, 0.0, 0)
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 1000.0, 0.0, 0.0, 0.0, 1000.0, 0.0, 0.0, -1, False, True, 0, 0, 0)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    subgraph = LocalSubgraph(
        global_node_ids=np.array([100, 101]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.array([1000.0, 1000.0], dtype=np.float32),
        interior_ele=np.zeros(len(interior), dtype=np.float32),
    )
    core_hubs = [
        {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0, "lat": 0.0004, "ele": 960.0},
        {"id": 2, "type": binfmt.TYPE_HUT, "lon": 0.009, "lat": 0.0003, "ele": 1000.0},
    ]
    records = compute_hub_edges_for_cell(
        subgraph, core_hubs, all_hubs=core_hubs, max_edge_km=5.0, max_snap_m=50.0,
        variants=FAST_ANY_ONLY,
    )
    assert len(records) == 1
    assert records[0]["ascent_m"] >= 40.0


def test_merge_and_dedup_drops_duplicate_hut_pairs():
    shard_a = [{"from_id": 1, "to_id": 2, "from_type": binfmt.TYPE_HUT,
                "to_type": binfmt.TYPE_HUT, "variant": 0, "distance_m": 100.0}]
    shard_b = [{"from_id": 2, "to_id": 1, "from_type": binfmt.TYPE_HUT,
                "to_type": binfmt.TYPE_HUT, "variant": 0, "distance_m": 100.0}]
    merged = merge_and_dedup([shard_a, shard_b])
    assert len(merged) == 1


def test_merge_and_dedup_keeps_directional_start_edges():
    shard = [
        {"from_id": 1, "to_id": 2, "from_type": binfmt.TYPE_PARKING,
         "to_type": binfmt.TYPE_HUT, "variant": 0, "distance_m": 100.0},
        {"from_id": 1, "to_id": 3, "from_type": binfmt.TYPE_PARKING,
         "to_type": binfmt.TYPE_HUT, "variant": 0, "distance_m": 200.0},
    ]
    merged = merge_and_dedup([shard])
    assert len(merged) == 2


def test_compute_hub_edges_for_cell_skips_access_to_access_pairs():
    # A station and a parking lot on the same trail line, no hut anywhere: nothing downstream
    # consumes a station<->parking edge, so no record should be routed at all.
    subgraph = _line_subgraph()
    core_hubs = [
        {"id": 1, "type": binfmt.TYPE_STATION, "lon": 0.0001, "lat": 0.0},
        {"id": 2, "type": binfmt.TYPE_PARKING, "lon": 0.0089, "lat": 0.0},
    ]
    records = compute_hub_edges_for_cell(
        subgraph, core_hubs, all_hubs=core_hubs, max_edge_km=5.0, max_snap_m=50.0,
        variants=FAST_ANY_ONLY,
    )
    assert records == []


def test_compute_hub_edges_for_cell_emits_access_to_hut_only_once():
    # Hut and station both core hubs of this cell: only the access->hut direction is emitted,
    # since __main__ drops hut->access records anyway.
    subgraph = _line_subgraph()
    core_hubs = [
        {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0},
        {"id": 2, "type": binfmt.TYPE_STATION, "lon": 0.0089, "lat": 0.0},
    ]
    records = compute_hub_edges_for_cell(
        subgraph, core_hubs, all_hubs=core_hubs, max_edge_km=5.0, max_snap_m=50.0,
        variants=FAST_ANY_ONLY,
    )
    assert len(records) == 1
    assert records[0]["from_type"] == binfmt.TYPE_STATION
    assert records[0]["to_type"] == binfmt.TYPE_HUT


def _two_edge_subgraph():
    # 3 nodes in a line, two distinct edges (0-1, 1-2) with different time_s, so the mask test
    # can drop one edge and the weight test can check every edge's weight against its own time_s.
    nodes = np.zeros(3, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.009, 0.0, 0)
    nodes[2] = (0.018, 0.0, 0)
    edges = np.zeros(2, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 1000.0, 0.0, 0.0, 0.0, 100.0, binfmt.UNSET, binfmt.UNSET, -1, False, True,
                0, 0, 0)
    edges[1] = (1, 2, 1000.0, 0.0, 0.0, 0.0, 200.0, binfmt.UNSET, binfmt.UNSET, -1, False, True,
                0, 0, 1)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    return LocalSubgraph(
        global_node_ids=np.array([100, 101, 102]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.zeros(len(nodes), dtype=np.float32),
        interior_ele=np.zeros(len(interior), dtype=np.float32),
    )


def test_igraph_routes_on_time_not_distance():
    subgraph = _two_edge_subgraph()
    graph, hub_vertex, coords = _build_igraph_with_snaps(subgraph, {})
    assert graph.es["weight"] == graph.es["time_s"]


def test_edge_mask_removes_edges_from_the_built_graph():
    subgraph = _two_edge_subgraph()
    graph_all, _, _ = _build_igraph_with_snaps(subgraph, {}, edge_mask=None)
    graph_filtered, _, _ = _build_igraph_with_snaps(
        subgraph, {}, edge_mask=np.array([True, False])
    )
    assert graph_filtered.ecount() < graph_all.ecount()


def test_compute_hub_edges_for_cell_fills_the_step_timer():
    # The per-step split is what tells a long run apart: snapping scales with hub count, the
    # distance/path steps with subgraph size x pair count.
    subgraph = _line_subgraph()
    core_hubs = [
        {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0},
        {"id": 2, "type": binfmt.TYPE_HUT, "lon": 0.0089, "lat": 0.0},
    ]
    timer = StepTimer()
    compute_hub_edges_for_cell(
        subgraph, core_hubs, all_hubs=core_hubs, max_edge_km=5.0, max_snap_m=50.0,
        variants=FAST_ANY_ONLY, timer=timer,
    )
    assert set(timer.seconds) == {"snap", "build_igraph", "distances", "paths"}
    assert timer.calls["snap"] == 1          # one timed pass over the whole snap loop
    assert timer.calls["snap_hubs"] == 2     # both huts snapped onto the line
    assert timer.calls["distances"] == 2     # one distance query per core hub


def _line_subgraph_t2_graded():
    # Same layout as _line_subgraph, but graded T2 (not ungraded) so a constrained row
    # (FAST_T2/FAST_T3) has a legal path to route, not just FAST_ANY.
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.009, 0.0, 0)
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 1000.0, 0.0, 0.0, 0.0, 1000.0, binfmt.UNSET, binfmt.UNSET, 2, False, True,
                0, 0, 0)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    return LocalSubgraph(
        global_node_ids=np.array([100, 101]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.zeros(len(nodes), dtype=np.float32),
        interior_ele=np.zeros(len(interior), dtype=np.float32),
    )


def test_variant_rows_are_not_collapsed_into_one_record():
    # spec C6: three places key on the hut pair alone and would silently discard variant rows
    subgraph = _line_subgraph_t2_graded()
    core_hubs = [
        {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0},
        {"id": 2, "type": binfmt.TYPE_HUT, "lon": 0.0089, "lat": 0.0},
    ]
    records = compute_hub_edges_for_cell(
        subgraph, core_hubs, all_hubs=core_hubs, max_edge_km=5.0, max_snap_m=50.0,
        variants=[variants.VARIANTS[binfmt.VARIANT_FAST_ANY],
                  variants.VARIANTS[binfmt.VARIANT_FAST_T3]],
    )
    assert {r["variant"] for r in records} == {binfmt.VARIANT_FAST_ANY, binfmt.VARIANT_FAST_T3}


def test_merge_and_dedup_keys_on_pair_and_variant():
    a = {"from_type": 0, "from_id": 1, "to_type": 0, "to_id": 2, "variant": 0}
    b = {"from_type": 0, "from_id": 2, "to_type": 0, "to_id": 1, "variant": 0}  # same pair reversed
    c = {"from_type": 0, "from_id": 1, "to_type": 0, "to_id": 2, "variant": 2}  # same pair, other row
    assert len(merge_and_dedup([[a], [b], [c]])) == 2


def _rec(variant, from_id=1, to_id=2, distance_m=100.0, geometry=None):
    return {
        "from_id": from_id, "to_id": to_id, "from_type": binfmt.TYPE_HUT, "to_type": binfmt.TYPE_HUT,
        "variant": variant, "distance_m": distance_m, "road_m": 0.0,
        "ascent_m": 0.0, "descent_m": 0.0, "max_ele_m": 0.0,
        "ungraded_m": 0.0, "inferred_m": 0.0, "snap_m": 0.0,
        "sac_rank": -1, "via_ferrata": False,
        "geometry": geometry if geometry is not None else [(0.0, 0.0), (0.01, 0.0)],
    }


def test_write_edge_output_preserves_each_record_variant(tmp_path):
    _write_edge_output([_rec(variant=0), _rec(variant=2)], tmp_path)
    arr = binfmt.load_array(tmp_path / "records.npy", mmap=False)
    assert sorted(arr["variant"].tolist()) == [0, 2]


def test_identical_variant_geometries_share_one_offset(tmp_path):
    geom = [(0.0, 0.0), (0.001, 0.0)]
    _write_edge_output([_rec(variant=0, geometry=geom), _rec(variant=2, geometry=geom)], tmp_path)
    records = binfmt.load_array(tmp_path / "records.npy", mmap=False)
    geometry = binfmt.load_array(tmp_path / "geometry.npy", mmap=False)
    assert records["geom_offset"][0] == records["geom_offset"][1]
    assert len(geometry) == 2   # one shared run, not two copies


def test_differing_geometries_do_not_share(tmp_path):
    _write_edge_output([
        _rec(variant=0, geometry=[(0.0, 0.0), (0.001, 0.0)]),
        _rec(variant=2, geometry=[(0.0, 0.0), (0.001, 0.001)]),
    ], tmp_path)
    records = binfmt.load_array(tmp_path / "records.npy", mmap=False)
    assert records["geom_offset"][0] != records["geom_offset"][1]


def test_route_exceeding_max_edge_km_is_dropped():
    # spec C8: selection cuts off on `dist`, but the routed path's distance_m can exceed the cap
    subgraph = _line_subgraph()
    core_hubs = [
        {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0},
        {"id": 2, "type": binfmt.TYPE_HUT, "lon": 0.0089, "lat": 0.0},
    ]
    records = compute_hub_edges_for_cell(
        subgraph, core_hubs, all_hubs=core_hubs, max_edge_km=0.5, max_snap_m=50.0,
        variants=FAST_ANY_ONLY,
    )
    assert all(r["distance_m"] <= 500.0 for r in records)


def test_a_variant_with_no_obeying_path_emits_no_record():
    # NOT a fallback to the unconstrained path: a constrained row that cannot connect a pair must
    # produce nothing, or the guarantee it exists for is broken
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.009, 0.0, 0)
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    # ungraded (sac_rank -1, constrained_ok False) - unroutable under any constrained row
    edges[0] = (0, 1, 1000.0, 0.0, 1000.0, 0.0, 1000.0, binfmt.UNSET, binfmt.UNSET, -1, False,
                False, 0, 0, 0)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    subgraph = LocalSubgraph(
        global_node_ids=np.array([100, 101]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.zeros(len(nodes), dtype=np.float32),
        interior_ele=np.zeros(len(interior), dtype=np.float32),
    )
    core_hubs = [
        {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0},
        {"id": 2, "type": binfmt.TYPE_HUT, "lon": 0.0089, "lat": 0.0},
    ]
    records = compute_hub_edges_for_cell(
        subgraph, core_hubs, all_hubs=core_hubs, max_edge_km=5.0, max_snap_m=50.0,
        variants=[variants.VARIANTS[binfmt.VARIANT_FAST_T3]],
    )
    assert records == []


def _col_subgraph():
    # 3 nodes in a line; node 1 (the middle) sits ABOVE both endpoints - a col. Edge 0->1 climbs
    # 500m (ascent), edge 1->2 drops 300m (descent); edge 0 also carries ungraded/inferred metres
    # so the summing test has something to sum.
    nodes = np.zeros(3, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.009, 0.0, 0)
    nodes[2] = (0.018, 0.0, 0)
    edges = np.zeros(2, dtype=binfmt.EDGE_DTYPE)
    # u, v, dist, road_m, ungraded_m, inferred_m, time_s, ascent_m, descent_m, sac_rank,
    # via_ferrata, constrained_ok, interior_offset, interior_count, edge_id
    edges[0] = (0, 1, 1000.0, 0.0, 100.0, 0.0, 500.0, 500.0, 0.0, -1, False, True, 0, 0, 0)
    edges[1] = (1, 2, 1000.0, 0.0, 0.0, 50.0, 300.0, 0.0, 300.0, -1, False, True, 0, 0, 1)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    return LocalSubgraph(
        global_node_ids=np.array([100, 101, 102]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.array([1000.0, 1500.0, 1200.0], dtype=np.float32),
        interior_ele=np.zeros(0, dtype=np.float32),
    )


def test_path_sums_ungraded_and_inferred_metres_like_road_m():
    subgraph = _col_subgraph()
    graph, _, vertex_coords = _build_igraph_with_snaps(subgraph, {})
    result = _path_for(graph, vertex_coords, 0, 2)
    assert result.ungraded_m == pytest.approx(100.0)
    assert result.inferred_m == pytest.approx(50.0)


def test_constrained_row_paths_have_zero_ungraded_metres():
    # the invariant the whole passability design rests on (spec C4/D1)
    subgraph = _line_subgraph_t2_graded()
    mask = variants.edge_mask(subgraph.local_edges, variants.VARIANTS[binfmt.VARIANT_FAST_T3])
    graph, hub_vertex, vertex_coords = _build_igraph_with_snaps(subgraph, {}, edge_mask=mask)
    result = _path_for(graph, vertex_coords, 0, 1)
    assert result.ungraded_m == 0.0


def test_max_ele_is_the_path_maximum_not_an_endpoint():
    # a path over a col must report the col, not the higher of the two huts
    subgraph = _col_subgraph()
    graph, _, vertex_coords = _build_igraph_with_snaps(subgraph, {})
    result = _path_for(graph, vertex_coords, 0, 2)
    ele_at_src, ele_at_tgt = 1000.0, 1200.0
    assert result.max_ele_m > max(ele_at_src, ele_at_tgt)
    assert result.max_ele_m == pytest.approx(1500.0)


def test_ascent_and_descent_swap_on_reverse_traversal():
    subgraph = _col_subgraph()
    graph, _, vertex_coords = _build_igraph_with_snaps(subgraph, {})
    fwd = _path_for(graph, vertex_coords, 0, 2)
    rev = _path_for(graph, vertex_coords, 2, 0)
    assert rev.ascent_m == pytest.approx(fwd.descent_m)
    assert rev.descent_m == pytest.approx(fwd.ascent_m)


def test_base_igraph_arrays_reused_across_variants_matches_per_call_build():
    # opt #1: _build_base_igraph_arrays is computed once per cell and reused across variants via
    # _build_igraph_from_base - must produce the exact same graph as the old
    # (single-call-per-variant) _build_igraph_with_snaps for each mask.
    subgraph = _line_subgraph_t2_graded()
    base = _build_base_igraph_arrays(subgraph, {})
    mask = variants.edge_mask(subgraph.local_edges, variants.VARIANTS[binfmt.VARIANT_FAST_T3])

    reused_graph, reused_hub_vertex, reused_coords = _build_igraph_from_base(base, edge_mask=mask)
    direct_graph, direct_hub_vertex, direct_coords = _build_igraph_with_snaps(
        subgraph, {}, edge_mask=mask
    )

    assert reused_graph.ecount() == direct_graph.ecount()
    assert reused_graph.es["time_s"] == direct_graph.es["time_s"]
    assert reused_hub_vertex == direct_hub_vertex
    assert reused_coords == direct_coords


def test_base_igraph_arrays_reuse_keeps_variants_independent():
    # a mask applied via one _build_igraph_from_base call must not leak into the next - each call
    # must derive kept_mask fresh from base.edge_source, not mutate anything on `base`.
    subgraph = _two_edge_subgraph()
    base = _build_base_igraph_arrays(subgraph, {})
    all_kept, _, _ = _build_igraph_from_base(base, edge_mask=None)
    one_dropped, _, _ = _build_igraph_from_base(base, edge_mask=np.array([True, False]))
    all_kept_again, _, _ = _build_igraph_from_base(base, edge_mask=None)
    assert one_dropped.ecount() < all_kept.ecount()
    assert all_kept_again.ecount() == all_kept.ecount()


def test_batched_paths_match_per_target_path_for():
    # opt #2: compute_hub_edges_for_cell now fetches every in-cutoff target's path for a hub in
    # one get_shortest_paths call instead of one call per target - the per-pair result must be
    # identical to the old one-call-per-target _path_for.
    subgraph = _col_subgraph()
    graph, hub_vertex, vertex_coords = _build_igraph_with_snaps(subgraph, {})
    individual = [_path_for(graph, vertex_coords, 0, tv) for tv in (1, 2)]
    epaths = graph.get_shortest_paths(0, to=[1, 2], weights="weight", output="epath")
    from graph_building.build_hub_edges import _accumulate_path
    batched = [
        _accumulate_path(graph, vertex_coords, 0, tv, epath)
        for tv, epath in zip([1, 2], epaths)
    ]
    assert individual == batched


def test_ascent_is_the_sum_the_router_used():
    # spec B3: routing and display cannot disagree, because they are the same numbers - a
    # straight 0->1->2 line where every edge is traversed forward, so the sum of each edge's own
    # ascent_m attr (what the router's path actually walked) must equal the reported total.
    subgraph = _col_subgraph()
    graph, _, vertex_coords = _build_igraph_with_snaps(subgraph, {})
    epath = graph.get_shortest_paths(0, to=2, weights="weight", output="epath")[0]
    result = _path_for(graph, vertex_coords, 0, 2)
    assert result.ascent_m == pytest.approx(sum(graph.es[e]["ascent_m"] for e in epath))


def test_cell_workload_score_scales_with_cached_subgraph_size(tmp_path):
    # gather_route_subgraphs.py already wrote local_edges.npy for this cell before build_hub_edges
    # ever runs - the score must read its byte size straight off disk, no array load.
    big_dir = cell_dir_for(tmp_path, 1)
    small_dir = cell_dir_for(tmp_path, 2)
    big_dir.mkdir(parents=True)
    small_dir.mkdir(parents=True)
    (big_dir / "local_edges.npy").write_bytes(b"\x00" * 1000)
    (small_dir / "local_edges.npy").write_bytes(b"\x00" * 10)
    assert (_cell_workload_score(tmp_path, 1, n_hubs=1)
            > _cell_workload_score(tmp_path, 2, n_hubs=1))


def test_cell_workload_score_scales_with_hub_count(tmp_path):
    cell_dir = cell_dir_for(tmp_path, 1)
    cell_dir.mkdir(parents=True)
    (cell_dir / "local_edges.npy").write_bytes(b"\x00" * 1000)
    assert (_cell_workload_score(tmp_path, 1, n_hubs=5)
            > _cell_workload_score(tmp_path, 1, n_hubs=1))


def test_cell_workload_score_is_zero_for_an_uncached_cell(tmp_path):
    # Defensive only - every hub-bearing cell is guaranteed a cached local_edges.npy by
    # gather_route_subgraphs.py (build_hub_edges.py's task_dep), so this path shouldn't be hit in
    # practice, but a missing file must not crash the sort.
    assert _cell_workload_score(tmp_path, 999, n_hubs=3) == 0
