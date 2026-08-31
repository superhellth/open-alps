import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from downloads.fetch_stations_parking import LAYERS  # noqa: E402


def _layer(name):
    return next(layer for layer in LAYERS if layer["name"] == name)


def test_stations_tag_filter_includes_rail_and_bus_stops():
    # osmium tags-filter OR's multiple filter-expression arguments together - two separate
    # expressions here, not one merged railway=...,highway=... string.
    tag_filter = _layer("stations")["tag_filter"]
    assert "n/railway=station,halt" in tag_filter
    assert "n/highway=bus_stop" in tag_filter


def test_stations_keep_fields_carry_access_and_lifecycle_tags():
    # network/operator dropped: unused downstream (filter_start_points.py, build_approach_table.py)
    # and unread by the frontend - see TourSearchPage.tsx, which only reads properties.name.
    keep_fields = _layer("stations")["keep_fields"]
    assert set(keep_fields) == {"name", "access", "motor_vehicle", "barrier", "disused", "abandoned"}


def test_parking_layer_is_unchanged():
    parking = _layer("parking")
    assert parking["tag_filter"] == ["nwr/amenity=parking"]
    assert parking["keep_fields"] == ["name", "capacity", "fee", "access", "motor_vehicle", "barrier"]
