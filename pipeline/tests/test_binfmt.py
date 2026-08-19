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
