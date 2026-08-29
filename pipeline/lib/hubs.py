"""Loads the combined hub set (huts + station/parking/partner access points, binfmt.TYPE_*) and
cell-buckets it against a lib/grid.py Grid - the exact join snap_hubs.py, gather_route_subgraphs.py
and build_hub_edges.py each need before their own per-cell work, previously hand-duplicated in all
three __main__ blocks. One place to extend when a new hub type joins TYPE_HUT/TYPE_STATION/
TYPE_PARKING/TYPE_PARTNER, instead of three near-identical joins silently drifting apart.

Usage: `hubs = load_all_hubs(OSM_DIR)` then `hubs_by_cell = bucket_by_cell(hubs, grid)`."""

import json
from pathlib import Path

from lib import binfmt
from lib.geo import hut_points


def load_all_hubs(osm_dir: Path) -> list:
    """Returns every hub as a flat {id, type, lon, lat, name} dict - `type` is one of
    binfmt.TYPE_*, `id` is the type-scoped id (hut index or start_points.npy's osm_id). `name` is
    only populated for huts (start_points.npy carries no name column); non-hut hubs get "" so
    every dict has the same keys regardless of type."""
    huts_path = osm_dir / "huts.geojson"
    hut_coords_by_id = {i: tuple(c) for i, c in enumerate(hut_points(huts_path))}
    with open(huts_path, encoding="utf-8") as f:
        hut_names_by_id = {
            i: feat["properties"].get("name", "")
            for i, feat in enumerate(json.load(f)["features"])
        }

    start_points = binfmt.load_array(osm_dir / "start_points.npy", mmap=False)
    start_by_id = {}
    for p in start_points:
        start_by_id.setdefault(int(p["type"]), {})[int(p["osm_id"])] = (float(p["lon"]), float(p["lat"]))

    all_hub_coords_by_type = {binfmt.TYPE_HUT: hut_coords_by_id, **start_by_id}
    return [
        {"id": hid, "type": htype, "lon": lon, "lat": lat,
         "name": hut_names_by_id.get(hid, "") if htype == binfmt.TYPE_HUT else ""}
        for htype, coords_by_id in all_hub_coords_by_type.items()
        for hid, (lon, lat) in coords_by_id.items()
    ]


def bucket_by_cell(hubs: list, grid) -> dict:
    """{cell_id: [hub, ...]} - every hub assigned to its lib/grid.py Grid cell by coordinate."""
    by_cell = {}
    for hub in hubs:
        cid = grid.cell_id_for_point(hub["lon"], hub["lat"])
        by_cell.setdefault(cid, []).append(hub)
    return by_cell
