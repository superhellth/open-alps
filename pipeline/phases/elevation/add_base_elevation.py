#!/usr/bin/env python3
"""Samples data/dem/dem.tif per BASE-GRAPH EDGE (spec B2), not per record.

Why per edge and not per node: nodes.npy holds 6.85M post-contraction junctions and the shape
lives in interior.npy (33.1M points). Node elevation gives only the NET delta across a contracted
edge, so a switchback chain over a col would report its endpoint difference and nothing else.

Why a separate process from build_base_graph.py: that script already peaks at 12.4 GB of 15.95 GB
(data/timings.jsonl). This one reads the DEM PER GRID CELL (cell_index.npy + lib/grid.py), never
as one 74008x39276 window.

Sampling is BILINEAR against a pre-smoothed raster (one cached gdal pass), replacing the old
nearest-neighbour np.floor into a 5 m (Bavaria DGM5) / 10 m (AT BEV) DEM. Ascent/descent are plain
sums of positive/negative deltas along the smoothed profile - eleNoiseThresholdM and its hysteresis
loop are retired, and the kernel width (metres) is the replacement tunable.

Persists node_ele.npy (f4 x 6.85M, 27 MB) and interior_ele.npy (f4 x 33.1M, 132 MB) so
build_profiles.py and every display path can avoid reopening the DEM.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from graph_building import build_base_graph as bbg  # noqa: E402
from lib import binfmt, speed  # noqa: E402
from lib.grid import Grid  # noqa: E402
from lib.pipeline import DEM_DIR, OSM_DIR, load_config  # noqa: E402
from lib.timing import StepTimer, phase  # noqa: E402

SCRIPT_NAME = "add_base_elevation.py"

# Buffer around a cell's own bounds for its DEM window read - only needs to cover bilinear
# interpolation's 1-pixel neighbourhood for points exactly on the cell boundary, at DEM
# resolutions of 5-10 m this is generous, not tight.
_DEM_WINDOW_BUFFER_KM = 0.2


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


def sample_bilinear(dem_window: np.ndarray, transform, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Bilinear sampling of a DEM window at pixel CENTRES (standard raster convention: transform
    maps integer (col, row) to a pixel's upper-left CORNER, so the centre of pixel (col, row) is
    at fractional pixel coordinate (col + 0.5, row + 0.5)). Replaces the old nearest-neighbour
    np.floor sampling."""
    lon = np.asarray(lon, dtype=np.float64)
    lat = np.asarray(lat, dtype=np.float64)
    inv = ~transform
    col, row = inv * (lon, lat)
    col_f, row_f = col - 0.5, row - 0.5

    height, width = dem_window.shape
    col0 = np.clip(np.floor(col_f).astype(np.int64), 0, width - 1)
    row0 = np.clip(np.floor(row_f).astype(np.int64), 0, height - 1)
    col1 = np.clip(col0 + 1, 0, width - 1)
    row1 = np.clip(row0 + 1, 0, height - 1)
    fx = np.clip(col_f - col0, 0.0, 1.0)
    fy = np.clip(row_f - row0, 0.0, 1.0)

    v00 = dem_window[row0, col0].astype(np.float64)
    v01 = dem_window[row0, col1].astype(np.float64)
    v10 = dem_window[row1, col0].astype(np.float64)
    v11 = dem_window[row1, col1].astype(np.float64)
    return (1 - fx) * (1 - fy) * v00 + fx * (1 - fy) * v01 + (1 - fx) * fy * v10 + fx * fy * v11


