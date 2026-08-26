"""Records how long pipeline phases take, so later runs can be compared against real numbers
instead of guesses - see pipeline/CLAUDE.md for why this matters (scope is expected to grow past
AT+Bayern, and this is how we'll see which phases stop scaling).

Appends one JSON line per phase to data/timings.jsonl. A phase's line is only written if its
`with phase(...):` block completes without raising - contextlib.contextmanager already skips the
post-yield code on an exception, so a failed run leaves no (misleading, partial) record.
"""

import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

TIMINGS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "timings.jsonl"


@contextmanager
def phase(script: str, name: str, **meta):
    t0 = time.monotonic()
    yield meta  # mutable: a block can add values (e.g. peak RSS) only knowable at the end
    elapsed = time.monotonic() - t0
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "script": script,
        "phase": name,
        "seconds": round(elapsed, 2),
    }
    if meta:
        rec["meta"] = meta
    with open(TIMINGS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


class StepTimer:
    """In-process accumulator for sub-phase timings. Two cases `phase()` cannot serve:

    1. A step that runs many times inside one phase (a per-cell/per-edge-set loop) - one
       `phase(...)` line per execution would bury the file in near-identical records.
    2. A step running in a worker process - `phase()` appends to a single file, so N
       ProcessPoolExecutor workers calling it concurrently risks interleaved lines.

    A StepTimer instead sums elapsed time and call counts per step name in memory; the parent
    merges every worker's totals and writes ONE `phase(...)` record carrying the whole split as
    meta. It is also just a convenient way to get a several-step breakdown of a single-process
    script into one record (see `phases/postprocessing/build_edge_tiles.py`).

    Steps must not nest: `summary()`'s percentages and `as_meta()`'s columns are only a real
    split of the run if each step is disjoint from the others.

    Usage:
        timer = StepTimer()
        with timer.step("snap"):
            ...
        parent_timer.merge(timer)          # in the parent, per returned worker result
        meta.update(parent_timer.as_meta())
    """

    def __init__(self):
        self.seconds = {}
        self.calls = {}

    @contextmanager
    def step(self, name: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.seconds[name] = self.seconds.get(name, 0.0) + (time.perf_counter() - t0)
            self.calls[name] = self.calls.get(name, 0) + 1

    def count(self, name: str, n: int = 1) -> None:
        """Bumps a pure counter (no timing) - e.g. how many pairs survived the cutoff."""
        self.calls[name] = self.calls.get(name, 0) + n

    def merge(self, other: "StepTimer") -> None:
        for name, secs in other.seconds.items():
            self.seconds[name] = self.seconds.get(name, 0.0) + secs
        for name, n in other.calls.items():
            self.calls[name] = self.calls.get(name, 0) + n

    def as_meta(self) -> dict:
        """Flat, JSON-safe meta for a `phase(...)` record: `<step>_s` / `<step>_calls`."""
        meta = {f"{name}_s": round(secs, 2) for name, secs in sorted(self.seconds.items())}
        meta.update({f"{name}_calls": n for name, n in sorted(self.calls.items())})
        return meta

    def summary(self) -> str:
        """One-line human breakdown, ordered by cost - for the progress/summary prints."""
        if not self.seconds:
            return "(no steps timed)"
        total = sum(self.seconds.values())
        parts = [
            f"{name} {secs:.1f}s ({100 * secs / total:.0f}%, {self.calls.get(name, 0):,}x)"
            for name, secs in sorted(self.seconds.items(), key=lambda kv: -kv[1])
        ]
        return " | ".join(parts)
