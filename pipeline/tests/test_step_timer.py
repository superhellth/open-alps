import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.timing import StepTimer  # noqa: E402


def test_accumulates_seconds_and_calls_per_step():
    timer = StepTimer()
    for _ in range(3):
        with timer.step("snap"):
            time.sleep(0.01)
    with timer.step("distances"):
        time.sleep(0.01)

    assert timer.calls["snap"] == 3
    assert timer.calls["distances"] == 1
    assert timer.seconds["snap"] > timer.seconds["distances"]


def test_step_records_time_even_when_the_block_raises():
    # A worker that dies mid-cell should still leave the parent a usable partial breakdown -
    # unlike phase(), which deliberately writes nothing on failure.
    timer = StepTimer()
    try:
        with timer.step("paths"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert timer.calls["paths"] == 1


def test_merge_sums_worker_totals():
    a, b = StepTimer(), StepTimer()
    a.seconds["snap"], a.calls["snap"] = 1.0, 2
    b.seconds["snap"], b.calls["snap"] = 2.5, 3
    b.seconds["paths"], b.calls["paths"] = 4.0, 7
    a.merge(b)
    assert a.seconds == {"snap": 3.5, "paths": 4.0}
    assert a.calls == {"snap": 5, "paths": 7}


def test_count_bumps_a_counter_without_timing_it():
    timer = StepTimer()
    timer.count("snap_hubs", 12)
    timer.count("snap_hubs", 3)
    assert timer.calls["snap_hubs"] == 15
    assert "snap_hubs" not in timer.seconds


def test_as_meta_is_json_safe_and_flat():
    timer = StepTimer()
    timer.seconds["snap"], timer.calls["snap"] = 1.234, 2
    meta = timer.as_meta()
    assert meta == {"snap_s": 1.23, "snap_calls": 2}


def test_summary_orders_steps_by_cost():
    timer = StepTimer()
    timer.seconds["snap"], timer.calls["snap"] = 1.0, 1
    timer.seconds["paths"], timer.calls["paths"] = 3.0, 1
    assert timer.summary().startswith("paths")


def test_step_timer_meta_round_trips_through_a_phase_record(tmp_path, monkeypatch):
    # The shape every instrumented script writes: one phase() record whose meta carries the split.
    import lib.timing as timing

    monkeypatch.setattr(timing, "TIMINGS_PATH", tmp_path / "timings.jsonl")
    timer = StepTimer()
    with timer.step("tippecanoe"):
        pass
    timer.count("n_edges", 7)

    with timing.phase("build_edge_tiles.py", "build_edge_tiles", layer="hut_edges",
                      **timer.as_meta()):
        pass

    import json
    rec = json.loads((tmp_path / "timings.jsonl").read_text(encoding="utf-8").strip())
    assert rec["phase"] == "build_edge_tiles"
    assert rec["meta"]["layer"] == "hut_edges"
    assert rec["meta"]["n_edges_calls"] == 7
    assert "tippecanoe_s" in rec["meta"]
