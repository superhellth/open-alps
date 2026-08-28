import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from preprocessing.filter_start_points import (  # noqa: E402
    _load_layer,
    build_id_table,
    filter_to_hut_range,
)

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


def test_load_layer_reads_id_from_properties_for_non_osm_sources(tmp_path):
    # partner_betriebe.geojson (fetch_huts.py, Task 2) is not OSM data - id is a plain int
    # already sitting in properties["id"] (the ArcGIS layer's OBJECTID), not a "n12345"-shaped
    # top-level Feature id the way stations/parking (osmium export) have.
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature",
             "geometry": {"type": "Point", "coordinates": [11.5, 47.3]},
             "properties": {"id": 502, "name": "Gasthof Alpenrose"}},
        ],
    }
    path = tmp_path / "partner_betriebe.geojson"
    path.write_text(json.dumps(fc), encoding="utf-8")

    points = _load_layer(path, "partner_betrieb", id_from_properties=True)

    assert len(points) == 1
    assert points[0]["osm_id"] == 502
    assert points[0]["type"] == "partner_betrieb"
    assert points[0]["lon"] == 11.5 and points[0]["lat"] == 47.3


def test_default_id_from_properties_is_false_existing_osm_behavior_unchanged(tmp_path):
    # regression: Task 3 must not change the default path used by stations.geojson/parking.geojson
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "id": "n8091317",
             "geometry": {"type": "Point", "coordinates": [16.31, 48.21]},
             "properties": {"name": "Wien Ottakring"}},
        ],
    }
    path = tmp_path / "stations.geojson"
    path.write_text(json.dumps(fc), encoding="utf-8")

    points = _load_layer(path, "station")

    assert points[0]["osm_id"] == 8091317


def test_start_points_retain_access_tags():
    table = build_id_table([
        {"type": "parking", "id": 1, "lon": 11.0, "lat": 47.0,
         "properties": {"name": "P", "access": "private", "motor_vehicle": "no"}},
    ])
    assert table["parking"]["1"]["access"] == "private"
    assert table["parking"]["1"]["motor_vehicle"] == "no"


def test_missing_access_becomes_none_not_absent():
    # spec E1: absent tag -> keep but mark access_unknown. Dropping the key makes "unknown"
    # and "open" indistinguishable downstream.
    table = build_id_table([{"type": "parking", "id": 2, "lon": 11.0, "lat": 47.0,
                            "properties": {"name": "Q"}}])
    assert table["parking"]["2"]["access"] is None


def test_preserves_input_order_of_survivors():
    points = [
        {"lon": 10.01, "lat": 47.0, "osm_id": 1, "type": "parking"},
        {"lon": 20.0, "lat": 47.0, "osm_id": 2, "type": "station"},
        {"lon": 10.99, "lat": 47.0, "osm_id": 3, "type": "parking"},
    ]
    kept = filter_to_hut_range(points, HUT_COORDS, max_edge_km=5.0)
    assert [p["osm_id"] for p in kept] == [1, 3]
