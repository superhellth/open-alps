import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases" / "elevation"))

import build_profiles as bp  # noqa: E402


def test_lookup_matches_exact_coordinates():
    nodes = np.zeros(2, dtype=[("lon", "f8"), ("lat", "f8")])
    nodes["lon"], nodes["lat"] = [11.0, 11.1], [47.0, 47.1]
    interior = np.zeros(1, dtype=[("lon", "f8"), ("lat", "f8")])
    interior["lon"], interior["lat"] = [11.05], [47.05]
    node_ele = np.array([1000.0, 1100.0], dtype=np.float32)
    interior_ele = np.array([1050.0], dtype=np.float32)

    keys, values = bp.build_elevation_lookup(nodes, interior, node_ele, interior_ele)
    got = bp.lookup_elevations(np.array([11.0, 11.05, 11.1]), np.array([47.0, 47.05, 47.1]),
                               keys, values)
    assert got.tolist() == [1000.0, 1050.0, 1100.0]


def test_lookup_returns_nan_for_unmatched_point():
    nodes = np.zeros(1, dtype=[("lon", "f8"), ("lat", "f8")])
    nodes["lon"], nodes["lat"] = [11.0], [47.0]
    interior = np.zeros(0, dtype=[("lon", "f8"), ("lat", "f8")])
    keys, values = bp.build_elevation_lookup(nodes, interior, np.array([1000.0], dtype=np.float32),
                                             np.zeros(0, dtype=np.float32))
    got = bp.lookup_elevations(np.array([12.0]), np.array([48.0]), keys, values)
    assert np.isnan(got[0])


def test_fill_unmatched_carries_nearest_neighbour_forward_and_backward():
    # hub endpoints (index 0, 3) are never base-graph points - both ends must be filled
    profile = np.array([np.nan, 1000.0, 1010.0, np.nan])
    filled = bp._fill_unmatched(profile)
    assert filled.tolist() == [1000.0, 1000.0, 1010.0, 1010.0]


def test_elevation_profile_interpolates_onto_n_points():
    lon = np.array([11.0, 11.001, 11.002])
    lat = np.array([47.0, 47.0, 47.0])
    samples = np.array([1000.0, 1010.0, 1020.0])
    profile = bp.elevation_profile(lon, lat, samples, n_points=5)
    assert len(profile) == 5
    assert profile[0] == 1000.0
    assert profile[-1] == 1020.0
