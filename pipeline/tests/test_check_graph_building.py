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
