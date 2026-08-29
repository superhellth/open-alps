import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import binfmt  # noqa: E402
from lib.edge_output import K_TRAVERSAL, write_edge_records  # noqa: E402


def _rec(from_id=0, to_id=1, variant=0, geometry=None, base_edge_ids=None):
    return {
        "from_id": from_id, "to_id": to_id, "from_type": binfmt.TYPE_HUT,
        "to_type": binfmt.TYPE_HUT, "variant": variant,
        "distance_m": 1000.0, "road_m": 0.0, "ascent_m": 50.0, "descent_m": 20.0,
        "max_ele_m": 1500.0, "ungraded_m": 0.0, "inferred_m": 0.0, "snap_m": 5.0,
        "sac_rank": 1, "via_ferrata": False,
        "geometry": geometry if geometry is not None else [(10.0, 47.0), (10.01, 47.0)],
        "base_edge_ids": base_edge_ids if base_edge_ids is not None else [10, 11, 12],
    }


def test_write_edge_output_preserves_each_record_variant(tmp_path):
    write_edge_records([_rec(variant=0), _rec(variant=2)], tmp_path)
    arr = binfmt.load_array(tmp_path / "records.npy", mmap=False)
    assert sorted(arr["variant"].tolist()) == [0, 2]


def test_identical_variant_geometries_share_one_offset(tmp_path):
    geom = [(10.0, 47.0), (10.01, 47.0), (10.02, 47.0)]
    write_edge_records([_rec(variant=0, geometry=geom), _rec(variant=2, geometry=geom)], tmp_path)
    records = binfmt.load_array(tmp_path / "records.npy", mmap=False)
    geometry = binfmt.load_array(tmp_path / "geometry.npy", mmap=False)
    assert records["geom_offset"][0] == records["geom_offset"][1]
    assert len(geometry) == len(geom)


def test_differing_geometries_do_not_share(tmp_path):
    write_edge_records([
        _rec(variant=0, geometry=[(10.0, 47.0), (10.01, 47.0)]),
        _rec(variant=2, geometry=[(11.0, 48.0), (11.01, 48.0)]),
    ], tmp_path)
    records = binfmt.load_array(tmp_path / "records.npy", mmap=False)
    assert records["geom_offset"][0] != records["geom_offset"][1]


def test_write_edge_output_writes_sorted_edge_ids_and_prefix_suffix(tmp_path):
    out_dir = tmp_path / "hut_edges"
    write_edge_records([_rec(base_edge_ids=[30, 10, 20])], out_dir, write_edge_ids=True)
    records = binfmt.load_array(out_dir / "records.npy", mmap=False)
    edge_ids = binfmt.load_array(out_dir / "edge_ids.npy", mmap=False)
    assert list(edge_ids) == [10, 20, 30]
    assert records["edge_id_count"][0] == 3
    assert records["prefix_count"][0] == 3
    assert records["prefix_ids"][0][:3].tolist() == [30, 10, 20]


def test_write_edge_output_skips_edge_ids_when_not_requested(tmp_path):
    out_dir = tmp_path / "start_edges"
    write_edge_records([_rec()], out_dir, write_edge_ids=False)
    assert not (out_dir / "edge_ids.npy").exists()
    records = binfmt.load_array(out_dir / "records.npy", mmap=False)
    assert records["edge_id_count"][0] == 0
    assert records["prefix_count"][0] == 0


from dataclasses import dataclass

from lib.edge_output import fold_endpoint_snaps  # noqa: E402


@dataclass
class _FakeSnap:
    gap_m: float
    gap_dz_m: float


@dataclass
class _FakePath:
    ascent_m: float
    descent_m: float


def test_fold_endpoint_snaps_sums_the_horizontal_gap():
    path = _FakePath(ascent_m=100.0, descent_m=50.0)
    src = _FakeSnap(gap_m=10.0, gap_dz_m=0.0)
    tgt = _FakeSnap(gap_m=5.0, gap_dz_m=0.0)
    snap_m, ascent_m, descent_m = fold_endpoint_snaps(path, src, tgt)
    assert snap_m == 15.0
    assert ascent_m == 100.0
    assert descent_m == 50.0


def test_fold_endpoint_snaps_prices_departure_climb_as_ascent():
    # src below its snap point (gap_dz_m < 0): climbing UP to the trail is ascent.
    path = _FakePath(ascent_m=0.0, descent_m=0.0)
    src = _FakeSnap(gap_m=10.0, gap_dz_m=-20.0)
    tgt = _FakeSnap(gap_m=0.0, gap_dz_m=0.0)
    _, ascent_m, descent_m = fold_endpoint_snaps(path, src, tgt)
    assert ascent_m == 20.0
    assert descent_m == 0.0


def test_fold_endpoint_snaps_prices_arrival_climb_as_ascent():
    # tgt above its snap point (gap_dz_m > 0): climbing UP off the trail to the hut is ascent.
    path = _FakePath(ascent_m=0.0, descent_m=0.0)
    src = _FakeSnap(gap_m=0.0, gap_dz_m=0.0)
    tgt = _FakeSnap(gap_m=10.0, gap_dz_m=30.0)
    _, ascent_m, descent_m = fold_endpoint_snaps(path, src, tgt)
    assert ascent_m == 30.0
    assert descent_m == 0.0
