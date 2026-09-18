import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from postprocessing.build_tour_tiles import build_stats  # noqa: E402




def _tour_leg_record(from_id, to_id, from_type, to_type, distance_m, ascent_m, descent_m,
                      duration_s, max_ele_m, geom_offset, geom_count, profile_offset, profile_count):
    r = np.zeros(1, dtype=binfmt.TOUR_LEG_DTYPE)[0]
    r["from_id"], r["to_id"], r["from_type"], r["to_type"] = from_id, to_id, from_type, to_type
    r["distance_m"], r["ascent_m"], r["descent_m"], r["duration_s"] = (
        distance_m, ascent_m, descent_m, duration_s,
    )
    r["max_ele_m"] = max_ele_m
    r["geom_offset"], r["geom_count"] = geom_offset, geom_count
    r["profile_offset"], r["profile_count"] = profile_offset, profile_count
    return r


def test_build_stats_resolves_ids_via_id_table():
    records = np.array([_tour_leg_record(1, 2, binfmt.TYPE_HUT, binfmt.TYPE_HUT,
                                          1000.0, 50.0, 10.0, 900.0, 1500.0, 0, 2, 0, 3)])
    geometry = np.zeros(2, dtype=binfmt.COORD_DTYPE)
    geometry["lon"], geometry["lat"] = [0.0, 0.01], [0.0, 0.0]
    profiles = np.array([1000.0, 1010.0, 1005.0], dtype=binfmt.PROFILE_DTYPE)
    id_table = {"hut:1": "hut-abc", "hut:2": "hut-xyz"}

    stats, point_counts, geometry_points, profile_counts, elevation_values = build_stats(
        records, geometry, profiles, id_table
    )

    assert len(stats) == 1
    assert "positions" not in stats[0]
    assert "elevation_profile" not in stats[0]
    assert "road_m" not in stats[0]
    assert "sac_scale" not in stats[0]
    assert "via_ferrata" not in stats[0]
    assert stats[0]["from_hut_id"] == "hut-abc"
    assert stats[0]["to_hut_id"] == "hut-xyz"
    assert stats[0]["ascent_m"] == 50.0
    assert stats[0]["duration_s"] == 900.0
    assert point_counts == [2]
    assert geometry_points.shape == (2, 2)
    assert profile_counts == [3]
    assert list(elevation_values) == [1000.0, 1010.0, 1005.0]


def test_geometry_bin_byte_layout_matches_point_counts():
    records = np.array([
        _tour_leg_record(1, 2, binfmt.TYPE_HUT, binfmt.TYPE_HUT, 1000.0, 50.0, 10.0, 900.0,
                          1500.0, 0, 4, 0, 0),
        _tour_leg_record(2, 3, binfmt.TYPE_HUT, binfmt.TYPE_HUT, 800.0, 30.0, 5.0, 700.0,
                          1400.0, 4, 3, 0, 0),
    ])
    geometry = np.zeros(7, dtype=binfmt.COORD_DTYPE)
    geometry["lon"] = [0.0, 0.001, 0.002, 0.003, 0.01, 0.011, 0.012]
    geometry["lat"] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    profiles = np.zeros(0, dtype=binfmt.PROFILE_DTYPE)
    id_table = {"hut:1": 1, "hut:2": 2, "hut:3": 3}

    stats, point_counts, geometry_points, profile_counts, elevation_values = build_stats(
        records, geometry, profiles, id_table
    )
    assert geometry_points.nbytes == 8 * sum(point_counts)


def test_build_stats_keeps_every_raw_geometry_point():
    records = np.zeros(1, dtype=binfmt.TOUR_LEG_DTYPE)
    pts = [(11.0, 47.0), (11.0001, 47.0001), (11.0002, 47.0002), (11.0003, 47.0003)]  # collinear
    geometry = np.zeros(len(pts), dtype=binfmt.COORD_DTYPE)
    geometry["lon"] = [p[0] for p in pts]
    geometry["lat"] = [p[1] for p in pts]
    records[0]["geom_offset"], records[0]["geom_count"] = 0, len(pts)
    stats, point_counts, geometry_points, _, _ = build_stats(
        records, geometry, np.zeros(0, dtype=binfmt.PROFILE_DTYPE), {})
    assert point_counts == [4]
    assert geometry_points.shape == (4, 2)
