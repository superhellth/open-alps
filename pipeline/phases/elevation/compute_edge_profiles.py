#!/usr/bin/env python3
"""Fills time_s/ascent_m/descent_m on every BASE-GRAPH EDGE (spec B2 Phase B) from the per-point
elevations sample_base_elevation.py already wrote (node_ele.npy/interior_ele.npy) - split out from
that script because --smoothing-kernel-m only ever affects this half: retuning it used to force a
full DEM resample too, even though the kernel only touches the smoothing/ascent-descent math here.

Why a separate process from build_base_graph.py: that script already peaks at 12.4 GB of 15.95 GB
(data/timings.jsonl). Node elevation alone gives only the NET delta across a contracted edge, so a
switchback chain over a col would report its endpoint difference and nothing else - this script
reconstructs each edge's full point sequence (node -> interior -> node) to smooth over the real
profile instead.

Ascent/descent are plain sums of positive/negative deltas along the smoothed profile -
eleNoiseThresholdM and its hysteresis loop are retired, and the kernel width (metres) is the
replacement tunable.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from graph_building import build_base_graph as bbg  # noqa: E402
from lib import binfmt, speed  # noqa: E402
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.timing import StepTimer, phase  # noqa: E402

SCRIPT_NAME = "compute_edge_profiles.py"


def smooth_profile(elevations, seg_len_m, kernel_m: float) -> np.ndarray:
    """Distance-weighted moving average (triangular kernel, half-width kernel_m/2) over the
    cumulative distance implied by seg_len_m - the kernel is metres, not points, since point
    spacing varies ~7x across base edges (p25 19.7 m, p75 133.7 m)."""
    elevations = np.asarray(elevations, dtype=np.float64)
    if len(elevations) <= 1 or kernel_m <= 0:
        return elevations.copy()
    seg_len_m = np.asarray(seg_len_m, dtype=np.float64)
    x = np.concatenate([[0.0], np.cumsum(seg_len_m)])
    half_width = kernel_m / 2.0
    diff = np.abs(x[:, None] - x[None, :])
    weight = np.clip(1.0 - diff / half_width, 0.0, None)
    return (weight @ elevations) / weight.sum(axis=1)


def edge_ascent_descent(smoothed, edge_starts, edge_counts) -> tuple:
    """Plain signed-delta sums along each edge's smoothed profile - no threshold, no hysteresis.
    `smoothed` is the tight concatenation of every edge's own point sequence in edge order
    (edge_starts[i] == sum(edge_counts[:i])), the same packing convention as
    build_base_graph.py's flat_interior / binfmt.gather_ragged. Vectorised over every edge at
    once via a single np.diff + bincount pass, not a per-edge Python loop."""
    smoothed = np.asarray(smoothed, dtype=np.float64)
    edge_counts = np.asarray(edge_counts, dtype=np.int64)
    n_edges = len(edge_counts)
    if len(smoothed) < 2:
        return np.zeros(n_edges), np.zeros(n_edges)

    diffs = np.diff(smoothed)
    point_group = np.repeat(np.arange(n_edges), edge_counts)
    left_group, right_group = point_group[:-1], point_group[1:]
    same_edge = left_group == right_group

    ascent_vals = np.where(same_edge & (diffs > 0), diffs, 0.0)
    descent_vals = np.where(same_edge & (diffs < 0), -diffs, 0.0)
    diff_group = np.where(same_edge, left_group, 0)  # group value is irrelevant where weight is 0

    ascent = np.bincount(diff_group, weights=ascent_vals, minlength=n_edges)[:n_edges]
    descent = np.bincount(diff_group, weights=descent_vals, minlength=n_edges)[:n_edges]
    return ascent, descent


def _fill_edge_time_and_elevation(edges, nodes, interior, node_ele, interior_ele, kernel_m,
                                  speed_model, timer: StepTimer):
    """Per base-graph edge: reconstructs its point sequence (u -> interior[offset:offset+count]
    -> v), smooths the elevation profile (kernel_m), computes time_s from the smoothed profile
    (lib.speed.edge_time_s), and appends the smoothed profile to a flat buffer. The per-edge
    reconstruction is a Python loop (same pattern as build_base_graph.py's pack_and_write
    pack_interior loop) - smoothing is an inherently per-edge local operation, a global vectorised
    pass would leak across edge boundaries the same way un-masked ascent/descent would.
    ascent_m/descent_m are filled afterwards in ONE vectorised batch call to edge_ascent_descent
    over every edge's smoothed profile at once."""
    n_edges = len(edges)
    time_s = np.zeros(n_edges, dtype=np.float64)
    edge_point_counts = np.empty(n_edges, dtype=np.int64)
    all_smoothed = []

    node_lon, node_lat = nodes["lon"], nodes["lat"]
    interior_lon, interior_lat = interior["lon"], interior["lat"]
    interior_offset, interior_count = edges["interior_offset"], edges["interior_count"]

    with timer.step("smooth"):
        for i in range(n_edges):
            u, v = int(edges["u"][i]), int(edges["v"][i])
            off, cnt = int(interior_offset[i]), int(interior_count[i])
            lon = np.concatenate(([node_lon[u]], interior_lon[off:off + cnt], [node_lon[v]]))
            lat = np.concatenate(([node_lat[u]], interior_lat[off:off + cnt], [node_lat[v]]))
            elev = np.concatenate(
                ([node_ele[u]], interior_ele[off:off + cnt], [node_ele[v]])
            ).astype(np.float64)
            edge_point_counts[i] = len(elev)

            seg_len = bbg.haversine_m_vec(lon[:-1], lat[:-1], lon[1:], lat[1:]) if len(lon) > 1 \
                else np.zeros(0)
            smoothed = smooth_profile(elev, seg_len, kernel_m)
            all_smoothed.append(smoothed)
            time_s[i] = float(speed.edge_time_s(seg_len, np.diff(smoothed), **speed_model).sum())

            if (i + 1) % 200_000 == 0 or i + 1 == n_edges:
                print(f"  smooth/time_s: {i + 1:,}/{n_edges:,} edges", flush=True)

    flat_smoothed = np.concatenate(all_smoothed) if all_smoothed else np.zeros(0)
    with timer.step("ascent_descent"):
        ascent, descent = edge_ascent_descent(
            flat_smoothed, np.zeros(n_edges, dtype=np.int64), edge_point_counts,
        )

    return time_s, ascent.astype(np.float32), descent.astype(np.float32)


