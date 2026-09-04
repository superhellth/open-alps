import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from postprocessing.select_approach_pairs import select_pairs  # noqa: E402


def _row(hut_id, start_id, start_type, variant, distance_m, time_s):
    return (hut_id, start_id, start_type, variant, distance_m, time_s)


def _arr(rows):
    return np.array(rows, dtype=binfmt.ACCESS_DISTANCE_DTYPE)


def test_keeps_only_the_k_fastest_fast_any_candidates_per_hut_and_source_type():
    rows = _arr([
        _row(1, 100, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_ANY, 1000.0, 500.0),
        _row(1, 101, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_ANY, 2000.0, 900.0),
        _row(1, 102, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_ANY, 3000.0, 1500.0),
    ])
    selected = select_pairs(rows, k=2)
    assert sorted(selected["start_id"].tolist()) == [100, 101]  # the two fastest by time_s


def test_selection_is_per_hut_and_source_type_group():
    # hut 1's parking candidates must not compete against hut 2's for the k slots.
    rows = _arr([
        _row(1, 100, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_ANY, 1000.0, 500.0),
        _row(2, 200, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_ANY, 1000.0, 500.0),
    ])
    selected = select_pairs(rows, k=1)
    assert set(selected["start_id"].tolist()) == {100, 200}


def test_station_and_parking_slots_are_independent():
    rows = _arr([
        _row(1, 100, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_ANY, 1000.0, 500.0),
        _row(1, 200, binfmt.TYPE_STATION, binfmt.VARIANT_FAST_ANY, 5000.0, 4000.0),
    ])
    selected = select_pairs(rows, k=1)
    assert set(selected["start_id"].tolist()) == {100, 200}


def test_reverse_index_closure_pulls_in_every_variant_of_a_selected_start():
    # start 100 is selected on FAST_ANY; its FAST_T2 row for the SAME hut must ship too, even
    # though FAST_T2 rows are never themselves ranking candidates (spec B5).
    rows = _arr([
        _row(1, 100, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_ANY, 1000.0, 500.0),
        _row(1, 100, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_T2, 1200.0, 600.0),
    ])
    selected = select_pairs(rows, k=1)
    assert sorted(selected["variant"].tolist()) == [binfmt.VARIANT_FAST_ANY, binfmt.VARIANT_FAST_T2]


def test_reverse_index_closure_pulls_in_a_selected_start_reaching_a_different_hut():
    # start 100 is selected as hut 1's approach; hut 2 also has a (non-selected-rank) row to the
    # SAME start 100 - the loop-closure index must ship that pair too (spec E2/B2: the client's
    # car mode needs exit start-point == entry start-point across the whole trip, not just the
    # entry hut's own top-k).
    rows = _arr([
        _row(1, 100, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_ANY, 1000.0, 500.0),
        _row(2, 100, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_ANY, 9000.0, 8000.0),
        _row(2, 999, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_ANY, 1000.0, 500.0),
    ])
    selected = select_pairs(rows, k=1)
    # hut 2's own top-1 is start 999, but start 100's closure must still bring in (hut 2, 100).
    pairs = {(int(r["hut_id"]), int(r["start_id"])) for r in selected}
    assert (2, 100) in pairs
    assert (2, 999) in pairs


def test_empty_input_returns_empty_output():
    selected = select_pairs(_arr([]), k=20)
    assert len(selected) == 0
