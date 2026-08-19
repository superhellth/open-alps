import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.grid import Grid  # noqa: E402

BBOX = {"minLng": 10.0, "maxLng": 10.2, "minLat": 47.0, "maxLat": 47.1}


def test_col_row_for_point_at_origin():
    grid = Grid(BBOX, tile_size_km=5.0)
    assert grid.col_row_for_point(BBOX["minLng"], BBOX["minLat"]) == (0, 0)


def test_col_row_for_point_clamped_to_last_cell_at_max_edge():
    grid = Grid(BBOX, tile_size_km=5.0)
    col, row = grid.col_row_for_point(BBOX["maxLng"], BBOX["maxLat"])
    assert col == grid.n_cols - 1
    assert row == grid.n_rows - 1


def test_cell_id_is_row_major():
    grid = Grid(BBOX, tile_size_km=5.0)
    assert grid.n_cols > 1
    # first cell of second row = n_cols
    mid_lat = BBOX["minLat"] + (grid.tile_size_km / 111.320) * 1.001
    assert grid.cell_id_for_point(BBOX["minLng"], mid_lat) == grid.n_cols


def test_cell_bounds_round_trips_cell_id_for_point():
    grid = Grid(BBOX, tile_size_km=5.0)
    for cell_id in grid.all_cell_ids():
        bounds = grid.cell_bounds(cell_id)
        mid_lng = (bounds["minLng"] + bounds["maxLng"]) / 2
        mid_lat = (bounds["minLat"] + bounds["maxLat"]) / 2
        assert grid.cell_id_for_point(mid_lng, mid_lat) == cell_id


def test_padded_bounds_extends_cell_bounds_by_buffer():
    grid = Grid(BBOX, tile_size_km=5.0)
    cell_id = grid.all_cell_ids()[0]
    plain = grid.cell_bounds(cell_id)
    padded = grid.padded_bounds(cell_id, buffer_km=10.0)
    assert padded["minLng"] < plain["minLng"]
    assert padded["maxLng"] > plain["maxLng"]
    assert padded["minLat"] < plain["minLat"]
    assert padded["maxLat"] > plain["maxLat"]


def test_cell_ids_overlapping_covers_padded_region():
    grid = Grid(BBOX, tile_size_km=5.0)
    cell_id = grid.all_cell_ids()[len(grid.all_cell_ids()) // 2]
    padded = grid.padded_bounds(cell_id, buffer_km=grid.tile_size_km)
    overlapping = grid.cell_ids_overlapping(padded)
    assert cell_id in overlapping
    assert len(overlapping) > 1  # buffer equal to tile size must pull in neighbors


def test_single_cell_grid_when_bbox_smaller_than_tile():
    grid = Grid(BBOX, tile_size_km=1000.0)
    assert grid.n_cols == 1
    assert grid.n_rows == 1
    assert grid.all_cell_ids() == [0]
