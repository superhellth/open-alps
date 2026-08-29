import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from postprocessing.build_edge_payload import pack_edges  # noqa: E402


def _record(from_id, to_id, variant, distance_m=1000.0, ascent_m=50.0, descent_m=20.0,
            max_ele_m=1500.0, sac_rank=2, via_ferrata=False, road_m=10.0, ungraded_m=0.0,
            inferred_m=0.0, snap_m=5.0):
    return (
        from_id, to_id, binfmt.TYPE_HUT, binfmt.TYPE_HUT, variant,
        distance_m, road_m, ascent_m, descent_m, max_ele_m, ungraded_m, inferred_m, snap_m,
        sac_rank, via_ferrata, 0, 2, 0, 3,
        0, 0, (-1,) * 8, 0, (-1,) * 8, 0,
    )


def _records(rows):
    return np.array(rows, dtype=binfmt.RECORD_DTYPE)


RECORDS = _records([
    _record(0, 1, binfmt.VARIANT_FAST_ANY),
    _record(0, 1, binfmt.VARIANT_FAST_T2),
    _record(1, 2, binfmt.VARIANT_FAST_ANY),
])
HUT_IDS = ["hut-a", "hut-b", "hut-c"]


def test_hut_ids_narrow_to_u2():
    _, manifest = pack_edges(RECORDS, HUT_IDS)
    assert manifest["columns"]["from_id"]["dtype"] == "u2"


def test_manifest_round_trips_every_column():
    payload, manifest = pack_edges(RECORDS, HUT_IDS)
    for name, spec in manifest["columns"].items():
        col = np.frombuffer(payload, dtype=spec["dtype"], count=manifest["rows"],
                            offset=spec["offset"])
        assert len(col) == manifest["rows"], name


def test_columns_are_contiguous_not_interleaved():
    payload, manifest = pack_edges(RECORDS, HUT_IDS)
    offsets = sorted(s["offset"] for s in manifest["columns"].values())
    assert offsets == sorted(set(offsets))
    assert offsets[0] == 0


def test_no_duration_column_is_shipped():
    _, manifest = pack_edges(RECORDS, HUT_IDS)
    assert not any("time" in c or "duration" in c for c in manifest["columns"])


def test_geometry_offsets_are_not_in_the_payload():
    _, manifest = pack_edges(RECORDS, HUT_IDS)
    assert "geom_offset" not in manifest["columns"]
