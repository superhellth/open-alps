import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from postprocessing.build_edge_tiles import build_stats, rdp_keep_indices  # noqa: E402


def test_rdp_keep_indices_collapses_straight_line():
    coords = np.array([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)])
    keep = rdp_keep_indices(coords, epsilon=0.01)
    assert list(keep) == [0, 3]


def test_rdp_keep_indices_preserves_a_corner():
    coords = np.array([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])
    keep = rdp_keep_indices(coords, epsilon=0.01)
    assert 1 in keep


def test_build_stats_resolves_ids_via_id_table():
    records = np.zeros(1, dtype=binfmt.RECORD_DTYPE)
    records[0] = (1, 2, binfmt.TYPE_HUT, binfmt.TYPE_HUT, 0, 1000.0, 0.0, 50.0, 10.0,
                  1500.0, 0.0, 0.0, 0.0, 2, False,
                  0, 2, 0, 3,
                  0, 0, (-1,) * 8, 0, (-1,) * 8, 0)
    geometry = np.zeros(2, dtype=binfmt.COORD_DTYPE)
    geometry["lon"], geometry["lat"] = [0.0, 0.01], [0.0, 0.0]
    profiles = np.array([1000.0, 1010.0, 1005.0], dtype=binfmt.PROFILE_DTYPE)
    id_table = {"hut:1": "hut-abc", "hut:2": "hut-xyz"}

    stats, point_counts, geometry_points, profile_counts, elevation_values = build_stats(
        records, geometry, profiles, id_table, simplify_tolerance_deg=0.001
    )

    assert len(stats) == 1
    assert "positions" not in stats[0]
    assert "elevation_profile" not in stats[0]
    assert stats[0]["from_hut_id"] == "hut-abc"
    assert stats[0]["to_hut_id"] == "hut-xyz"
    assert stats[0]["ascent_m"] == 50.0
    assert point_counts == [2]
    assert geometry_points.shape == (2, 2)
    assert profile_counts == [3]
    assert list(elevation_values) == [1000.0, 1010.0, 1005.0]


def test_geometry_bin_byte_layout_matches_point_counts():
    records = np.zeros(2, dtype=binfmt.RECORD_DTYPE)
    records[0] = (1, 2, binfmt.TYPE_HUT, binfmt.TYPE_HUT, 0, 1000.0, 0.0, 50.0, 10.0,
                  1500.0, 0.0, 0.0, 0.0, 2, False, 0, 4, 0, 0,
                  0, 0, (-1,) * 8, 0, (-1,) * 8, 0)
    records[1] = (2, 3, binfmt.TYPE_HUT, binfmt.TYPE_HUT, 0, 800.0, 0.0, 30.0, 5.0,
                  1400.0, 0.0, 0.0, 0.0, -1, False, 4, 3, 0, 0,
                  0, 0, (-1,) * 8, 0, (-1,) * 8, 0)
    geometry = np.zeros(7, dtype=binfmt.COORD_DTYPE)
    geometry["lon"] = [0.0, 1.0, 2.0, 3.0, 10.0, 11.0, 12.0]
    geometry["lat"] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    profiles = np.zeros(0, dtype=binfmt.PROFILE_DTYPE)

    stats, point_counts, geometry_points, profile_counts, elevation_values = build_stats(
        records, geometry, profiles, {}, simplify_tolerance_deg=0.01
    )

    assert len(point_counts) == 2
    geometry_bin = geometry_points.astype("f4").tobytes()
    assert len(geometry_bin) == sum(point_counts) * 8
    # prefix sums land on real point boundaries: each edge's own point_counts[i] entry is
    # exactly the row-count of the slice build_stats appended for that edge.
    offset = 0
    for i, count in enumerate(point_counts):
        edge_points = geometry_points[offset:offset + count]
        assert len(edge_points) == count
        offset += count
    assert offset == len(geometry_points)


