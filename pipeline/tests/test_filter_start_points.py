import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from filter_start_points import filter_to_hut_range  # noqa: E402

HUT_COORDS = np.array([(10.0, 47.0), (11.0, 47.0)])


def test_keeps_point_within_range_of_a_hut():
    points = [{"lon": 10.01, "lat": 47.0, "osm_id": 1, "type": "parking"}]
    kept = filter_to_hut_range(points, HUT_COORDS, max_edge_km=5.0)
    assert len(kept) == 1


def test_drops_point_far_from_every_hut():
    points = [{"lon": 20.0, "lat": 47.0, "osm_id": 2, "type": "station"}]
    kept = filter_to_hut_range(points, HUT_COORDS, max_edge_km=5.0)
    assert len(kept) == 0


def test_keeps_point_near_the_second_hut_only():
    points = [{"lon": 10.99, "lat": 47.0, "osm_id": 3, "type": "parking"}]
    kept = filter_to_hut_range(points, HUT_COORDS, max_edge_km=5.0)
    assert len(kept) == 1
    assert kept[0]["osm_id"] == 3


def test_preserves_input_order_of_survivors():
    points = [
        {"lon": 10.01, "lat": 47.0, "osm_id": 1, "type": "parking"},
        {"lon": 20.0, "lat": 47.0, "osm_id": 2, "type": "station"},
        {"lon": 10.99, "lat": 47.0, "osm_id": 3, "type": "parking"},
    ]
    kept = filter_to_hut_range(points, HUT_COORDS, max_edge_km=5.0)
    assert [p["osm_id"] for p in kept] == [1, 3]
