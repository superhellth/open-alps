"""Loads the combined hub set (huts + station/parking/partner access points, binfmt.TYPE_*) and
cell-buckets it against a lib/grid.py Grid - the exact join snap_hubs.py, gather_route_subgraphs.py
and build_hub_edges.py each need before their own per-cell work, previously hand-duplicated in all
three __main__ blocks. One place to extend when a new hub type joins TYPE_HUT/TYPE_STATION/
TYPE_PARKING/TYPE_PARTNER, instead of three near-identical joins silently drifting apart.

Usage: `hubs = load_all_hubs(OSM_DIR)` then `hubs_by_cell = bucket_by_cell(hubs, grid)`."""

import json
from pathlib import Path

from lib import binfmt
from lib.geo import haversine_m as _haversine_m
from lib.geo import hut_points

HUB_TYPE_JSON_NAMES = {
    binfmt.TYPE_HUT: "hut", binfmt.TYPE_STATION: "station",
    binfmt.TYPE_PARKING: "parking", binfmt.TYPE_PARTNER: "partner_betrieb",
}


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


def nearest_hub_to_point(hubs: list, point: tuple, max_snap_m: float) -> tuple:
    """Nearest hub to `point` from the combined hub set (spec 2026-08-30-tour-folder-ingestion-
    design.md §2's endpoint-snapping table) - the transpose of the deleted lib/tour_geometry.py's
    assign_hut_position (nearest *hub* to an endpoint, not nearest *chain point* to a hut).
    Preferring TYPE_HUT over any other type when both sit within max_snap_m, so a leg ending at a
    hut beside a car park resolves to the hut.

    Returns (chosen, nearest, nearest_dist_m). `nearest`/`nearest_dist_m` describe the single
    closest candidate of ANY type, regardless of range or whether it was chosen - needed so a
    leg_endpoint_unsnapped gap can report what the nearest miss was (spec §5), which
    assign_hut_position could not (it discarded the distance on failure). `chosen` is None when
    nothing is within max_snap_m."""
    if not hubs:
        return None, None, float("inf")

    dists = [(_haversine_m(point[0], point[1], h["lon"], h["lat"]), h) for h in hubs]
    nearest_dist, nearest = min(dists, key=lambda t: t[0])

    in_range = [(d, h) for d, h in dists if d <= max_snap_m]
    if not in_range:
        return None, nearest, nearest_dist

    huts_in_range = [(d, h) for d, h in in_range if h["type"] == binfmt.TYPE_HUT]
    pool = huts_in_range if huts_in_range else in_range
    _, chosen = min(pool, key=lambda t: t[0])
    return chosen, nearest, nearest_dist
