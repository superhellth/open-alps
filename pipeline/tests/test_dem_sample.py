import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import dem_sample  # noqa: E402


def test_bilinear_sampling_interpolates_between_cells():
    from affine import Affine
    window = np.array([[0.0, 10.0], [20.0, 30.0]], dtype=np.float32)
    transform = Affine(1.0, 0.0, 0.0, 0.0, -1.0, 0.0)
    got = dem_sample.sample_bilinear(window, transform, np.array([1.0]), np.array([-1.0]))
    assert got[0] == pytest.approx(15.0)


def test_sample_points_reads_a_window_and_bilinear_samples(tmp_path):
    import rasterio
    from rasterio.transform import from_origin

    data = np.array([[0.0, 10.0], [20.0, 30.0]], dtype=np.float32)
    # top-left corner (10.0, 47.0), 1deg pixels: row0 spans lat[46,47], row1 spans lat[45,46];
    # col0 spans lon[10,11], col1 spans lon[11,12]. Pixel centres: (10.5,46.5)=0.0, (11.5,46.5)=10.0,
    # (10.5,45.5)=20.0, (11.5,45.5)=30.0 - their midpoint (11.0, 46.0) averages to 15.0.
    transform = from_origin(10.0, 47.0, 1.0, 1.0)
    path = tmp_path / "dem.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=2, width=2, count=1, dtype="float32",
        crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data, 1)

    got = dem_sample.sample_points(path, [(11.0, 46.0)])
    assert got[0] == pytest.approx(15.0)


def test_sample_points_preserves_point_order(tmp_path):
    import rasterio
    from rasterio.transform import from_origin

    data = np.full((4, 4), 1000.0, dtype=np.float32)
    transform = from_origin(10.0, 47.0, 0.1, 0.1)
    path = tmp_path / "dem.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=4, width=4, count=1, dtype="float32",
        crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data, 1)

    points = [(10.05, 46.95), (10.35, 46.65), (10.15, 46.85)]
    got = dem_sample.sample_points(path, points)
    assert len(got) == 3
    assert all(v == pytest.approx(1000.0) for v in got)
