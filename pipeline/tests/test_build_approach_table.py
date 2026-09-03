import inspect
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from postprocessing.build_approach_table import (  # noqa: E402
    build_tables, gather_candidates, select_approaches,
)


def _record(from_id, from_type, to_id, distance_m, ascent_m, descent_m,
            variant=binfmt.VARIANT_FAST_ANY):
    return (
        from_id, to_id, from_type, binfmt.TYPE_HUT, variant,
        distance_m, 0.0, ascent_m, descent_m, 0.0, 0.0, 0.0, 0.0,
        -1, False, 0, 0, 0, 0,
        0, 0, (-1,) * 8, 0, (-1,) * 8, 0,
    )


def _records(rows):
    return np.array(rows, dtype=binfmt.RECORD_DTYPE)


def test_partner_betrieb_source_type_is_not_dropped():
    records = _records([_record(1, binfmt.TYPE_PARTNER, 7, 1000.0, 50.0, 20.0)])

    rows = select_approaches(records, id_table={"partner_betrieb": {"1": {"access": None}}}, k=3)

    assert any(r["start_id"] == 1 for r in rows)


def test_absent_access_is_kept_and_marked_unknown():
    records = _records([_record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0)])
    rows = select_approaches(records, id_table={"parking": {"1": {"access": None}}}, k=3)
    assert rows[0]["access_unknown"] is True


def test_restricted_access_start_points_are_surfaced_not_dropped():
    # private/gated/disused points are hard-dropped upstream, in filter_start_points.py's
    # is_usable() (docs/backlog/access-node-coverage.md) - nothing reaching start_edges/
    # records.npy can carry access="private" any more, but if id_table somehow did carry it,
    # this stage must not silently drop it a second time (that filtering logic lives in exactly
    # one place now).
    records = _records([_record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0)])
    rows = select_approaches(records, id_table={"parking": {"1": {"access": "private"}}}, k=3)
    assert any(r["start_id"] == 1 for r in rows)
    assert rows[0]["access"] == "private"


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


def test_edge_id_is_the_true_start_edges_row_index():
    records = _records([
        _record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0),    # row 0
        _record(2, binfmt.TYPE_PARKING, 7, 1100.0, 60.0, 25.0),    # row 1
        _record(10, binfmt.TYPE_STATION, 7, 5000.0, 200.0, 100.0),  # row 2
    ])
    rows = select_approaches(records, id_table={}, k=3)
    by_start_id = {r["start_id"]: r["edge_id"] for r in rows}
    assert by_start_id[1] == 0
    assert by_start_id[2] == 1
    assert by_start_id[10] == 2


def test_edge_id_round_trips_through_build_tables():
    records = _records([
        _record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0),    # row 0
        _record(10, binfmt.TYPE_STATION, 7, 5000.0, 200.0, 100.0),  # row 1
    ])
    approaches, index = build_tables(records, id_table={}, k=3)
    approach_edge_id = {r["start_id"]: r["edge_id"] for r in approaches}
    assert approach_edge_id[1] == 0
    assert approach_edge_id[10] == 1
    for start_id, expected_edge_id in approach_edge_id.items():
        for row in index["start_to_huts"][start_id]:
            assert row["edge_id"] == expected_edge_id
        matching = [row for row in index["hut_to_starts"][7] if row["start_id"] == start_id]
        assert matching and all(row["edge_id"] == expected_edge_id for row in matching)


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


def test_gather_candidates_returns_every_fast_any_candidate_per_hut():
    records = _records([
        _record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0),
        _record(2, binfmt.TYPE_STATION, 7, 2000.0, 60.0, 25.0),
        _record(3, binfmt.TYPE_PARKING, 9, 500.0, 10.0, 5.0),
    ])
    by_hut = gather_candidates(records, id_table={})
    assert set(by_hut.keys()) == {7, 9}
    assert len(by_hut[7]) == 2
    assert {c["start_id"] for c in by_hut[7]} == {1, 2}


def test_gather_candidates_excludes_non_fast_any_variants():
    records = _records([
        _record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0, variant=binfmt.VARIANT_FAST_T2),
    ])
    by_hut = gather_candidates(records, id_table={})
    assert by_hut == {}


def test_select_approaches_still_selects_k_best_after_refactor():
    # regression guard: select_approaches' own behavior must be byte-for-byte unchanged by
    # routing through gather_candidates.
    records = _records([
        _record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0),
        _record(2, binfmt.TYPE_PARKING, 7, 500.0, 10.0, 5.0),
    ])
    rows = select_approaches(records, id_table={}, k=1)
    assert len(rows) == 1
    assert rows[0]["start_id"] == 2  # the faster of the two
