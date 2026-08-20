import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from elevation.add_elevation import elevation_profile, fill_elevation_records  # noqa: E402


def _one_record_fixture():
    records = np.zeros(1, dtype=binfmt.RECORD_DTYPE)
    records[0] = (1, 2, binfmt.TYPE_HUT, binfmt.TYPE_HUT, binfmt.VARIANT_SHORTEST,
                  1000.0, 0.0, binfmt.UNSET, binfmt.UNSET, -1, False, 0, 3, 0, 0)
    geometry = np.zeros(3, dtype=binfmt.COORD_DTYPE)
    geometry["lon"] = [0.0, 0.005, 0.01]
    geometry["lat"] = [0.0, 0.0, 0.0]
    elevations = np.array([1000.0, 1010.0, 1000.0])  # up then down
    return records, geometry, elevations


def test_fill_elevation_records_sets_ascent_descent():
    records, geometry, elevations = _one_record_fixture()
    updated, profiles = fill_elevation_records(
        records, geometry, elevations, profile_points=5, noise_threshold_m=1.0
    )
    assert updated[0]["ascent_m"] == 10.0
    assert updated[0]["descent_m"] == 10.0


def test_elevation_profile_vectorized_distance_matches_expected_values():
    # 3 equally-spaced points on the equator (lat=0) -> two equal-length segments, so with
    # n_points=3 the interpolation targets land exactly on the original samples - locks in the
    # vectorized cumsum-based cumulative distance against a known result.
    lon = np.array([0.0, 0.005, 0.01])
    lat = np.array([0.0, 0.0, 0.0])
    samples = np.array([1000.0, 1010.0, 1000.0])
    profile = elevation_profile(lon, lat, samples, n_points=3)
    assert profile == [1000.0, 1010.0, 1000.0]


def test_fill_elevation_records_writes_profile_offsets_sequentially():
    records = np.zeros(2, dtype=binfmt.RECORD_DTYPE)
    records[0] = (1, 2, binfmt.TYPE_HUT, binfmt.TYPE_HUT, 0, 1000.0, 0.0, -1, -1, -1, False,
                  0, 3, 0, 0)
    records[1] = (2, 3, binfmt.TYPE_HUT, binfmt.TYPE_HUT, 0, 500.0, 0.0, -1, -1, -1, False,
                  3, 2, 0, 0)
    geometry = np.zeros(5, dtype=binfmt.COORD_DTYPE)
    geometry["lon"] = [0.0, 0.005, 0.01, 0.02, 0.025]
    geometry["lat"] = [0.0] * 5
    elevations = np.array([1000.0, 1010.0, 1000.0, 900.0, 910.0])

    updated, profiles = fill_elevation_records(
        records, geometry, elevations, profile_points=4, noise_threshold_m=1.0
    )

    assert updated[0]["profile_offset"] == 0
    assert updated[0]["profile_count"] == 4
    assert updated[1]["profile_offset"] == 4
    assert updated[1]["profile_count"] == 4
    assert len(profiles) == 8
