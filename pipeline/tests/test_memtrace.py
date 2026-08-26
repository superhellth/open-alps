import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lib.timing as timing  # noqa: E402
from lib.memtrace import rss_sampler  # noqa: E402


def test_sampler_sees_a_large_allocation_made_inside_the_block():
    with rss_sampler(interval_s=0.01) as sample:
        block = np.ones(40_000_000, dtype=np.float64)  # ~320 MB, held for the whole block
        block[0] = 1.0
        time.sleep(0.1)  # give the sampler thread a few ticks
        del block
    assert sample.total_ram_gb > 0
    assert sample.start_rss_gb > 0
    # peak must have risen by roughly the allocation, allowing generous slack for the allocator
    assert sample.peak_rss_gb - sample.start_rss_gb > 0.15


def test_sampler_reports_zero_growth_for_a_trivial_block():
    with rss_sampler(interval_s=0.01) as sample:
        pass
    assert sample.peak_rss_gb >= sample.start_rss_gb
    assert sample.swap_in_delta_mb >= 0


def test_phase_yields_a_mutable_meta_dict(tmp_path, monkeypatch):
    path = tmp_path / "timings.jsonl"
    monkeypatch.setattr(timing, "TIMINGS_PATH", path)

    with timing.phase("test.py", "demo", nodes=5) as meta:
        meta["peak_rss_gb"] = 1.25

    rec = json.loads(path.read_text(encoding="utf-8").strip())
    assert rec["meta"] == {"nodes": 5, "peak_rss_gb": 1.25}
