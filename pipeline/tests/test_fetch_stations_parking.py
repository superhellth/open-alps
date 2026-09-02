import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from downloads.fetch_stations_parking import LAYERS  # noqa: E402


def _layer(name):
    return next(layer for layer in LAYERS if layer["name"] == name)


def test_stations_tag_filter_includes_rail_and_narrowed_bus_stops():
    # Rail is a single-stage pipeline (plain OR'd tag match); bus is a three-stage AND pipeline
    # (bus_stop -> public_transport=platform -> name), since osmium tags-filter only ORs the tags
    # named in one call - an AND needs sequential filter passes.
    pipelines = _layer("stations")["tag_filter_pipelines"]
    assert ["n/railway=station,halt"] in pipelines
    assert ["n/highway=bus_stop", "n/public_transport=platform", "n/name"] in pipelines


def test_stations_keep_fields_carry_access_and_lifecycle_tags():
    # network/operator dropped: unused downstream (filter_start_points.py, build_approach_table.py)
    # and unread by the frontend - see TourSearchPage.tsx, which only reads properties.name.
    keep_fields = _layer("stations")["keep_fields"]
    assert set(keep_fields) == {"name", "access", "motor_vehicle", "barrier", "disused", "abandoned"}


def test_parking_layer_is_unchanged():
    parking = _layer("parking")
    assert parking["tag_filter_pipelines"] == [["nwr/amenity=parking"]]
    assert parking["keep_fields"] == ["name", "capacity", "fee", "access", "motor_vehicle", "barrier"]
