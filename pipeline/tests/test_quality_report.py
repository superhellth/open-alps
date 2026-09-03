import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.quality_report import build_check, write_report  # noqa: E402


def test_build_check_reports_true_count_and_caps_flagged_rows():
    rows = [{"id": i, "metric": i} for i in range(10)]
    check = build_check(
        "some_check", params={"threshold": 5}, checked=100, flagged_rows=rows,
        baseline=10, max_flagged_rows=3, sort_key=lambda r: r["metric"],
    )
    assert check["check"] == "some_check"
    assert check["params"] == {"threshold": 5}
    assert check["summary"] == {"checked": 100, "flagged": 10, "baseline": 10}
    assert check["truncated"] is True
    assert len(check["flagged"]) == 3
    assert [r["id"] for r in check["flagged"]] == [9, 8, 7]  # worst-first (highest metric first)


def test_build_check_not_truncated_when_under_cap():
    check = build_check(
        "clean_check", params={}, checked=50, flagged_rows=[], baseline=0, max_flagged_rows=500,
    )
    assert check["truncated"] is False
    assert check["flagged"] == []
    assert check["summary"]["flagged"] == 0


def test_write_report_writes_envelope_with_phase_and_checks(tmp_path):
    checks = [build_check("c1", {}, 1, [], 0, 500)]
    out = tmp_path / "preprocessing.json"
    write_report(out, "preprocessing", checks)

    report = json.loads(out.read_text())
    assert report["phase"] == "preprocessing"
    assert "generated_at" in report
    assert report["checks"] == checks


def test_write_report_creates_parent_directories(tmp_path):
    out = tmp_path / "nested" / "dir" / "report.json"
    write_report(out, "preprocessing", [])
    assert out.exists()
