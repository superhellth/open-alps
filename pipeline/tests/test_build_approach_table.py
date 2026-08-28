import inspect
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from postprocessing.build_approach_table import build_tables, select_approaches  # noqa: E402


def _record(from_id, from_type, to_id, distance_m, ascent_m, descent_m,
            variant=binfmt.VARIANT_FAST_ANY):
    return (
        from_id, to_id, from_type, binfmt.TYPE_HUT, variant,
        distance_m, 0.0, ascent_m, descent_m, 0.0, 0.0, 0.0, 0.0,
        -1, False, 0, 0, 0, 0,
    )


def _records(rows):
    return np.array(rows, dtype=binfmt.RECORD_DTYPE)


def test_partner_betrieb_source_type_is_not_dropped():
    records = _records([_record(1, binfmt.TYPE_PARTNER, 7, 1000.0, 50.0, 20.0)])

    rows = select_approaches(records, id_table={"partner_betrieb": {"1": {"access": None}}}, k=3)

    assert any(r["start_id"] == 1 for r in rows)


def test_restricted_access_start_points_are_dropped():
    records = _records([_record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0)])
    rows = select_approaches(records, id_table={"parking": {"1": {"access": "private"}}}, k=3)
    assert all(r["start_id"] != 1 for r in rows)


def test_absent_access_is_kept_and_marked_unknown():
    records = _records([_record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0)])
    rows = select_approaches(records, id_table={"parking": {"1": {"access": None}}}, k=3)
    assert rows[0]["access_unknown"] is True


def test_gated_forest_road_is_dropped():
    records = _records([_record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0)])
    rows = select_approaches(records, id_table={"parking": {"1": {"barrier": "gate"}}}, k=3)
    assert all(r["start_id"] != 1 for r in rows)


def test_k_best_never_fills_every_slot_from_one_source_type():
    # 4 parking candidates all faster than the one station candidate for hut 7 - a naive
    # top-k-by-time would starve the station out of the result entirely (spec E1).
    records_with_both_sources = _records([
        _record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0),
        _record(2, binfmt.TYPE_PARKING, 7, 1100.0, 60.0, 25.0),
        _record(3, binfmt.TYPE_PARKING, 7, 1200.0, 70.0, 30.0),
        _record(4, binfmt.TYPE_PARKING, 7, 1300.0, 80.0, 35.0),
        _record(10, binfmt.TYPE_STATION, 7, 5000.0, 200.0, 100.0),
    ])
    rows = select_approaches(records_with_both_sources, id_table={}, k=3)
    types = {r["source_type"] for r in rows if r["hut_id"] == 7}
    assert binfmt.TYPE_PARKING in types and binfmt.TYPE_STATION in types


def test_no_approach_time_cap_is_applied():
    # spec E1: maxApproachTime is deleted. An approach is a full leg, bounded by the same
    # pipeline range cap as any hut-hut edge and filtered client-side by the same maxLegTime.
    src = inspect.getsource(select_approaches)
    assert "approach_time" not in src and "maxApproachTime" not in src


def test_reverse_index_covers_every_retained_start_point():
    records = _records([
        _record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0),
        _record(10, binfmt.TYPE_STATION, 7, 5000.0, 200.0, 100.0),
    ])
    id_table = {}
    approaches, index = build_tables(records, id_table, k=3)
    for start_id in {r["start_id"] for r in approaches}:
        assert len(index["start_to_huts"][start_id]) >= 1


def test_reverse_index_is_bounded_by_the_start_edge_table():
    records = _records([
        _record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0),
        _record(10, binfmt.TYPE_STATION, 7, 5000.0, 200.0, 100.0),
    ])
    id_table = {}
    approaches, index = build_tables(records, id_table, k=3)
    assert sum(len(v) for v in index["start_to_huts"].values()) <= len(records)
