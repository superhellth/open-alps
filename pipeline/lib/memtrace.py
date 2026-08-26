"""Samples process RSS on a background thread for the duration of a block, so an expensive phase
can record how close it came to physical RAM alongside its wall-clock time. Exists because
build_base_graph.py's contract_structural phase costs ~96us per raw edge - roughly 30x what its
Python walk body should cost - on a 17.1 GB box where the live set is estimated at 15-20 GB. A
seconds number alone cannot tell swapping apart from slow code; this is the other half.

See docs/superpowers/plans/2026-08-20-contraction-measurement-spike.md.
"""

import threading
from contextlib import contextmanager
from dataclasses import dataclass

import psutil

_GB = 1024 ** 3
_MB = 1024 ** 2


@dataclass
class RssSample:
    total_ram_gb: float = 0.0
    start_rss_gb: float = 0.0
    peak_rss_gb: float = 0.0
    swap_in_delta_mb: float = 0.0

    def as_meta(self) -> dict:
        return {
            "total_ram_gb": round(self.total_ram_gb, 2),
            "start_rss_gb": round(self.start_rss_gb, 2),
            "peak_rss_gb": round(self.peak_rss_gb, 2),
            "swap_in_delta_mb": round(self.swap_in_delta_mb, 1),
        }


@contextmanager
def rss_sampler(interval_s: float = 0.5):
    proc = psutil.Process()
    sample = RssSample(
        total_ram_gb=psutil.virtual_memory().total / _GB,
        start_rss_gb=proc.memory_info().rss / _GB,
    )
    sample.peak_rss_gb = sample.start_rss_gb
    swap_in_start = psutil.swap_memory().sin

    stop = threading.Event()

    def _poll():
        while not stop.wait(interval_s):
            try:
                rss = proc.memory_info().rss / _GB
            except psutil.Error:  # process gone / permission blip - nothing useful to record
                return
            if rss > sample.peak_rss_gb:
                sample.peak_rss_gb = rss

    thread = threading.Thread(target=_poll, daemon=True, name="rss-sampler")
    thread.start()
    try:
        yield sample
    finally:
        stop.set()
        thread.join(timeout=interval_s * 4)
        rss = proc.memory_info().rss / _GB
        if rss > sample.peak_rss_gb:
            sample.peak_rss_gb = rss
        # psutil's swap sin/sout are cumulative machine-wide counters; the delta over the block is
        # the signal that this block (or something contending with it) actually paged in.
        sample.swap_in_delta_mb = max(0.0, (psutil.swap_memory().sin - swap_in_start) / _MB)
