import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from preprocessing.filter_start_points import _load_layer, filter_to_hut_range  # noqa: E402

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


def test_load_layer_reads_top_level_feature_id(tmp_path):
    # osmium export --add-unique-id=type_id (fetch_stations_parking.py) puts the id on the
    # Feature itself as "<type-char><digits>" (e.g. "n8091317"), not inside "properties" -
    # regression test for the bug where _load_layer looked in properties and silently dropped
    # every feature, leaving start_points.npy empty.
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "id": "n8091317",
             "geometry": {"type": "Point", "coordinates": [16.31, 48.21]},
             "properties": {"name": "Wien Ottakring"}},
            {"type": "Feature", "id": "w21261052",
             "geometry": {"type": "Point", "coordinates": [15.44, 47.07]},
             "properties": {"name": "Burgring Garage"}},
        ],
    }
    path = tmp_path / "stations.geojson"
    path.write_text(json.dumps(fc), encoding="utf-8")

    points = _load_layer(path, "station")

    assert len(points) == 2
    assert points[0]["osm_id"] == 8091317
    assert points[1]["osm_id"] == 21261052
    assert points[0]["lon"] == 16.31 and points[0]["lat"] == 48.21


def test_preserves_input_order_of_survivors():
    points = [
        {"lon": 10.01, "lat": 47.0, "osm_id": 1, "type": "parking"},
        {"lon": 20.0, "lat": 47.0, "osm_id": 2, "type": "station"},
        {"lon": 10.99, "lat": 47.0, "osm_id": 3, "type": "parking"},
    ]
    kept = filter_to_hut_range(points, HUT_COORDS, max_edge_km=5.0)
    assert [p["osm_id"] for p in kept] == [1, 3]
