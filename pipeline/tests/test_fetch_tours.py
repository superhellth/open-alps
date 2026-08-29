import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from downloads.fetch_tours import (  # noqa: E402
    build_tour_records, parse_huettenliste, resolve_hut_indices,
)

HUT_ID_TO_INDEX = {"{GUID-A}": 0, "{GUID-B}": 1, "{GUID-C}": 2}


def test_parse_huettenliste_splits_and_strips():
    assert parse_huettenliste("{GUID-A}, {GUID-B} ,{GUID-C}") == ["{GUID-A}", "{GUID-B}", "{GUID-C}"]


def test_parse_huettenliste_empty_is_empty_list():
    assert parse_huettenliste(None) == []
    assert parse_huettenliste("") == []


def test_resolve_hut_indices_resolves_every_known_guid():
    gaps = []
    out = resolve_hut_indices(["{GUID-A}", "{GUID-C}"], HUT_ID_TO_INDEX, "TST", gaps)
    assert out == [0, 2]
    assert gaps == []


def test_resolve_hut_indices_records_unresolvable_guid_as_sentinel_not_dropped():
    # spec §1: dropping a hut from the middle of the chain would silently fuse two real stages
    # into one leg - it must come back as a sentinel (-1) plus a gap record, never be omitted.
    gaps = []
    out = resolve_hut_indices(["{GUID-A}", "{GUID-MISSING}", "{GUID-C}"], HUT_ID_TO_INDEX, "TST", gaps)
    assert out == [0, -1, 2]
    assert len(gaps) == 1
    assert gaps[0]["globalId"] == "{GUID-MISSING}"
    assert gaps[0]["tourShortCode"] == "TST"


def _feature(short_code, name, huettenliste, is_loop=0, global_id="{TOUR-1}", geometry_paths=None):
    return {
        "attributes": {
            "GlobalID": global_id, "Bezeichnung": name, "Kurzbezeichnung": short_code,
            "Rundtour": is_loop, "Homepage": "https://example.invalid",
            "Download": None, "Huettenliste": huettenliste,
        },
        "geometry": {"paths": geometry_paths if geometry_paths is not None else [[[10.0, 47.0], [10.1, 47.1]]]},
    }


def test_dummy_record_is_filtered_by_short_code_not_by_missing_name():
    # #DUMMY has a non-empty, resolvable Huettenliste (spec §0) - the filter must key off
    # Kurzbezeichnung=="#DUMMY", not off a null-name/empty-hut-list heuristic.
    features = [
        _feature("#DUMMY", None, "{GUID-A},{GUID-B}"),
        _feature("REAL", "Real Tour", "{GUID-A},{GUID-C}"),
    ]
    tours, traces, gaps = build_tour_records(features, HUT_ID_TO_INDEX)
    assert len(tours) == 1
    assert tours[0]["shortCode"] == "REAL"


def test_karwendel_hoehenweg_style_null_name_is_kept():
    # A real tour can also lack a distinct Bezeichnung/Kurzbezeichnung pair (spec §0) - must NOT
    # be filtered just because Kurzbezeichnung is missing/None, only #DUMMY is special-cased.
    features = [_feature(None, "Karwendel Höhenweg", "{GUID-A},{GUID-B}")]
    tours, _, _ = build_tour_records(features, HUT_ID_TO_INDEX)
    assert len(tours) == 1
    assert tours[0]["name"] == "Karwendel Höhenweg"


def test_empty_hut_list_tour_is_kept_with_empty_hut_indices():
    # Wiener Höhenweg / MontafonerSilvrettarunde (spec §0): geometry exists, hut list doesn't -
    # stays in tours.json, just produces zero legs downstream (out of scope here).
    features = [_feature("WHW", "Wiener Höhenweg", None)]
    tours, traces, _ = build_tour_records(features, HUT_ID_TO_INDEX)
    assert tours[0]["hutIndices"] == []


def test_tour_id_is_the_positional_index_and_traces_are_aligned():
    features = [
        _feature("A", "Tour A", "{GUID-A}", global_id="{G-A}"),
        _feature("B", "Tour B", "{GUID-B}", global_id="{G-B}"),
    ]
    tours, traces, _ = build_tour_records(features, HUT_ID_TO_INDEX)
    assert [t["tourId"] for t in tours] == [0, 1]
    assert [t["tourId"] for t in traces] == [0, 1]
    assert tours[1]["globalId"] == "{G-B}"


def test_is_loop_and_hut_indices_populated():
    features = [_feature("A", "Tour A", "{GUID-A},{GUID-B},{GUID-C}", is_loop=1)]
    tours, _, _ = build_tour_records(features, HUT_ID_TO_INDEX)
    assert tours[0]["isLoop"] is True
    assert tours[0]["hutIndices"] == [0, 1, 2]
