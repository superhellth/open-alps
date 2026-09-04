import hashlib
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from quality.check_postprocessing import (  # noqa: E402
    check_approach_coverage, check_manifest_agreement, check_public_copy_freshness,
    check_shipped_straightness,
)


def test_approach_coverage_flags_hut_with_zero_rows():
    candidates_by_hut = {7: [{"source_type": binfmt.TYPE_PARKING}]}
    approach_columns = {"hut_id": np.array([], dtype="u2"), "source_type": np.array([], dtype="u1")}
    check = check_approach_coverage(candidates_by_hut, approach_columns, n_huts=8, max_flagged=500)
    zero_rows = next(c for c in check["flagged"] if c["reason"] == "zero_approach_rows")
    assert zero_rows["hut_id"] == 7


def test_approach_coverage_flags_dropped_source_type():
    candidates_by_hut = {
        7: [{"source_type": binfmt.TYPE_PARKING}, {"source_type": binfmt.TYPE_STATION}],
    }
    # only the parking row survived selection - station was available but dropped
    approach_columns = {
        "hut_id": np.array([7], dtype="u2"), "source_type": np.array([binfmt.TYPE_PARKING], dtype="u1"),
    }
    check = check_approach_coverage(candidates_by_hut, approach_columns, n_huts=8, max_flagged=500)
    dropped = [c for c in check["flagged"] if c["reason"] == "dropped_source_type"]
    assert len(dropped) == 1
    assert dropped[0]["hut_id"] == 7
    assert dropped[0]["source_type"] == "station"


def test_approach_coverage_clean_case_flags_nothing():
    candidates_by_hut = {7: [{"source_type": binfmt.TYPE_PARKING}]}
    approach_columns = {
        "hut_id": np.array([7], dtype="u2"), "source_type": np.array([binfmt.TYPE_PARKING], dtype="u1"),
    }
    check = check_approach_coverage(candidates_by_hut, approach_columns, n_huts=8, max_flagged=500)
    assert check["summary"]["flagged"] == 0


def test_manifest_agreement_flags_row_count_mismatch():
    check = check_manifest_agreement(
        "hut_edges", n_records=10, payload_rows=9, point_counts=[1] * 10,
        geometry_byte_len=8 * 10, max_flagged=500,
    )
    assert any(r["reason"] == "payload_rows_mismatch" for r in check["flagged"])


def test_manifest_agreement_flags_geometry_point_count_mismatch():
    check = check_manifest_agreement(
        "hut_edges", n_records=10, payload_rows=10, point_counts=[1] * 9,  # only 9 entries, not 10
        geometry_byte_len=8 * 9, max_flagged=500,
    )
    assert any(r["reason"] == "geometry_manifest_row_mismatch" for r in check["flagged"])


def test_manifest_agreement_flags_geometry_byte_length_mismatch():
    check = check_manifest_agreement(
        "hut_edges", n_records=10, payload_rows=10, point_counts=[1] * 10,
        geometry_byte_len=8 * 5,  # should be 8 * sum(point_counts) == 80
        max_flagged=500,
    )
    assert any(r["reason"] == "geometry_byte_length_mismatch" for r in check["flagged"])


def test_manifest_agreement_clean_case_flags_nothing():
    check = check_manifest_agreement(
        "hut_edges", n_records=10, payload_rows=10, point_counts=[1] * 10,
        geometry_byte_len=8 * 10, max_flagged=500,
    )
    assert check["summary"]["flagged"] == 0


def test_shipped_straightness_flags_near_straight_long_edge():
    # a straight line of only 2 points, well over min_length_m, whose recorded path length is
    # close to its endpoint-to-endpoint distance (~758m for these two points) -> straightness
    # close to 1.0, above the 0.97 threshold.
    check = check_shipped_straightness(
        "hut_edges", point_counts=[2], geometry_points=[[(11.0, 47.0), (11.01, 47.0)]],
        lengths_m=[770.0], min_length_m=300, straightness_threshold=0.97, max_points=4,
        max_flagged=500,
    )
    assert check["summary"]["flagged"] == 1


def test_shipped_straightness_skips_short_edges():
    check = check_shipped_straightness(
        "hut_edges", point_counts=[2], geometry_points=[[(11.0, 47.0), (11.0001, 47.0)]],
        lengths_m=[10.0], min_length_m=300, straightness_threshold=0.97, max_points=4,
        max_flagged=500,
    )
    assert check["summary"]["flagged"] == 0


def test_public_copy_freshness_flags_mismatched_hash(tmp_path):
    osm_dir = tmp_path / "osm"
    public_dir = tmp_path / "public"
    osm_dir.mkdir()
    public_dir.mkdir()
    (osm_dir / "huts.geojson").write_bytes(b"fresh")
    (public_dir / "huts.geojson").write_bytes(b"stale")
    check = check_public_copy_freshness(["huts.geojson"], osm_dir, public_dir, max_flagged=500)
    assert check["summary"]["flagged"] == 1
    assert check["flagged"][0]["reason"] == "content_mismatch"


def test_public_copy_freshness_flags_missing_public_file(tmp_path):
    osm_dir = tmp_path / "osm"
    public_dir = tmp_path / "public"
    osm_dir.mkdir()
    public_dir.mkdir()
    (osm_dir / "huts.geojson").write_bytes(b"fresh")
    check = check_public_copy_freshness(["huts.geojson"], osm_dir, public_dir, max_flagged=500)
    assert check["flagged"][0]["reason"] == "missing_in_public"


def test_public_copy_freshness_clean_case_flags_nothing(tmp_path):
    osm_dir = tmp_path / "osm"
    public_dir = tmp_path / "public"
    osm_dir.mkdir()
    public_dir.mkdir()
    content = b"identical"
    (osm_dir / "huts.geojson").write_bytes(content)
    (public_dir / "huts.geojson").write_bytes(content)
    check = check_public_copy_freshness(["huts.geojson"], osm_dir, public_dir, max_flagged=500)
    assert check["summary"]["flagged"] == 0
