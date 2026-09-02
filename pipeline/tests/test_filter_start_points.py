import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from preprocessing.filter_start_points import (  # noqa: E402
    _load_arcgis_layer,
    _load_osm_export_layer,
    build_id_table,
    dedupe_by_osm_id,
    filter_to_hut_range,
    is_usable,
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


def test_keeps_a_point_due_east_at_the_true_km_distance():
    # Regression for spec C1: the old filter thresholded at max_edge_km/111.320 degrees - the
    # km-per-degree of LATITUDE, not longitude. At 47.5N a degree of longitude is ~75.2km, so a
    # point exactly 20km due east of a hut (well inside a 30km cap) sat at 20/75.2 = 0.266 deg,
    # OUTSIDE the old 30/111.320 = 0.269deg threshold by a hair for some points, and farther out
    # points up to ~30km east were dropped outright even though they're inside range. Use a point
    # at a longitude offset that is trail-irrelevant-but-real-world-close: 25km due east at
    # 47.5N is 25/75.2 = 0.3325 deg of longitude - OUTSIDE the old latitude-based threshold
    # (30/111.320 = 0.2695 deg) even though 25km < 30km max_edge_km.
    lat = 47.5
    hut_coords = np.array([(11.0, lat)])
    lon_offset_deg_for_25km_east = 25.0 / (111.320 * np.cos(np.radians(lat)))
    points = [{"lon": 11.0 + lon_offset_deg_for_25km_east, "lat": lat, "osm_id": 1, "type": "parking"}]
    kept = filter_to_hut_range(points, hut_coords, max_edge_km=30.0)
    assert len(kept) == 1


def test_still_drops_a_point_genuinely_farther_than_max_edge_km_in_any_direction():
    lat = 47.5
    hut_coords = np.array([(11.0, lat)])
    lon_offset_deg_for_50km_east = 50.0 / (111.320 * np.cos(np.radians(lat)))
    points = [{"lon": 11.0 + lon_offset_deg_for_50km_east, "lat": lat, "osm_id": 1, "type": "parking"}]
    kept = filter_to_hut_range(points, hut_coords, max_edge_km=30.0)
    assert len(kept) == 0


def test_still_drops_a_point_genuinely_far_north_south():
    # sanity check that the latitude axis (unaffected by the bug) still behaves correctly after
    # the fix - km-per-degree of latitude is ~constant everywhere, so no projection is needed
    # there, only on longitude.
    hut_coords = np.array([(11.0, 47.0)])
    points = [{"lon": 11.0, "lat": 47.0 + 1.0, "osm_id": 1, "type": "parking"}]  # ~111km north
    kept = filter_to_hut_range(points, hut_coords, max_edge_km=30.0)
    assert len(kept) == 0


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

    points = _load_osm_export_layer(path, "station")

    assert len(points) == 2
    assert points[0]["osm_id"] == 8091317
    assert points[1]["osm_id"] == 21261052
    assert points[0]["lon"] == 16.31 and points[0]["lat"] == 48.21


def test_load_arcgis_layer_reads_id_from_properties(tmp_path):
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

    points = _load_arcgis_layer(path, "partner_betrieb")

    assert len(points) == 1
    assert points[0]["osm_id"] == 502
    assert points[0]["type"] == "partner_betrieb"
    assert points[0]["lon"] == 11.5 and points[0]["lat"] == 47.3


def test_start_points_retain_access_tags():
    table = build_id_table([
        {"type": "parking", "osm_id": 1, "lon": 11.0, "lat": 47.0,
         "properties": {"name": "P", "access": "private", "motor_vehicle": "no"}},
    ])
    assert table["parking"]["1"]["access"] == "private"
    assert table["parking"]["1"]["motor_vehicle"] == "no"


def test_missing_access_becomes_none_not_absent():
    # spec E1: absent tag -> keep but mark access_unknown. Dropping the key makes "unknown"
    # and "open" indistinguishable downstream.
    table = build_id_table([{"type": "parking", "osm_id": 2, "lon": 11.0, "lat": 47.0,
                            "properties": {"name": "Q"}}])
    assert table["parking"]["2"]["access"] is None


def test_is_usable_drops_private_access():
    assert is_usable({"access": "private"}) is False


def test_is_usable_drops_no_access():
    assert is_usable({"access": "no"}) is False


def test_is_usable_drops_private_motor_vehicle():
    assert is_usable({"motor_vehicle": "private"}) is False


def test_is_usable_drops_gate_barrier():
    assert is_usable({"barrier": "gate"}) is False


def test_is_usable_drops_lift_gate_barrier():
    assert is_usable({"barrier": "lift_gate"}) is False


def test_is_usable_drops_disused_station():
    assert is_usable({"disused": "yes"}) is False


def test_is_usable_drops_abandoned_station():
    assert is_usable({"abandoned": "yes"}) is False


def test_is_usable_keeps_point_with_no_tags():
    assert is_usable({}) is True


def test_is_usable_keeps_permit_access_customers():
    # customers/permit are real-world access values that don't mean "unusable" - spec E1's
    # access_unknown/access_values plumbing surfaces them to the UI instead of dropping them.
    assert is_usable({"access": "customers"}) is True


def test_dedupe_drops_same_type_and_osm_id_seen_twice():
    # The AT/Bayern region extracts overlap at the border, so a single real-world node can be
    # exported once per region and land in stations.geojson/parking.geojson twice at
    # byte-identical coordinates - docs/backlog/duplicate-start-points-across-region-extracts.md.
    points = [
        {"lon": 13.0, "lat": 47.5, "osm_id": 42, "type": "station"},
        {"lon": 13.0, "lat": 47.5, "osm_id": 42, "type": "station"},
    ]
    deduped = dedupe_by_osm_id(points)
    assert len(deduped) == 1
    assert deduped[0]["osm_id"] == 42


def test_dedupe_keeps_same_osm_id_across_different_types():
    # osm_id is only unique WITHIN a layer (station/parking/partner_betrieb draw from different
    # id spaces), so the same numeric id under two types must not collide.
    points = [
        {"lon": 13.0, "lat": 47.5, "osm_id": 42, "type": "station"},
        {"lon": 13.0, "lat": 47.5, "osm_id": 42, "type": "parking"},
    ]
    deduped = dedupe_by_osm_id(points)
    assert len(deduped) == 2


def test_dedupe_keeps_the_first_occurrence():
    first = {"lon": 13.0, "lat": 47.5, "osm_id": 42, "type": "station", "properties": {"name": "A"}}
    second = {"lon": 13.0, "lat": 47.5, "osm_id": 42, "type": "station", "properties": {"name": "B"}}
    deduped = dedupe_by_osm_id([first, second])
    assert len(deduped) == 1
    assert deduped[0]["properties"]["name"] == "A"


def test_dedupe_preserves_order_and_leaves_distinct_points_alone():
    points = [
        {"lon": 10.0, "lat": 47.0, "osm_id": 1, "type": "parking"},
        {"lon": 11.0, "lat": 47.0, "osm_id": 2, "type": "station"},
    ]
    deduped = dedupe_by_osm_id(points)
    assert [p["osm_id"] for p in deduped] == [1, 2]


def test_preserves_input_order_of_survivors():
    points = [
        {"lon": 10.01, "lat": 47.0, "osm_id": 1, "type": "parking"},
        {"lon": 20.0, "lat": 47.0, "osm_id": 2, "type": "station"},
        {"lon": 10.99, "lat": 47.0, "osm_id": 3, "type": "parking"},
    ]
    kept = filter_to_hut_range(points, HUT_COORDS, max_edge_km=5.0)
    assert [p["osm_id"] for p in kept] == [1, 3]
