"""Shared report envelope for pipeline/phases/quality/*.py check modules (spec
docs/superpowers/specs/2026-09-02-data-quality-monitoring-design.md §2). A check module builds
one dict per check via build_check(), collects them into a list, and passes that list to
write_report() to produce data/quality/<phase>.json.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


def build_check(check: str, params: dict, checked: int, flagged_rows: list, baseline: int,
                 max_flagged_rows: int, sort_key=None) -> dict:
    """Builds one envelope entry (spec §2's "checks" array shape). flagged_rows should already be
    worst-first if sort_key is None; otherwise it is sorted descending by sort_key(row) before
    capping. summary.flagged is always the TRUE count (before capping) - truncated is True iff
    that count exceeds max_flagged_rows."""
    if sort_key is not None:
        flagged_rows = sorted(flagged_rows, key=sort_key, reverse=True)
    total = len(flagged_rows)
    return {
        "check": check,
        "params": params,
        "summary": {"checked": checked, "flagged": total, "baseline": baseline},
        "truncated": total > max_flagged_rows,
        "flagged": flagged_rows[:max_flagged_rows],
    }


def write_report(path: Path, phase: str, checks: list) -> None:
    """Writes data/quality/<phase>.json: one envelope per phase, one entry per check."""
    report = {
        "phase": phase,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f)
