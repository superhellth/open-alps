import sys
from pathlib import Path

from shapely.geometry import box
from shapely.prepared import prep

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from downloads.fetch_stations_parking import (  # noqa: E402
    LAYERS, _area_to_point, dedupe_stop_positions, filter_to_boundary,
)


def _layer(name):
    return next(layer for layer in LAYERS if layer["name"] == name)


def test_stations_tag_filter_includes_rail_and_narrowed_bus_stops():
    # Rail is a two-stage AND pipeline (railway=station,halt -> name); bus is a three-stage AND
    # pipeline (bus_stop -> public_transport=platform,stop_position -> name), since osmium tags-filter only ORs
    # the tags named in one call - an AND needs sequential filter passes. Rail does NOT require
    # public_transport=platform - that tag is essentially never present on railway=station/halt
    # nodes (measured), so requiring it would drop real stations rather than filter noise.
    pipelines = _layer("stations")["tag_filter_pipelines"]
    assert ["n/railway=station,halt", "n/name"] in pipelines
    assert ["n/highway=bus_stop", "n/public_transport=platform,stop_position", "n/name"] in pipelines


def test_stations_keep_fields_carry_access_and_lifecycle_tags():
    # network/operator dropped: unused downstream (filter_start_points.py, build_approach_table.py)
    # and unread by the frontend - see TourSearchPage.tsx, which only reads properties.name.
    keep_fields = _layer("stations")["keep_fields"]
    assert set(keep_fields) == {"name", "access", "motor_vehicle", "barrier", "disused", "abandoned"}


def test_parking_layer_is_unchanged():
    parking = _layer("parking")
    assert parking["tag_filter_pipelines"] == [["nwr/amenity=parking"]]
    assert parking["keep_fields"] == ["name", "capacity", "fee", "access", "motor_vehicle", "barrier"]


def test_parking_layer_requests_polygon_geometry_too():
    # Most real parking lots are mapped as a closed way, not a node - point-only silently drops
    # them (verified against a live OSM extract: real amenity=parking ways near two official-tour
    # trailheads never reached parking.geojson). _area_to_point below converts them back.
    assert _layer("parking")["geometry_types"] == "point,polygon"


def test_area_to_point_leaves_real_nodes_untouched():
    feat = {"id": "n123", "geometry": {"type": "Point", "coordinates": [12.0, 47.0]}}
    assert _area_to_point(feat) is feat
    assert feat["geometry"] == {"type": "Point", "coordinates": [12.0, 47.0]}


def test_area_to_point_converts_way_polygon_to_centroid_with_decoded_id():
    # osmium's area-id convention: a way-sourced area's id is way_id * 2 (even).
    square = {
        "id": "a53069508",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0], [0.0, 0.0]]],
        },
    }
    result = _area_to_point(square)
    assert result["id"] == "w26534754"
    assert result["geometry"]["type"] == "Point"
    assert result["geometry"]["coordinates"] == [1.0, 1.0]


def test_area_to_point_converts_relation_multipolygon_with_decoded_id():
    # Odd area id -> relation-sourced multipolygon: relation_id * 2 + 1.
    feat = {
        "id": "a41",
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": [[[[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0], [0.0, 0.0]]]],
        },
    }
    result = _area_to_point(feat)
    assert result["id"] == "r20"
    assert result["geometry"] == {"type": "Point", "coordinates": [1.0, 1.0]}


def _stop(fid, name, pt, lon, lat):
    props = {"name": name}
    if pt:
        props["public_transport"] = pt
    return {"id": fid, "properties": props, "geometry": {"type": "Point", "coordinates": [lon, lat]}}


def test_dedupe_drops_stop_position_next_to_same_name_platform():
    platform = _stop("n2", "Plangeross", "platform", 10.8683, 46.9866)
    stop_pos = _stop("n1", "Plangeross", "stop_position", 10.86835, 46.98661)  # ~10 m away
    assert dedupe_stop_positions([stop_pos, platform]) == [platform]


def test_dedupe_keeps_lone_stop_position_and_different_names_and_far_ones():
    lone = _stop("n1", "Plangeross", "stop_position", 10.8683, 46.9866)
    other_name = _stop("n2", "Weißwald", "stop_position", 10.86831, 46.98661)
    far = _stop("n3", "Plangeross", "stop_position", 10.8690, 46.9866)  # ~50 m away
    assert len(dedupe_stop_positions([lone, other_name, far])) == 3


def test_dedupe_collapses_stop_positions_lowest_id_wins():
    a = _stop("n5", "X", "stop_position", 10.0, 47.0)
    b = _stop("n3", "X", "stop_position", 10.00002, 47.0)
    assert dedupe_stop_positions([a, b]) == [b]


def test_dedupe_never_drops_rail_stations():
    rail = _stop("n9", "Landeck", None, 10.5, 47.1)
    stop_pos = _stop("n1", "Landeck", "stop_position", 10.50001, 47.1)
    assert dedupe_stop_positions([stop_pos, rail]) == [rail]


def test_filter_to_boundary_drops_points_outside_the_region():
    inside = {"id": "n1", "geometry": {"type": "Point", "coordinates": [0.5, 0.5]}, "properties": {}}
    outside = {"id": "n2", "geometry": {"type": "Point", "coordinates": [2.0, 0.5]}, "properties": {}}

    kept = filter_to_boundary([inside, outside], prep(box(0, 0, 1, 1)))

    assert [f["id"] for f in kept] == ["n1"]
