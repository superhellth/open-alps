import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from quality.check_tour_matching import (  # noqa: E402
    check_endpoint_types, check_gap_reasons, check_leg_scalars, check_tours_json_agreement,
)


def _tour(tour_id, name, num_days, legs):
    return {"tourId": tour_id, "name": name, "numDays": num_days, "legs": legs}


def _leg(leg_index, from_hub, to_hub, distance_m=1000.0, ascent_m=100.0, descent_m=50.0,
         duration_s=900.0):
    return {
        "legIndex": leg_index, "edgeId": leg_index, "maxEleM": 2000.0, "distanceM": distance_m, "ascentM": ascent_m,
        "descentM": descent_m, "durationS": duration_s, "from": from_hub, "to": to_hub,
    }


def test_endpoint_types_flags_a_non_hut_interior_from():
    tours = [_tour(0, "T", 3, [
        _leg(0, {"type": "station", "id": 1}, {"type": "hut", "id": 2}),
        _leg(1, {"type": "hut", "id": 2}, {"type": "hut", "id": 3}),
    ])]
    check = check_endpoint_types(tours, max_flagged=500)
    assert check["summary"]["flagged"] == 0  # legIndex 0's "from" may be any type


def test_endpoint_types_flags_a_non_hut_interior_endpoint():
    tours = [_tour(0, "T", 3, [
        _leg(0, {"type": "hut", "id": 1}, {"type": "station", "id": 2}),  # interior "to" at leg 0 of 3
    ])]
    check = check_endpoint_types(tours, max_flagged=500)
    assert check["summary"]["flagged"] == 1
    assert check["flagged"][0]["endpoint"] == "to"


def test_endpoint_types_allows_any_type_at_tour_start_and_end():
    tours = [_tour(0, "T", 1, [
        _leg(0, {"type": "parking", "id": 1}, {"type": "station", "id": 2}),
    ])]
    check = check_endpoint_types(tours, max_flagged=500)
    assert check["summary"]["flagged"] == 0


def test_leg_scalars_flags_negative_and_non_finite_values():
    tours = [_tour(0, "T", 1, [
        _leg(0, {"type": "hut", "id": 1}, {"type": "hut", "id": 2}, distance_m=-1.0,
             ascent_m=float("nan")),
    ])]
    check = check_leg_scalars(tours, max_flagged=500)
    fields = {r["field"] for r in check["flagged"]}
    assert {"distanceM", "ascentM"} <= fields


def test_leg_scalars_clean_case_flags_nothing():
    tours = [_tour(0, "T", 1, [_leg(0, {"type": "hut", "id": 1}, {"type": "hut", "id": 2})])]
    check = check_leg_scalars(tours, max_flagged=500)
    assert check["summary"]["flagged"] == 0


def test_gap_reasons_flags_every_gap():
    gaps = [
        {"tourId": 0, "tourName": "T", "legIndex": 0, "reason": "leg_endpoint_unsnapped",
         "detail": {"endpoint": "to"}},
        {"tourId": 0, "tourName": "T", "legIndex": 1, "reason": "leg_endpoint_unsnapped"},
    ]
    check = check_gap_reasons(gaps, max_flagged=500)
    assert check["summary"]["checked"] == 2
    assert check["summary"]["flagged"] == 2
    assert check["flagged"][0]["detail"] == {"endpoint": "to"}
    assert check["flagged"][1]["detail"] is None


def test_leg_scalars_skips_gap_legs():
    tours = [_tour(0, "T", 2, [
        {"legIndex": 0, "edgeId": None, "from": None, "to": None},
        _leg(1, {"type": "hut", "id": 1}, {"type": "hut", "id": 2}),
    ])]
    check = check_leg_scalars(tours, max_flagged=500)
    assert check["summary"]["checked"] == 1
    assert check["summary"]["flagged"] == 0


def test_leg_scalars_flags_non_finite_max_ele():
    leg = _leg(0, None, None)
    leg["maxEleM"] = float("nan")
    assert check_leg_scalars([_tour(0, "T", 1, [leg])], max_flagged=500)["summary"]["flagged"] == 1


def test_tours_json_agreement_flags_edge_id_out_of_range_and_row_count_mismatch():
    tours = [{"tourId": 0, "name": "T", "numDays": 2, "legs": [
        {"legIndex": 0, "edgeId": 0}, {"legIndex": 1, "edgeId": 5}]}]
    check = check_tours_json_agreement(tours, n_records=3, max_flagged=500)
    reasons = {r["reason"] for r in check["flagged"]}
    assert reasons == {"edge_id_out_of_range", "matched_leg_count_mismatch"}


def test_tours_json_agreement_clean_case():
    tours = [{"tourId": 0, "name": "T", "numDays": 2, "legs": [
        {"legIndex": 0, "edgeId": 0}, {"legIndex": 1, "edgeId": None}]}]
    assert check_tours_json_agreement(tours, n_records=1, max_flagged=500)["summary"]["flagged"] == 0


def test_profile_integrity_accepts_tour_leg_records():
    import numpy as np
    from lib import binfmt
    from quality.check_elevation import check_profile_integrity

    records = np.zeros(1, dtype=binfmt.TOUR_LEG_DTYPE)
    records[0]["geom_count"], records[0]["profile_count"] = 3, 5
    profiles = np.zeros(5, dtype=binfmt.PROFILE_DTYPE)
    check = check_profile_integrity(records, profiles, 5, "tour_edges", max_flagged=500)
    assert check["summary"]["checked"] == 1
    assert check["summary"]["flagged"] == 0
