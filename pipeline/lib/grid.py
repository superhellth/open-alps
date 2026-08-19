"""Row-major grid partitioning a lon/lat bbox into tile_size_km cells, used by
build_hub_edges.py to slice the persisted base graph (lib/binfmt.py) into per-worker regions.
cell_id encoding is fully determined by (bbox, tile_size_km) so it's re-derivable identically at
both build_base_graph.py write time and build_hub_edges.py query time - no lookup table needed."""

import math

KM_PER_DEG_LAT = 111.320


class Grid:
    def __init__(self, bbox: dict, tile_size_km: float):
        self.bbox = bbox
        self.tile_size_km = tile_size_km
        mid_lat = (bbox["minLat"] + bbox["maxLat"]) / 2
        self.km_per_deg_lng = KM_PER_DEG_LAT * math.cos(math.radians(mid_lat))
        width_km = (bbox["maxLng"] - bbox["minLng"]) * self.km_per_deg_lng
        height_km = (bbox["maxLat"] - bbox["minLat"]) * KM_PER_DEG_LAT
        self.n_cols = max(1, math.ceil(width_km / tile_size_km))
        self.n_rows = max(1, math.ceil(height_km / tile_size_km))

    def col_row_for_point(self, lon: float, lat: float) -> tuple[int, int]:
        col = int((lon - self.bbox["minLng"]) * self.km_per_deg_lng / self.tile_size_km)
        row = int((lat - self.bbox["minLat"]) * KM_PER_DEG_LAT / self.tile_size_km)
        col = min(max(col, 0), self.n_cols - 1)
        row = min(max(row, 0), self.n_rows - 1)
        return col, row

    def cell_id_for_point(self, lon: float, lat: float) -> int:
        col, row = self.col_row_for_point(lon, lat)
        return row * self.n_cols + col

    def cell_bounds(self, cell_id: int) -> dict:
        row, col = divmod(cell_id, self.n_cols)
        min_lng = self.bbox["minLng"] + col * self.tile_size_km / self.km_per_deg_lng
        max_lng = self.bbox["minLng"] + (col + 1) * self.tile_size_km / self.km_per_deg_lng
        min_lat = self.bbox["minLat"] + row * self.tile_size_km / KM_PER_DEG_LAT
        max_lat = self.bbox["minLat"] + (row + 1) * self.tile_size_km / KM_PER_DEG_LAT
        return {"minLng": min_lng, "maxLng": max_lng, "minLat": min_lat, "maxLat": max_lat}

    def padded_bounds(self, cell_id: int, buffer_km: float) -> dict:
        b = self.cell_bounds(cell_id)
        dlng = buffer_km / self.km_per_deg_lng
        dlat = buffer_km / KM_PER_DEG_LAT
        return {
            "minLng": b["minLng"] - dlng, "maxLng": b["maxLng"] + dlng,
            "minLat": b["minLat"] - dlat, "maxLat": b["maxLat"] + dlat,
        }

    def cell_ids_overlapping(self, bounds: dict) -> list[int]:
        c0, r0 = self.col_row_for_point(bounds["minLng"], bounds["minLat"])
        c1, r1 = self.col_row_for_point(bounds["maxLng"], bounds["maxLat"])
        return [r * self.n_cols + c for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)]

    def all_cell_ids(self) -> list[int]:
        return list(range(self.n_cols * self.n_rows))
