import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from postprocessing.build_edge_ids import pack_edge_ids  # noqa: E402


def _record(edge_id_offset, edge_id_count, prefix_ids, prefix_count, suffix_ids, suffix_count):
    return (
        0, 1, binfmt.TYPE_HUT, binfmt.TYPE_HUT, binfmt.VARIANT_FAST_ANY,
        1000.0, 0.0, 50.0, 20.0, 1500.0, 0.0, 0.0, 5.0, 1, False, 0, 2, 0, 0,
        edge_id_offset, edge_id_count,
        tuple(prefix_ids), prefix_count, tuple(suffix_ids), suffix_count,
    )


def test_pack_edge_ids_round_trips_two_records():
    records = np.array([
        _record(0, 3, [30, 10, 20, -1, -1, -1, -1, -1], 3, [20, 10, 30, -1, -1, -1, -1, -1], 3),
        _record(3, 2, [40, -1, -1, -1, -1, -1, -1, -1], 1, [50, -1, -1, -1, -1, -1, -1, -1], 1),
    ], dtype=binfmt.RECORD_DTYPE)
    flat_edge_ids = np.array([10, 20, 30, 40, 50], dtype="i4")

    payload, manifest = pack_edge_ids(records, flat_edge_ids)

    assert manifest["rows"] == 2
    assert manifest["k"] == 8
    assert manifest["edge_id_count"] == [3, 2]
    assert manifest["prefix_count"] == [3, 1]
    assert manifest["suffix_count"] == [3, 1]

    sorted_bytes = manifest["sorted_bytes"]
    prefix_bytes = manifest["prefix_bytes"]
    suffix_bytes = manifest["suffix_bytes"]
    assert sorted_bytes + prefix_bytes + suffix_bytes == len(payload)

    sorted_arr = np.frombuffer(payload[:sorted_bytes], dtype="i4")
    prefix_arr = np.frombuffer(payload[sorted_bytes:sorted_bytes + prefix_bytes], dtype="i4")
    suffix_arr = np.frombuffer(
        payload[sorted_bytes + prefix_bytes:sorted_bytes + prefix_bytes + suffix_bytes], dtype="i4"
    )

    assert sorted_arr.tolist() == [10, 20, 30, 40, 50]
    assert prefix_arr[:8].tolist() == [30, 10, 20, -1, -1, -1, -1, -1]
    assert prefix_arr[8:16].tolist() == [40, -1, -1, -1, -1, -1, -1, -1]
    assert suffix_arr[:8].tolist() == [20, 10, 30, -1, -1, -1, -1, -1]
