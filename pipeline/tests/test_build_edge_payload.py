import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from lib.anchors import anchor_column_names, decode_row  # noqa: E402
from postprocessing.build_edge_payload import anchor_columns_for_payload, hut_guids, pack_edges  # noqa: E402


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


def test_pack_edges_has_no_tour_columns():
    payload, manifest = pack_edges(RECORDS, HUT_IDS)
    assert "tour_id" not in manifest["columns"]
    assert "leg_index" not in manifest["columns"]





def test_hut_guids_in_feature_order():
    feats = [{"properties": {"id": "{A}"}}, {"properties": {"id": "{B}"}}]
    assert hut_guids(feats) == ["{A}", "{B}"]


@pytest.mark.parametrize("bad", [{}, {"id": None}, {"id": ""}])
def test_hut_guids_rejects_missing_guid(bad):
    with pytest.raises(ValueError):
        hut_guids([{"properties": {"id": "{A}"}}, {"properties": bad}])


def test_anchor_columns_are_appended_as_i2_after_the_scalar_columns():
    records = _records([_record(0, 1, binfmt.VARIANT_FAST_ANY)])
    records["geom_offset"], records["geom_count"] = 0, 2
    geometry = np.zeros(2, dtype=binfmt.COORD_DTYPE)
    geometry["lon"], geometry["lat"] = [11.0, 11.4], [47.0, 47.0]
    hut_lonlat = np.array([[11.0, 47.0], [11.4, 47.0]])

    anchors = anchor_columns_for_payload(records, geometry, hut_lonlat)
    payload, manifest = pack_edges(records, ["a", "b"], anchors)

    for name in anchor_column_names():
        assert manifest["columns"][name]["dtype"] == "i2"
    cols = {n: np.frombuffer(payload, dtype="i2", count=1, offset=s["offset"])
            for n, s in manifest["columns"].items() if n in anchors}
    assert decode_row(cols, 0, hut_lonlat[0])[1] == pytest.approx([11.2, 47.0], abs=1e-4)


def test_pack_edges_without_anchors_is_unchanged():
    _, manifest = pack_edges(RECORDS, HUT_IDS)
    assert "a50_dlat" not in manifest["columns"]