def main(argv=None):
    config = load_config()
    speed_model = config["graph"]["speedModel"]
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph-dir", default=str(OSM_DIR / "base_graph"))
    parser.add_argument("--smoothing-kernel-m", type=float,
                        default=config["dem"]["smoothingKernelM"])
    # Declared as CLI args (not read from config directly) so dodo.py's TaskOptionsChanged can
    # track them - see task_compute_edge_profiles's comment for why a speedModel-only config edit
    # must invalidate this task's cache.
    parser.add_argument("--speed-v0", type=float, default=speed_model["v0"])
    parser.add_argument("--speed-k", type=float, default=speed_model["k"])
    parser.add_argument("--speed-s0", type=float, default=speed_model["s0"])
    args = parser.parse_args(argv)

    base_graph_dir = Path(args.base_graph_dir)
    resolved_speed_model = {"v0": args.speed_v0, "k": args.speed_k, "s0": args.speed_s0}
    timer = StepTimer()
    with phase(SCRIPT_NAME, "compute_edge_profiles", smoothing_kernel_m=args.smoothing_kernel_m,
               **resolved_speed_model) as meta:
        with timer.step("load_arrays"):
            nodes = binfmt.load_array(base_graph_dir / "nodes.npy", mmap=False)
            interior = binfmt.load_array(base_graph_dir / "interior.npy", mmap=False)
            edges = binfmt.load_array(base_graph_dir / "edges.npy", mmap=False)
            node_ele = binfmt.load_array(base_graph_dir / "node_ele.npy", mmap=False)
            interior_ele = binfmt.load_array(base_graph_dir / "interior_ele.npy", mmap=False)

        print(f"computing time_s/ascent_m/descent_m for {len(edges):,} edges ...", flush=True)
        time_s, ascent_m, descent_m = _fill_edge_time_and_elevation(
            edges, nodes, interior, node_ele, interior_ele, args.smoothing_kernel_m,
            resolved_speed_model, timer,
        )
        edges["time_s"] = time_s
        edges["ascent_m"] = ascent_m
        edges["descent_m"] = descent_m

        with timer.step("write"):
            binfmt.save_array(base_graph_dir / "edges.npy", edges)
            (base_graph_dir / "edge_profiles.stamp").write_text(
                f"smoothing_kernel_m={args.smoothing_kernel_m}\n", encoding="utf-8"
            )
        print(f"rewritten {base_graph_dir / 'edges.npy'} with time_s/ascent_m/descent_m", flush=True)
        meta.update(timer.as_meta())
    print(f"step totals: {timer.summary()}", flush=True)


if __name__ == "__main__":
    main()
