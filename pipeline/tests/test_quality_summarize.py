import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from quality.summarize import build_summary  # noqa: E402


def test_build_summary_flattens_every_check_across_phases():
    phase_reports = {
        "preprocessing": {"phase": "preprocessing", "checks": [
            {"check": "start_point_integrity", "params": {}, "summary": {"checked": 10, "flagged": 1, "baseline": 1}},
        ]},
        "elevation": {"phase": "elevation", "checks": [
            {"check": "elevation_range", "params": {}, "summary": {"checked": 100, "flagged": 0, "baseline": 0}},
        ]},
    }
    summary = build_summary(phase_reports)
    assert len(summary["checks"]) == 2
    assert {c["phase"] for c in summary["checks"]} == {"preprocessing", "elevation"}
    assert summary["checks"][0]["check"] == "start_point_integrity"
    assert "generated_at" in summary


def test_build_summary_handles_missing_phase_report():
    # a phase report that hasn't been built yet (fresh checkout) must not crash the summary.
    summary = build_summary({"preprocessing": {"phase": "preprocessing", "checks": []}})
    assert summary["checks"] == []
