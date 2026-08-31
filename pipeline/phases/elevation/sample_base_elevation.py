#!/usr/bin/env python3
"""Samples data/dem/dem.tif per BASE-GRAPH NODE and INTERIOR POINT (spec B2 Phase A), not per
record - see compute_edge_profiles.py for the per-edge smoothing/time_s/ascent-descent pass this
feeds into. Split into its own script because it's the half of the old add_base_elevation.py that
--smoothing-kernel-m has no effect on: retuning the kernel used to force a full DEM resample too,
even though the kernel only ever touches the smoothing step downstream.

Why per grid cell and not one big window: nodes.npy holds 6.85M post-contraction junctions and the
shape lives in interior.npy (33.1M points), spread across the whole base graph's bbox. This script
reads data/dem/dem.tif PER GRID CELL (cell_index.npy + lib/grid.py), never as one
74008x39276 window.

Sampling is BILINEAR against the materialized DEM (one cached gdal pass upstream in
build_dem_vrt.py), replacing the old nearest-neighbour np.floor sampling.

Persists node_ele.npy (f4 x 6.85M, 27 MB) and interior_ele.npy (f4 x 33.1M, 132 MB) so
compute_edge_profiles.py and every display path can avoid reopening the DEM.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import binfmt  # noqa: E402
from lib.grid import Grid  # noqa: E402
from lib.pipeline import DEM_DIR, OSM_DIR, load_config  # noqa: E402
from lib.timing import StepTimer, phase  # noqa: E402

SCRIPT_NAME = "sample_base_elevation.py"

# Buffer around a cell's own bounds for its DEM window read - only needs to cover bilinear
# interpolation's 1-pixel neighbourhood for points exactly on the cell boundary, at DEM
# resolutions of 5-10 m this is generous, not tight.
_DEM_WINDOW_BUFFER_KM = 0.2


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


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph-dir", default=str(OSM_DIR / "base_graph"),
                        help="directory holding the persisted base graph (build_base_graph.py's output)")
    parser.add_argument("--dem", default=str(DEM_DIR / "dem.tif"),
                        help="path to the materialized DEM GeoTIFF (build_dem_vrt.py's output)")
    args = parser.parse_args(argv)

    base_graph_dir = Path(args.base_graph_dir)
    timer = StepTimer()
    with phase(SCRIPT_NAME, "sample_base_elevation") as meta:
        with timer.step("load_arrays"):
            manifest = binfmt.load_manifest(base_graph_dir / "manifest.json")
            grid = Grid(manifest["bbox"], manifest["tile_size_km"])
            nodes = binfmt.load_array(base_graph_dir / "nodes.npy", mmap=False)
            cell_index = binfmt.load_array(base_graph_dir / "cell_index.npy", mmap=False)
            interior = binfmt.load_array(base_graph_dir / "interior.npy", mmap=False)

        print(f"sampling DEM over {len(nodes):,} nodes / {len(interior):,} interior points "
              f"across {len(grid.all_cell_ids()):,} cells ...", flush=True)
        node_ele, interior_ele = _sample_all_points(args.dem, nodes, cell_index, interior, grid, timer)

        with timer.step("write"):
            binfmt.save_array(base_graph_dir / "node_ele.npy", node_ele)
            binfmt.save_array(base_graph_dir / "interior_ele.npy", interior_ele)
        print(f"written {base_graph_dir / 'node_ele.npy'}, {base_graph_dir / 'interior_ele.npy'}",
              flush=True)
        meta.update(timer.as_meta())
    print(f"step totals: {timer.summary()}", flush=True)


if __name__ == "__main__":
    main()
