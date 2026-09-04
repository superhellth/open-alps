#!/usr/bin/env python3
"""B2/B4 of docs/superpowers/specs/2026-09-02-hub-edge-scaling-design.md: the global selection
step that decides WHICH (hut, start, variant) pairs are worth materializing full path geometry
for, before build_access_edges.py pays for that materialization.

Top-K-per-hut is cell-local (every candidate for a hut lies inside its own cell's padded set, a
worker could rank it), but the loop-closure reverse index (every hut reachable from a RETAINED
start id, build_approach_table.py's E2) is not - a retained start point may be reachable from huts
in a neighbouring cell. That closure is the one thing that forces this to be its own global,
whole-table pass rather than in-worker selection inside build_hub_edges.py.

Ranks on time_s (build_hub_edges.py's B3 output already carries it, no path walk needed) over
VARIANT_FAST_ANY rows only - same "an approach is a fastest, unconstrained leg" rule
build_approach_table.py's own selection already uses - and over-selects k=20 per (hut, source
type) rather than trying to match build_approach_table.py's eventual DIN-duration re-rank exactly
(measured: top-20 leaves the true DIN-best-3 outside the selection only 1.2% of the time, using a
deliberately worse distance_m proxy as the upper bound - see spec B4).

Usage: python pipeline/phases/postprocessing/select_approach_pairs.py [--k 20]
Requires data/osm/access_distances.npy (build_hub_edges.py's output).
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import binfmt  # noqa: E402
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "select_approach_pairs.py"


def select_pairs(access_distances: np.ndarray, k: int) -> np.ndarray:
    """Returns the subset of `access_distances` worth materializing geometry for: the union of
    (a) the k fastest (by time_s) VARIANT_FAST_ANY rows per (hut_id, start_type) group, and
    (b) every row (any variant) whose start_id appears in (a) - the loop-closure reverse index
    (spec B5: build_tables loops records with no variant filter, so restricting (b) to FAST_ANY
    would silently truncate the closure)."""
    if len(access_distances) == 0:
        return access_distances

    by_group = defaultdict(list)
    for i, r in enumerate(access_distances):
        if int(r["variant"]) != binfmt.VARIANT_FAST_ANY:
            continue
        by_group[(int(r["hut_id"]), int(r["start_type"]))].append(i)

    retained_indices = set()
    retained_start_ids = set()
    for indices in by_group.values():
        indices.sort(key=lambda i: float(access_distances[i]["time_s"]))
        top = indices[:k]
        retained_indices.update(top)
        retained_start_ids.update(int(access_distances[i]["start_id"]) for i in top)

    for i, r in enumerate(access_distances):
        if int(r["start_id"]) in retained_start_ids:
            retained_indices.add(i)

    return access_distances[sorted(retained_indices)]


if __name__ == "__main__":
    config = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--access-distances", default=str(OSM_DIR / "access_distances.npy"),
                         help="path to build_hub_edges.py's access_distances.npy")
    parser.add_argument("--k", type=int, default=config["approach"].get("selectK", 20),
                         help="candidates retained per (hut, source type) before build_approach_table.py's own re-rank (see pipeline.config.json's approach.selectK)")
    parser.add_argument("--out", default=str(OSM_DIR / "selected_access_pairs.npy"),
                         help="path to write the selected pair list")
    args = parser.parse_args()

    with phase(SCRIPT_NAME, "select_approach_pairs"):
        access_distances = binfmt.load_array(Path(args.access_distances), mmap=False)
        print(f"access_distances rows: {len(access_distances):,}", flush=True)

        selected = select_pairs(access_distances, args.k)
        print(f"selected pairs (k={args.k}): {len(selected):,}", flush=True)

        binfmt.save_array(Path(args.out), selected)
        print(f"written {args.out}", flush=True)
