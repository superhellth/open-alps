import inspect
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from postprocessing.build_approach_table import (  # noqa: E402
    build_tables, bucket_index, gather_candidates, parse_duration_buckets,
    parse_variant_names, select_approaches,
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

    rows = select_approaches(
        records, id_table={"partner_betrieb": {"1": {"access": None}}},
        duration_buckets=[4, 6], variant_ids={binfmt.VARIANT_FAST_ANY},
    )

    assert any(r["start_id"] == 1 for r in rows)


def test_absent_access_is_kept_and_marked_unknown():
    records = _records([_record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0)])
    rows = select_approaches(
        records, id_table={"parking": {"1": {"access": None}}},
        duration_buckets=[4, 6], variant_ids={binfmt.VARIANT_FAST_ANY},
    )
    assert rows[0]["access_unknown"] is True


def test_restricted_access_start_points_are_surfaced_not_dropped():
    # private/gated/disused points are hard-dropped upstream, in filter_start_points.py's
    # is_usable() (docs/backlog/access-node-coverage.md) - nothing reaching start_edges/
    # records.npy can carry access="private" any more, but if id_table somehow did carry it,
    # this stage must not silently drop it a second time (that filtering logic lives in exactly
    # one place now).
    records = _records([_record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0)])
    rows = select_approaches(
        records, id_table={"parking": {"1": {"access": "private"}}},
        duration_buckets=[4, 6], variant_ids={binfmt.VARIANT_FAST_ANY},
    )
    assert any(r["start_id"] == 1 for r in rows)
    assert rows[0]["access"] == "private"


def test_edge_id_is_the_true_start_edges_row_index():
    records = _records([
        _record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0),      # row 0, bucket 0
        _record(2, binfmt.TYPE_PARKING, 7, 15000.0, 800.0, 400.0),   # row 1, bucket 1 - distinct cell
        _record(10, binfmt.TYPE_STATION, 7, 5000.0, 200.0, 100.0),   # row 2
    ])
    rows = select_approaches(
        records, id_table={}, duration_buckets=[4, 6], variant_ids={binfmt.VARIANT_FAST_ANY},
    )
    by_start_id = {r["start_id"]: r["edge_id"] for r in rows}
    assert by_start_id[1] == 0
    assert by_start_id[2] == 1
    assert by_start_id[10] == 2


def test_edge_id_round_trips_through_build_tables():
    records = _records([
        _record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0),    # row 0
        _record(10, binfmt.TYPE_STATION, 7, 5000.0, 200.0, 100.0),  # row 1
    ])
    approaches, index = build_tables(
        records, id_table={}, duration_buckets=[4, 6], variant_ids={binfmt.VARIANT_FAST_ANY},
    )
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
    approaches, index = build_tables(
        records, id_table, duration_buckets=[4, 6], variant_ids={binfmt.VARIANT_FAST_ANY},
    )
    for start_id in {r["start_id"] for r in approaches}:
        assert len(index["start_to_huts"][start_id]) >= 1


def test_reverse_index_is_bounded_by_the_start_edge_table():
    records = _records([
        _record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0),
        _record(10, binfmt.TYPE_STATION, 7, 5000.0, 200.0, 100.0),
    ])
    id_table = {}
    approaches, index = build_tables(
        records, id_table, duration_buckets=[4, 6], variant_ids={binfmt.VARIANT_FAST_ANY},
    )
    assert sum(len(v) for v in index["start_to_huts"].values()) <= len(records)


def test_gather_candidates_returns_every_fast_any_candidate_per_hut():
    records = _records([
        _record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0),
        _record(2, binfmt.TYPE_STATION, 7, 2000.0, 60.0, 25.0),
        _record(3, binfmt.TYPE_PARKING, 9, 500.0, 10.0, 5.0),
    ])
    by_hut = gather_candidates(records, id_table={}, variant_ids={binfmt.VARIANT_FAST_ANY})
    assert set(by_hut.keys()) == {7, 9}
    assert len(by_hut[7]) == 2
    assert {c["start_id"] for c in by_hut[7]} == {1, 2}


def test_gather_candidates_excludes_variants_not_in_configured_set():
    records = _records([
        _record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0, variant=binfmt.VARIANT_FAST_T2),
    ])
    by_hut = gather_candidates(records, id_table={}, variant_ids={binfmt.VARIANT_FAST_ANY})
    assert by_hut == {}


def test_gather_candidates_includes_any_configured_variant():
    # variant_ids is genuinely arbitrary - this hut's only candidate is FAST_T2, which is
    # excluded by default config but must be included when the caller configures it.
    records = _records([
        _record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0, variant=binfmt.VARIANT_FAST_T2),
    ])
    by_hut = gather_candidates(records, id_table={}, variant_ids={binfmt.VARIANT_FAST_T2})
    assert len(by_hut[7]) == 1
    assert by_hut[7][0]["variant"] == binfmt.VARIANT_FAST_T2


def test_gather_candidates_tags_each_candidate_with_its_variant():
    records = _records([_record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0)])
    by_hut = gather_candidates(records, id_table={}, variant_ids={binfmt.VARIANT_FAST_ANY})
    assert by_hut[7][0]["variant"] == binfmt.VARIANT_FAST_ANY


