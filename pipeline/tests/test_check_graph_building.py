import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from quality.check_graph_building import (  # noqa: E402
    check_connectivity, check_range_cap, check_snap_health, check_tour_gaps,
    union_find_components,
)


def test_union_find_components_merges_connected_nodes():
    # nodes 0-1-2 connected, node 3 isolated
    components = union_find_components(4, [(0, 1), (1, 2)])
    assert components[0] == components[1] == components[2]
    assert components[3] != components[0]


def test_union_find_components_all_isolated_when_no_edges():
    components = union_find_components(3, [])
    assert len(set(components)) == 3


def test_snap_health_counts_distinct_huts_not_entries():
    # §4.3.1: unsnapped_huts.json has one entry per rejection reason, so 1 hub with 2 reasons must
    # count as 1 distinct hub, not 2.
    unsnapped = [
        {"hub_id": 5, "hub_type": binfmt.TYPE_HUT, "reason": "gap_too_far"},
        {"hub_id": 5, "hub_type": binfmt.TYPE_HUT, "reason": "vertical_offset"},
        {"hub_id": 8, "hub_type": binfmt.TYPE_HUT, "reason": "gap_too_far"},
    ]
    check = check_snap_health(unsnapped, max_flagged=500)
    assert check["summary"]["flagged"] == 2  # distinct (hub_type, hub_id) pairs
    assert check["summary"]["checked"] == 3  # total entries


def _hut_record(from_id, to_id, variant=binfmt.VARIANT_FAST_ANY):
    r = np.zeros(1, dtype=binfmt.RECORD_DTYPE)[0]
    r["from_id"], r["to_id"], r["from_type"], r["to_type"], r["variant"] = (
        from_id, to_id, binfmt.TYPE_HUT, binfmt.TYPE_HUT, variant,
    )
    return r


def test_connectivity_reports_isolated_huts_per_variant():
    # hut 0-1 connected on FAST_ANY, hut 2 isolated on every variant
    records = np.array([_hut_record(0, 1, binfmt.VARIANT_FAST_ANY)])
    check = check_connectivity(records, n_huts=3, max_flagged=500)
    fast_any = next(c for c in check["flagged"] if c["variant"] == "FAST_ANY")
    assert fast_any["isolated_huts"] == 1
    assert fast_any["components"] == 2  # {0,1} and {2}


def test_connectivity_fully_connected_variant_is_not_flagged():
    records = np.array([_hut_record(0, 1)])
    check = check_connectivity(records, n_huts=2, max_flagged=500)
    fast_any = next(c for c in check["flagged"] if c["variant"] == "FAST_ANY")
    assert fast_any["isolated_huts"] == 0
    assert fast_any["components"] == 1


def _access_record(distance_m):
    r = np.zeros(1, dtype=binfmt.RECORD_DTYPE)[0]
    r["from_id"], r["to_id"], r["distance_m"] = 1, 2, distance_m
    return r


def test_range_cap_flags_distance_over_the_configured_max():
    records = np.array([_access_record(31_000.0), _access_record(1000.0)])
    check = check_range_cap(records, "hut_edges", max_edge_km=30, max_flagged=500)
    assert check["summary"]["flagged"] == 1
    assert check["flagged"][0]["distance_m"] == 31_000.0


def test_tour_gaps_reshapes_gap_entries_into_flagged_rows():
    gaps = [{"tourId": 0, "tourName": "Kaisertour", "legIndex": 1,
              "reason": "leg_endpoint_unsnapped", "detail": {"endpoint": "from"}}]
    check = check_tour_gaps(gaps, max_flagged=500)
    assert check["summary"]["flagged"] == 1
    assert check["flagged"][0]["tourName"] == "Kaisertour"
    assert check["flagged"][0]["reason"] == "leg_endpoint_unsnapped"


from quality.check_graph_building import (  # noqa: E402 (extend the existing import line)
    check_scalar_sanity, check_self_retrace, check_vertex_gap, polyline_for_base_edge,
    polyline_for_record,
)


def test_polyline_for_record_slices_geometry_by_offset_and_count():
    geometry = np.zeros(5, dtype=binfmt.COORD_DTYPE)
    geometry["lon"] = [0, 1, 2, 3, 4]
    geometry["lat"] = [0, 0, 0, 0, 0]
    record = np.zeros(1, dtype=binfmt.RECORD_DTYPE)[0]
    record["geom_offset"], record["geom_count"] = 1, 3
    coords = polyline_for_record(record, geometry)
    assert coords.tolist() == [[1, 0], [2, 0], [3, 0]]


