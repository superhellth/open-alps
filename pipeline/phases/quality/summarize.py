#!/usr/bin/env python3
"""Flattens every phase's data/quality/<phase>.json into one data/quality/summary.json (spec
docs/superpowers/specs/2026-09-02-data-quality-monitoring-design.md §2): one file that says
whether anything needs follow-up without opening all four phase reports.

Usage: python pipeline/phases/quality/summarize.py
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.pipeline import QUALITY_DIR  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "summarize.py"
PHASES = ["preprocessing", "elevation", "graph_building", "postprocessing"]


def build_summary(phase_reports: dict) -> dict:
    checks = []
    for phase_name, report in phase_reports.items():
        for check in report.get("checks", []):
            checks.append({
                "phase": phase_name, "check": check["check"], "params": check.get("params", {}),
                "summary": check["summary"],
            })
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "checks": checks}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--quality-dir", default=str(QUALITY_DIR))
    parser.add_argument("--out", default=str(QUALITY_DIR / "summary.json"))
    args = parser.parse_args(argv)

    quality_dir = Path(args.quality_dir)

    with phase(SCRIPT_NAME, "quality_summary"):
        phase_reports = {}
        for phase_name in PHASES:
            report_path = quality_dir / f"{phase_name}.json"
            if not report_path.exists():
                continue
            with open(report_path, encoding="utf-8") as f:
                phase_reports[phase_name] = json.load(f)

        summary = build_summary(phase_reports)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(summary, f)
        flagged_checks = [c for c in summary["checks"] if c["summary"]["flagged"] > 0]
        print(f"quality summary: {len(summary['checks'])} checks, "
              f"{len(flagged_checks)} with flagged rows", flush=True)
        print(f"written {args.out}", flush=True)


if __name__ == "__main__":
    main()
