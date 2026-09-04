import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from quality.check_elevation import (  # noqa: E402
    check_elevation_range, check_implied_speed, check_profile_integrity,
    check_unresolved_sentinels,
)


def test_elevation_range_flags_nan_and_out_of_range():
    node_ele = np.array([120.0, float("nan"), 5000.0], dtype="f4")
    interior_ele = np.array([200.0], dtype="f4")
    check = check_elevation_range(node_ele, interior_ele, (-50, 4300), max_flagged=500)
    assert check["summary"]["checked"] == 4
    assert check["summary"]["flagged"] == 2


def test_elevation_range_clean_case_flags_nothing():
    node_ele = np.array([120.0, 3793.5], dtype="f4")
    interior_ele = np.array([119.7], dtype="f4")
    check = check_elevation_range(node_ele, interior_ele, (-50, 4300), max_flagged=500)
    assert check["summary"]["flagged"] == 0


def _edge(u=0, v=1, dist=100.0, time_s=100.0, ascent=10.0, descent=5.0, edge_id=0):
    e = np.zeros(1, dtype=binfmt.EDGE_DTYPE)[0]
    e["u"], e["v"], e["dist"], e["time_s"] = u, v, dist, time_s
    e["ascent_m"], e["descent_m"], e["edge_id"] = ascent, descent, edge_id
    return e


def test_unresolved_sentinels_flags_unset_time_s():
    edges = np.array([_edge(time_s=binfmt.UNSET), _edge(time_s=100.0, edge_id=1)])
    check = check_unresolved_sentinels(edges, max_flagged=500)
    assert check["summary"]["flagged"] == 1
    assert check["flagged"][0]["edge_id"] == 0


def test_implied_speed_flags_below_threshold():
    slow = _edge(dist=10.0, time_s=1000.0, edge_id=0)   # 0.01 m/s
    fast = _edge(dist=1000.0, time_s=1000.0, edge_id=1)  # 1.0 m/s
    edges = np.array([slow, fast])
    check = check_implied_speed(edges, min_speed_ms=0.05, max_flagged=500)
    assert check["summary"]["flagged"] == 1
    assert check["flagged"][0]["edge_id"] == 0


def test_implied_speed_skips_zero_time_s():
    edges = np.array([_edge(dist=0.0, time_s=0.0, edge_id=0)])
    check = check_implied_speed(edges, min_speed_ms=0.05, max_flagged=500)
    assert check["summary"]["checked"] == 1
    assert check["summary"]["flagged"] == 0


def _record(profile_offset, profile_count, geom_count):
    r = np.zeros(1, dtype=binfmt.RECORD_DTYPE)[0]
    r["profile_offset"], r["profile_count"], r["geom_count"] = profile_offset, profile_count, geom_count
    return r


def test_profile_integrity_flags_zero_count_with_nonzero_geometry():
    records = np.array([_record(0, 0, geom_count=5)])
    profiles = np.zeros(0, dtype=binfmt.PROFILE_DTYPE)
    check = check_profile_integrity(records, profiles, profile_points=30, layer_name="hut_edges",
                                     max_flagged=500)
    assert check["summary"]["flagged"] == 1
    assert check["flagged"][0]["reason"] == "zero_profile_nonzero_geometry"


def test_profile_integrity_flags_offset_past_end_of_profiles():
    records = np.array([_record(0, 30, geom_count=5)])
    profiles = np.zeros(10, dtype=binfmt.PROFILE_DTYPE)  # offset 0 + count 30 > len 10
    check = check_profile_integrity(records, profiles, profile_points=30, layer_name="hut_edges",
                                     max_flagged=500)
    assert any(r["reason"] == "offset_past_end" for r in check["flagged"])


def test_profile_integrity_flags_wrong_point_count():
    records = np.array([_record(0, 15, geom_count=5)])
    profiles = np.zeros(15, dtype=binfmt.PROFILE_DTYPE)
    check = check_profile_integrity(records, profiles, profile_points=30, layer_name="hut_edges",
                                     max_flagged=500)
    assert any(r["reason"] == "wrong_point_count" for r in check["flagged"])


def test_profile_integrity_clean_case_flags_nothing():
    records = np.array([_record(0, 30, geom_count=5)])
    profiles = np.zeros(30, dtype=binfmt.PROFILE_DTYPE)
    check = check_profile_integrity(records, profiles, profile_points=30, layer_name="hut_edges",
                                     max_flagged=500)
    assert check["summary"]["flagged"] == 0