def test_polyline_for_base_edge_concatenates_node_interior_node():
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes["lon"], nodes["lat"] = [0.0, 2.0], [0.0, 0.0]
    interior = np.zeros(1, dtype=binfmt.COORD_DTYPE)
    interior["lon"], interior["lat"] = [1.0], [0.0]
    edge = np.zeros(1, dtype=binfmt.EDGE_DTYPE)[0]
    edge["u"], edge["v"], edge["interior_offset"], edge["interior_count"] = 0, 1, 0, 1
    coords = polyline_for_base_edge(edge, nodes, interior)
    assert coords.tolist() == [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]]


def _poly_row(lons, lats, **identity):
    coords = np.column_stack([lons, lats]).astype(np.float64)
    return (identity, coords)


def test_vertex_gap_flags_a_long_hop_between_consecutive_vertices():
    # ~0.01 deg longitude at the equator is ~1.1km - use a big jump to be unambiguous regardless
    # of latitude-dependent scaling.
    polylines = [_poly_row([11.0, 11.0, 11.5], [47.0, 47.001, 47.001], from_id=1, to_id=2, variant="FAST_ANY")]
    check = check_vertex_gap(polylines, "hut_edges", max_gap_m=500, max_flagged=500)
    assert check["summary"]["flagged"] == 1
    assert check["flagged"][0]["max_gap_m"] > 500


def test_vertex_gap_does_not_flag_dense_polyline():
    lons = np.linspace(11.0, 11.001, 20)
    lats = np.full(20, 47.0)
    polylines = [_poly_row(lons, lats, from_id=1, to_id=2, variant="FAST_ANY")]
    check = check_vertex_gap(polylines, "hut_edges", max_gap_m=500, max_flagged=500)
    assert check["summary"]["flagged"] == 0


def test_self_retrace_flags_a_far_apart_revisit_of_the_same_cell():
    # a path that returns to (near) its own start after going far away and coming back - separated
    # by well over 200m of path length.
    lons = [11.0, 11.01, 11.0]
    lats = [47.0, 47.0, 47.0]
    polylines = [_poly_row(lons, lats, from_id=1, to_id=2, variant="FAST_ANY")]
    check = check_self_retrace(polylines, "hut_edges", snap_tolerance_m=5, min_separation_m=200,
                                max_flagged=500)
    assert check["summary"]["flagged"] == 1


def test_self_retrace_does_not_flag_a_nearby_switchback():
    # consecutive points revisiting a cell within the separation window must NOT flag (spec:
    # naive 5m-only rule flags 98.5% of real trail geometry at switchbacks).
    lons = [11.0, 11.00002, 11.00004]
    lats = [47.0, 47.0, 47.0]
    polylines = [_poly_row(lons, lats, from_id=1, to_id=2, variant="FAST_ANY")]
    check = check_self_retrace(polylines, "hut_edges", snap_tolerance_m=5, min_separation_m=200,
                                max_flagged=500)
    assert check["summary"]["flagged"] == 0


def _scalar_record(max_ele_m=1000.0, ascent_m=100.0, descent_m=100.0, distance_m=1000.0):
    r = np.zeros(1, dtype=binfmt.RECORD_DTYPE)[0]
    r["max_ele_m"], r["ascent_m"], r["descent_m"], r["distance_m"] = (
        max_ele_m, ascent_m, descent_m, distance_m,
    )
    return r


def test_scalar_sanity_flags_max_ele_below_dem_minimum():
    records = np.array([_scalar_record(max_ele_m=0.0)])
    check = check_scalar_sanity(records, "start_edges", ascent_cap_m=5000, dem_min_ele_m=120.0,
                                 max_flagged=500)
    assert any(r["reason"] == "max_ele_below_dem_minimum" for r in check["flagged"])


def test_scalar_sanity_flags_ascent_over_cap():
    records = np.array([_scalar_record(ascent_m=6000.0)])
    check = check_scalar_sanity(records, "start_edges", ascent_cap_m=5000, dem_min_ele_m=120.0,
                                 max_flagged=500)
    assert any(r["reason"] == "ascent_over_cap" for r in check["flagged"])


def test_scalar_sanity_flags_negative_distance_ascent_descent():
    records = np.array([_scalar_record(distance_m=-1.0, ascent_m=-1.0, descent_m=-1.0)])
    check = check_scalar_sanity(records, "start_edges", ascent_cap_m=5000, dem_min_ele_m=120.0,
                                 max_flagged=500)
    reasons = {r["reason"] for r in check["flagged"]}
    assert {"negative_distance", "negative_ascent", "negative_descent"} <= reasons


def test_scalar_sanity_clean_case_flags_nothing():
    records = np.array([_scalar_record()])
    check = check_scalar_sanity(records, "start_edges", ascent_cap_m=5000, dem_min_ele_m=120.0,
                                 max_flagged=500)
    assert check["summary"]["flagged"] == 0
