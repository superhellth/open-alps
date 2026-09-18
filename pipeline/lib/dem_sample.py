"""DEM bilinear sampling generalized to an arbitrary ordered list of (lon, lat) points - moved out
match_tour_edges.py samples one small window per tour leg's own GPX trace bbox - a trace is always
small enough that one window per call is the right granularity. See
docs/superpowers/specs/2026-09-14-gpx-hut-snap-design.md."""

import math
from pathlib import Path

import numpy as np

# Buffer around a trace's own bounds for its DEM window read - only needs to cover bilinear
# interpolation's 1-pixel neighbourhood for points exactly on the window boundary; at DEM
# resolutions of 5-10m this is generous, not tight.
_DEM_WINDOW_BUFFER_KM = 0.2


def sample_bilinear(dem_window: np.ndarray, transform, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Bilinear sampling of a DEM window at pixel CENTRES (standard raster convention: transform
    maps integer (col, row) to a pixel's upper-left CORNER, so the centre of pixel (col, row) is at
    fractional pixel coordinate (col + 0.5, row + 0.5))."""
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


def _bounds_with_buffer(points: list, buffer_km: float) -> tuple:
    """(min_lon, min_lat, max_lon, max_lat) around `points`, padded by buffer_km - same per-point-
    local flat-earth degree conversion as lib/geo.py's circle_polygon (one degree of longitude is
    only cos(lat) as many real km as one degree of latitude away from the equator)."""
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    lat_mean = sum(lats) / len(lats)
    deg_per_km_lat = 1 / 111.320
    deg_per_km_lng = 1 / (111.320 * math.cos(math.radians(lat_mean)))
    dlat = buffer_km * deg_per_km_lat
    dlng = buffer_km * deg_per_km_lng
    return min(lons) - dlng, min(lats) - dlat, max(lons) + dlng, max(lats) + dlat


def sample_points(dem_path: Path, points: list) -> np.ndarray:
    """Opens dem_path, reads ONE windowed slice covering `points`' own bbox (+ buffer), then
    bilinear-samples every point in order. `points` is an ordered list of (lon, lat) tuples."""
    import rasterio
    import rasterio.windows

    lons = np.array([p[0] for p in points], dtype=np.float64)
    lats = np.array([p[1] for p in points], dtype=np.float64)
    with rasterio.open(dem_path) as dem:
        min_lon, min_lat, max_lon, max_lat = _bounds_with_buffer(points, _DEM_WINDOW_BUFFER_KM)
        raw = rasterio.windows.from_bounds(
            min_lon, min_lat, max_lon, max_lat, transform=dem.transform,
        )
        col_off = math.floor(raw.col_off)
        row_off = math.floor(raw.row_off)
        width = max(1, math.ceil(raw.col_off + raw.width) - col_off)
        height = max(1, math.ceil(raw.row_off + raw.height) - row_off)
        window = rasterio.windows.Window(col_off, row_off, width, height)
        window = window.intersection(rasterio.windows.Window(0, 0, dem.width, dem.height))
        band = dem.read(1, window=window)
        window_transform = rasterio.windows.transform(window, dem.transform)
        return sample_bilinear(band, window_transform, lons, lats)
