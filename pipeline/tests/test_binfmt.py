import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import binfmt  # noqa: E402


def test_save_load_array_round_trips(tmp_path):
    arr = np.array([(1.0, 2.0, 0), (3.0, 4.0, 1)], dtype=binfmt.NODE_DTYPE)
    path = tmp_path / "nodes.npy"
    binfmt.save_array(path, arr)
    loaded = binfmt.load_array(path, mmap=False)
    assert np.array_equal(loaded, arr)


def test_load_array_mmap_returns_memmap(tmp_path):
    arr = np.array([(1.0, 2.0, 0)], dtype=binfmt.NODE_DTYPE)
    path = tmp_path / "nodes.npy"
    binfmt.save_array(path, arr)
    loaded = binfmt.load_array(path, mmap=True)
    assert isinstance(loaded, np.memmap)


def test_save_load_manifest_round_trips(tmp_path):
    path = tmp_path / "manifest.json"
    manifest = {"bbox": {"minLng": 1.0}, "tile_size_km": 60}
    binfmt.save_manifest(path, manifest)
    assert binfmt.load_manifest(path) == manifest


def test_build_csr_index_groups_contiguous_ranges():
    group_ids = np.array([2, 0, 1, 0, 2, 1])
    order, index = binfmt.build_csr_index(group_ids, n_groups=3)
    # group 0's two entries (original positions 1, 3) are contiguous in `order`
    g0_start, g0_count = index["start_offset"][0], index["count"][0]
    assert g0_count == 2
    assert set(order[g0_start:g0_start + g0_count].tolist()) == {1, 3}
    # every original index appears exactly once across all groups
    assert sorted(order.tolist()) == list(range(6))


def test_build_csr_index_empty_group_has_zero_count():
    group_ids = np.array([0, 0])
    order, index = binfmt.build_csr_index(group_ids, n_groups=3)
    assert index["count"][1] == 0
    assert index["count"][2] == 0


def test_edge_dtype_has_time_and_grading_columns_and_no_weight():
    names = binfmt.EDGE_DTYPE.names
    for field in ("time_s", "ascent_m", "descent_m", "ungraded_m", "inferred_m", "constrained_ok"):
        assert field in names, field
    # spec A3: dropping the field (not repurposing it) makes a stale cache fail loudly with a
    # KeyError instead of feeding penalised metres to a router reading seconds
    assert "weight" not in names


def test_variant_constants_replace_variant_shortest():
    assert binfmt.VARIANT_FAST_ANY == 0
    assert binfmt.VARIANT_FAST_T2 == 1
    assert binfmt.VARIANT_FAST_T3 == 2
    assert not hasattr(binfmt, "VARIANT_SHORTEST")


def test_variant_fast_t3_ungraded_is_the_fourth_row():
    # findings doc 2026-08-22-tour-suggestion-findings.md §3/§4: 31.7%/36.9% of huts lose their
    # last T2/T3 connection under the strict ungraded_m==0 rule, both far over the 5% threshold -
    # the fourth row is required, not optional.
    assert binfmt.VARIANT_FAST_T3_UNGRADED == 3
    assert binfmt.VARIANT_NAMES[binfmt.VARIANT_FAST_T3_UNGRADED] == "FAST_T3_UNGRADED"


def test_record_dtype_carries_the_scalar_filter_columns():
    for field in ("max_ele_m", "ungraded_m", "inferred_m", "snap_m"):
        assert field in binfmt.RECORD_DTYPE.names, field


def test_type_partner_is_distinct_from_existing_hub_types():
    assert binfmt.TYPE_PARTNER == 3
    assert binfmt.TYPE_PARTNER not in (binfmt.TYPE_HUT, binfmt.TYPE_STATION, binfmt.TYPE_PARKING)


def test_record_dtype_has_no_stored_duration():
    # spec D3: reported duration is direction-dependent. A stored scalar guarantees something
    # reads it for a leg walked backwards and is wrong by the full ascent/descent rate gap.
    assert "time_min" not in binfmt.RECORD_DTYPE.names
    assert "time_s" not in binfmt.RECORD_DTYPE.names