def _sample_all_points(dem_path, nodes, cell_index, interior, grid, timer: StepTimer):
    """Fills node_ele/interior_ele by reading one DEM window per grid cell (never the whole
    74008x39276 raster at once - see module docstring). nodes are already sorted/CSR-indexed by
    cell_id (build_base_graph.py's pack_and_write); interior points carry no cell_id, so their
    per-cell grouping is computed here the same way (grid.cell_ids_for_points + build_csr_index)."""
    import rasterio
    import rasterio.windows

    node_ele = np.zeros(len(nodes), dtype=np.float32)
    interior_ele = np.zeros(len(interior), dtype=np.float32)

    interior_cell_ids = grid.cell_ids_for_points(interior["lon"], interior["lat"])
    n_cells = len(grid.all_cell_ids())
    interior_order, interior_cell_index = binfmt.build_csr_index(interior_cell_ids, n_groups=n_cells)

    with rasterio.open(dem_path) as dem:
        for cell_id in range(n_cells):
            n_start, n_count = int(cell_index["start_offset"][cell_id]), int(cell_index["count"][cell_id])
            i_start, i_count = (int(interior_cell_index["start_offset"][cell_id]),
                                int(interior_cell_index["count"][cell_id]))
            if n_count == 0 and i_count == 0:
                continue

            with timer.step("read_dem"):
                bounds = grid.padded_bounds(cell_id, _DEM_WINDOW_BUFFER_KM)
                window = rasterio.windows.from_bounds(
                    bounds["minLng"], bounds["minLat"], bounds["maxLng"], bounds["maxLat"],
                    transform=dem.transform,
                ).round_offsets().round_lengths()
                window = window.intersection(rasterio.windows.Window(0, 0, dem.width, dem.height))
                band = dem.read(1, window=window)
                window_transform = rasterio.windows.transform(window, dem.transform)

            with timer.step("sample"):
                if n_count:
                    node_ele[n_start:n_start + n_count] = sample_bilinear(
                        band, window_transform,
                        nodes["lon"][n_start:n_start + n_count], nodes["lat"][n_start:n_start + n_count],
                    )
                if i_count:
                    idx = interior_order[i_start:i_start + i_count]
                    interior_ele[idx] = sample_bilinear(
                        band, window_transform, interior["lon"][idx], interior["lat"][idx],
                    )

            print(f"  sample: cell {cell_id + 1}/{n_cells} -> {n_count:,} nodes, "
                  f"{i_count:,} interior points", flush=True)

    return node_ele, interior_ele


def _fill_edge_time_and_elevation(edges, nodes, interior, node_ele, interior_ele, kernel_m,
                                  speed_model, timer: StepTimer):
    """Per base-graph edge: reconstructs its point sequence (u -> interior[offset:offset+count]
    -> v), smooths the elevation profile (kernel_m), computes time_s from the smoothed profile
    (lib.speed.edge_time_s), and appends the smoothed profile to a flat buffer. The per-edge
    reconstruction is a Python loop (same pattern as build_base_graph.py's pack_and_write
    pack_interior loop, and the old add_elevation.py's fill_elevation_records) - smoothing is an
    inherently per-edge local operation, a global vectorised pass would leak across edge
    boundaries the same way un-masked ascent/descent would. ascent_m/descent_m are filled
    afterwards in ONE vectorised batch call to edge_ascent_descent (Task 7) over every edge's
    smoothed profile at once."""
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph-dir", default=str(OSM_DIR / "base_graph"))
    parser.add_argument("--dem", default=str(DEM_DIR / "dem.tif"))
    parser.add_argument("--smoothing-kernel-m", type=float,
                        default=config["dem"]["smoothingKernelM"])
    args = parser.parse_args(argv)

    base_graph_dir = Path(args.base_graph_dir)
    timer = StepTimer()
    with phase(SCRIPT_NAME, "add_base_elevation", smoothing_kernel_m=args.smoothing_kernel_m) as meta:
        with timer.step("load_arrays"):
            manifest = binfmt.load_manifest(base_graph_dir / "manifest.json")
            grid = Grid(manifest["bbox"], manifest["tile_size_km"])
            nodes = binfmt.load_array(base_graph_dir / "nodes.npy", mmap=False)
            cell_index = binfmt.load_array(base_graph_dir / "cell_index.npy", mmap=False)
            interior = binfmt.load_array(base_graph_dir / "interior.npy", mmap=False)
            edges = binfmt.load_array(base_graph_dir / "edges.npy", mmap=False)

        print(f"sampling DEM over {len(nodes):,} nodes / {len(interior):,} interior points "
              f"across {len(grid.all_cell_ids()):,} cells ...", flush=True)
        node_ele, interior_ele = _sample_all_points(args.dem, nodes, cell_index, interior, grid, timer)

        with timer.step("write"):
            binfmt.save_array(base_graph_dir / "node_ele.npy", node_ele)
            binfmt.save_array(base_graph_dir / "interior_ele.npy", interior_ele)
        print(f"written {base_graph_dir / 'node_ele.npy'}, {base_graph_dir / 'interior_ele.npy'}",
              flush=True)

        print(f"computing time_s/ascent_m/descent_m for {len(edges):,} edges ...", flush=True)
        time_s, ascent_m, descent_m = _fill_edge_time_and_elevation(
            edges, nodes, interior, node_ele, interior_ele, args.smoothing_kernel_m,
            config["graph"]["speedModel"], timer,
        )
        edges["time_s"] = time_s
        edges["ascent_m"] = ascent_m
        edges["descent_m"] = descent_m

        with timer.step("write"):
            binfmt.save_array(base_graph_dir / "edges.npy", edges)
        print(f"rewritten {base_graph_dir / 'edges.npy'} with time_s/ascent_m/descent_m", flush=True)
        meta.update(timer.as_meta())
    print(f"step totals: {timer.summary()}", flush=True)


if __name__ == "__main__":
    main()
