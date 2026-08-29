"""Per-cell progress reporting + worker-pool scaffolding shared by snap_hubs.py,
gather_route_subgraphs.py and build_hub_edges.py's __main__ loops - each used to hand-roll its own
ProcessPoolExecutor/as_completed submit loop and its own `elapsed/avg/remaining` arithmetic for the
"[i/total] ... | elapsed Xm, ~Ym remaining" line pipeline/CLAUDE.md's progress-logging convention
requires of every long-running script."""

import time
from concurrent.futures import ProcessPoolExecutor, as_completed


def run_pool(tasks: list, worker_fn, workers: int = None):
    """Submits every task to a ProcessPoolExecutor and yields each result as it completes (order
    not preserved - same semantics as as_completed). worker_fn must be a module-level function
    (picklable) taking one task element."""
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker_fn, t) for t in tasks]
        for fut in as_completed(futures):
            yield fut.result()


class ProgressTracker:
    """Tracks completed/total + elapsed wall clock, for printing one progress line per finished
    unit of work. Average-so-far * remaining-count is a deliberately simple ETA - good enough for
    a human watching stdout, not a claim of precision."""

    def __init__(self, total: int):
        self.total = total
        self.completed = 0
        self.t_start = time.time()

    def tick(self) -> tuple:
        """Call once per completed unit of work. Returns (overall_elapsed_s, remaining_s)."""
        self.completed += 1
        overall_elapsed = time.time() - self.t_start
        avg_s = overall_elapsed / self.completed
        remaining_s = avg_s * (self.total - self.completed)
        return overall_elapsed, remaining_s

    def eta_suffix(self) -> str:
        """`tick()` then format its result as the trailing "| elapsed Xm, ~Ym remaining" every
        graph_building script prints - call this in place of `tick()` when the caller doesn't need
        the raw seconds itself."""
        overall_elapsed, remaining_s = self.tick()
        return f"elapsed {overall_elapsed/60:.1f}m, ~{remaining_s/60:.1f}m remaining"