def test_bucket_index_assigns_left_closed_boundaries():
    boundaries = [4, 6]
    assert bucket_index(3.9, boundaries) == 0
    assert bucket_index(4.0, boundaries) == 0
    assert bucket_index(4.1, boundaries) == 1
    assert bucket_index(6.0, boundaries) == 1
    assert bucket_index(6.1, boundaries) == 2


def test_two_candidates_in_same_cell_keeps_only_the_faster():
    # both parking, both FAST_ANY, both duration_h well under 4h -> same cell.
    records = _records([
        _record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0),   # faster
        _record(2, binfmt.TYPE_PARKING, 7, 3000.0, 200.0, 100.0),  # slower
    ])
    rows = select_approaches(
        records, id_table={}, duration_buckets=[4, 6], variant_ids={binfmt.VARIANT_FAST_ANY},
    )
    assert len(rows) == 1
    assert rows[0]["start_id"] == 1


def test_hut_with_only_one_source_type_gets_no_phantom_rows_for_absent_types():
    records = _records([_record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0)])
    rows = select_approaches(
        records, id_table={}, duration_buckets=[4, 6], variant_ids={binfmt.VARIANT_FAST_ANY},
    )
    types = {r["source_type"] for r in rows}
    assert types == {binfmt.TYPE_PARKING}


def test_bucket_with_zero_candidates_produces_no_row_and_no_exception():
    # a single very-fast candidate only fills the first duration bucket - the other two
    # buckets for this (source_type, variant) simply produce no row.
    records = _records([_record(1, binfmt.TYPE_PARKING, 7, 500.0, 10.0, 5.0)])
    rows = select_approaches(
        records, id_table={}, duration_buckets=[4, 6], variant_ids={binfmt.VARIANT_FAST_ANY},
    )
    assert len(rows) == 1


def test_same_type_and_bucket_different_variant_keeps_both_rows():
    # a synthetic second variant id, not a real future variant - proves the matrix is keyed
    # on variant and doesn't silently collapse it.
    synthetic_variant = binfmt.VARIANT_FAST_T2
    records = _records([
        _record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0, variant=binfmt.VARIANT_FAST_ANY),
        _record(2, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0, variant=synthetic_variant),
    ])
    rows = select_approaches(
        records, id_table={}, duration_buckets=[4, 6],
        variant_ids={binfmt.VARIANT_FAST_ANY, synthetic_variant},
    )
    assert len(rows) == 2
    assert {r["variant"] for r in rows} == {binfmt.VARIANT_FAST_ANY, synthetic_variant}


def test_hut_needing_two_missing_types_no_longer_loses_one_to_overwrite():
    # regression test for the bug this design fixes (docs/backlog/
    # approach-reserved-type-slot-overwrite.md): 4 fast parking candidates plus one slower
    # station plus one slower partner_betrieb, all in the same duration bucket. The old
    # top-k+reservation code would clobber one of the two reserved slots; the matrix keeps
    # one row per (type, bucket) cell, so both survive.
    records = _records([
        _record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0),
        _record(2, binfmt.TYPE_PARKING, 7, 1100.0, 60.0, 25.0),
        _record(3, binfmt.TYPE_PARKING, 7, 1200.0, 70.0, 30.0),
        _record(4, binfmt.TYPE_PARKING, 7, 1300.0, 80.0, 35.0),
        _record(10, binfmt.TYPE_STATION, 7, 1400.0, 90.0, 40.0),
        _record(20, binfmt.TYPE_PARTNER, 7, 1500.0, 100.0, 45.0),
    ])
    rows = select_approaches(
        records, id_table={}, duration_buckets=[4, 6], variant_ids={binfmt.VARIANT_FAST_ANY},
    )
    types = {r["source_type"] for r in rows}
    assert types == {binfmt.TYPE_PARKING, binfmt.TYPE_STATION, binfmt.TYPE_PARTNER}


def test_parse_duration_buckets_splits_and_orders_floats():
    assert parse_duration_buckets("4,6") == [4.0, 6.0]
    assert parse_duration_buckets("4.5") == [4.5]


def test_parse_variant_names_resolves_to_ids():
    assert parse_variant_names("FAST_ANY") == {binfmt.VARIANT_FAST_ANY}
    assert parse_variant_names("FAST_ANY,FAST_T2") == {
        binfmt.VARIANT_FAST_ANY, binfmt.VARIANT_FAST_T2,
    }


def test_parse_variant_names_rejects_unknown_name():
    import pytest
    with pytest.raises(ValueError, match="NOT_A_REAL_VARIANT"):
        parse_variant_names("NOT_A_REAL_VARIANT")


def test_every_selected_row_carries_a_variant_ready_for_the_variant_column():
    records = _records([_record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0)])
    rows = select_approaches(
        records, id_table={}, duration_buckets=[4, 6], variant_ids={binfmt.VARIANT_FAST_ANY},
    )
    assert all(isinstance(r["variant"], int) for r in rows)
    assert rows[0]["variant"] == binfmt.VARIANT_FAST_ANY
