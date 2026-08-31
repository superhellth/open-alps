import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import binfmt  # noqa: E402
from lib.hubs import HUB_TYPE_JSON_NAMES, nearest_hub_to_point  # noqa: E402


def _hub(id_, type_, lon, lat, name=""):
    return {"id": id_, "type": type_, "lon": lon, "lat": lat, "name": name}


def test_nearest_hub_to_point_snaps_to_hut_within_range():
    hubs = [_hub(0, binfmt.TYPE_HUT, 11.0, 47.0, name="Test Hut")]
    chosen, nearest, dist = nearest_hub_to_point(hubs, (11.0005, 47.0), max_snap_m=100.0)
    assert chosen == hubs[0]
    assert nearest == hubs[0]
    assert dist < 100.0


def test_nearest_hub_to_point_snaps_to_station_within_range():
    hubs = [_hub(5, binfmt.TYPE_STATION, 11.0, 47.0)]
    chosen, _, _ = nearest_hub_to_point(hubs, (11.0003, 47.0), max_snap_m=100.0)
    assert chosen["type"] == binfmt.TYPE_STATION
    assert chosen["id"] == 5


def test_nearest_hub_to_point_prefers_hut_over_equidistant_access_point():
    # A hut and a parking spot both within max_snap_m, hut slightly farther but still in range -
    # hut wins (spec §2: "a leg ending at a hut beside a car park resolves to the hut").
    point = (11.0, 47.0)
    hut = _hub(0, binfmt.TYPE_HUT, 11.0005, 47.0)
    parking = _hub(0, binfmt.TYPE_PARKING, 11.0002, 47.0)
    chosen, _, _ = nearest_hub_to_point([parking, hut], point, max_snap_m=100.0)
    assert chosen["type"] == binfmt.TYPE_HUT


def test_nearest_hub_to_point_beyond_max_snap_m_returns_none_but_reports_nearest():
    far_hub = _hub(0, binfmt.TYPE_HUT, 12.0, 48.0)
    point = (11.0, 47.0)
    chosen, nearest, dist = nearest_hub_to_point([far_hub], point, max_snap_m=100.0)
    assert chosen is None
    assert nearest == far_hub
    assert dist > 100.0


def test_nearest_hub_to_point_empty_hubs_returns_none():
    chosen, nearest, dist = nearest_hub_to_point([], (11.0, 47.0), max_snap_m=100.0)
    assert chosen is None and nearest is None and dist == float("inf")


def test_hub_type_json_names_covers_all_four_types():
    assert HUB_TYPE_JSON_NAMES == {
        binfmt.TYPE_HUT: "hut", binfmt.TYPE_STATION: "station",
        binfmt.TYPE_PARKING: "parking", binfmt.TYPE_PARTNER: "partner_betrieb",
    }