def test_build_stats_drops_elevation_profile_from_stats_and_returns_it_separately():
    records = np.zeros(1, dtype=binfmt.RECORD_DTYPE)
    records[0] = (1, 2, binfmt.TYPE_HUT, binfmt.TYPE_HUT, 0, 1000.0, 0.0, 50.0, 10.0,
                  1500.0, 0.0, 0.0, 0.0, 2, False,
                  0, 2, 0, 3,
                  0, 0, (-1,) * 8, 0, (-1,) * 8, 0)
    geometry = np.zeros(2, dtype=binfmt.COORD_DTYPE)
    geometry["lon"], geometry["lat"] = [0.0, 0.01], [0.0, 0.0]
    profiles = np.array([1000.0, 1010.0, 1005.0], dtype=binfmt.PROFILE_DTYPE)
    id_table = {"hut:1": "hut-abc", "hut:2": "hut-xyz"}

    stats, point_counts, geometry_points, profile_counts, elevation_values = build_stats(
        records, geometry, profiles, id_table, simplify_tolerance_deg=0.001
    )

    assert "elevation_profile" not in stats[0]
    assert profile_counts == [3]
    assert list(elevation_values) == [1000.0, 1010.0, 1005.0]
    assert elevation_values.dtype == np.dtype("f4")


def test_build_stats_degenerate_edge_has_zero_profile_count():
    records = np.zeros(1, dtype=binfmt.RECORD_DTYPE)
    # profile_offset=0, profile_count=0 - degenerate edge, geom_count < 2 upstream.
    records[0] = (1, 2, binfmt.TYPE_HUT, binfmt.TYPE_HUT, 0, 1000.0, 0.0, 0.0, 0.0,
                  1500.0, 0.0, 0.0, 0.0, -1, False,
                  0, 1, 0, 0,
                  0, 0, (-1,) * 8, 0, (-1,) * 8, 0)
    geometry = np.zeros(1, dtype=binfmt.COORD_DTYPE)
    geometry["lon"], geometry["lat"] = [0.0], [0.0]
    profiles = np.zeros(0, dtype=binfmt.PROFILE_DTYPE)

    stats, point_counts, geometry_points, profile_counts, elevation_values = build_stats(
        records, geometry, profiles, {}, simplify_tolerance_deg=0.001
    )

    assert profile_counts == [0]
    assert elevation_values.shape == (0,)


def test_elevation_bin_byte_layout_matches_profile_counts():
    records = np.zeros(2, dtype=binfmt.RECORD_DTYPE)
    records[0] = (1, 2, binfmt.TYPE_HUT, binfmt.TYPE_HUT, 0, 1000.0, 0.0, 50.0, 10.0,
                  1500.0, 0.0, 0.0, 0.0, 2, False, 0, 4, 0, 2,
                  0, 0, (-1,) * 8, 0, (-1,) * 8, 0)
    records[1] = (2, 3, binfmt.TYPE_HUT, binfmt.TYPE_HUT, 0, 800.0, 0.0, 30.0, 5.0,
                  1400.0, 0.0, 0.0, 0.0, -1, False, 4, 3, 2, 3,
                  0, 0, (-1,) * 8, 0, (-1,) * 8, 0)
    geometry = np.zeros(7, dtype=binfmt.COORD_DTYPE)
    geometry["lon"] = [0.0, 1.0, 2.0, 3.0, 10.0, 11.0, 12.0]
    geometry["lat"] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    profiles = np.array([100.0, 101.0, 200.0, 201.0, 202.0], dtype=binfmt.PROFILE_DTYPE)

    stats, point_counts, geometry_points, profile_counts, elevation_values = build_stats(
        records, geometry, profiles, {}, simplify_tolerance_deg=0.01
    )

    assert profile_counts == [2, 3]
    elevation_bin = elevation_values.tobytes()
    assert len(elevation_bin) == sum(profile_counts) * 4
    offset = 0
    for i, count in enumerate(profile_counts):
        edge_values = elevation_values[offset:offset + count]
        assert len(edge_values) == count
        offset += count
    assert offset == len(elevation_values)
    assert list(elevation_values) == [100.0, 101.0, 200.0, 201.0, 202.0]


def test_type_prefix_includes_partner_betrieb():
    from postprocessing.build_edge_tiles import TYPE_PREFIX

    assert TYPE_PREFIX[binfmt.TYPE_PARTNER] == "partner_betrieb"
