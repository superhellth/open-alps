"""Packs a routed leg/edge (a plain dict with distance/ascent/descent/geometry/base_edge_ids) into
binfmt.RECORD_DTYPE + a flat geometry.npy - the record-packing half of build_hub_edges.py's old
_write_edge_output, extracted so match_tour_edges.py (spec 2026-08-29-official-tours-integration-
design.md §2.6) can emit the exact same on-disk shape without duplicating this logic."""

import hashlib
from pathlib import Path

import numpy as np

from lib import binfmt

K_TRAVERSAL = 8  # spec §4 of the overlapping-tracks design: ~1km at 132m mean base-edge length.


def write_edge_records(records: list, out_dir: Path, write_edge_ids: bool = False) -> None:
    """Packs `records` (each a dict with from_id/to_id/from_type/to_type/variant/distance_m/
    road_m/ascent_m/descent_m/max_ele_m/ungraded_m/inferred_m/snap_m/sac_rank/via_ferrata/
    geometry/base_edge_ids) into out_dir/records.npy + out_dir/geometry.npy, mirroring how
    build_base_graph.py packs contracted-edge interior polylines: one growing geometry array, each
    record's geom_offset/geom_count pointing into it. profile_offset/profile_count stay 0 here -
    the elevation profile pass (build_profiles.py) fills those in a later pass over this same
    records.npy.

    Identical coordinate runs are deduplicated by content hash (blake2b-128, collision probability
    far below floating-point noise in the coordinates themselves) so repeated geometry (e.g. a
    constrained hub-edge variant routing the same polyline as FAST_ANY) doesn't grow the geometry
    file linearly for zero new information.

    write_edge_ids: True to also write out_dir/edge_ids.npy - each record's FULL base-edge-id set,
    deduped and sorted ascending, concatenated across records in record order. RECORD_DTYPE's
    edge_id_offset/edge_id_count slice into it; prefix_ids/suffix_ids (fixed-width K_TRAVERSAL,
    -1-padded) live directly on RECORD_DTYPE."""
    records_arr = np.zeros(len(records), dtype=binfmt.RECORD_DTYPE)
    flat_geometry = []
    flat_edge_ids = []
    cursor = 0
    edge_id_cursor = 0
    seen_geoms = {}
    for i, r in enumerate(records):
        geom = r["geometry"]
        key = hashlib.blake2b(
            np.asarray(geom, dtype=np.float64).tobytes(), digest_size=16
        ).digest()
        offset = seen_geoms.get(key)
        if offset is None:
            offset = cursor
            seen_geoms[key] = offset
            flat_geometry.extend(geom)
            cursor += len(geom)

        if write_edge_ids:
            traversal_ids = r["base_edge_ids"]
            sorted_ids = sorted(set(traversal_ids))
            edge_id_offset = edge_id_cursor
            edge_id_count = len(sorted_ids)
            flat_edge_ids.extend(sorted_ids)
            edge_id_cursor += edge_id_count
            prefix = traversal_ids[:K_TRAVERSAL]
            suffix = list(reversed(traversal_ids[-K_TRAVERSAL:])) if traversal_ids else []
            prefix_count = len(prefix)
            suffix_count = len(suffix)
            prefix_ids = tuple(prefix + [-1] * (K_TRAVERSAL - prefix_count))
            suffix_ids = tuple(suffix + [-1] * (K_TRAVERSAL - suffix_count))
        else:
            edge_id_offset, edge_id_count = 0, 0
            prefix_ids = suffix_ids = (-1,) * K_TRAVERSAL
            prefix_count = suffix_count = 0

        records_arr[i] = (
            r["from_id"], r["to_id"], r["from_type"], r["to_type"], r["variant"],
            r["distance_m"], r["road_m"], r["ascent_m"], r["descent_m"], r["max_ele_m"],
            r["ungraded_m"], r["inferred_m"], r["snap_m"], r["sac_rank"],
            r["via_ferrata"], offset, len(geom), 0, 0,
            edge_id_offset, edge_id_count, prefix_ids, prefix_count, suffix_ids, suffix_count,
        )

    geometry_arr = np.zeros(len(flat_geometry), dtype=binfmt.COORD_DTYPE)
    if flat_geometry:
        geometry_arr["lon"] = [p[0] for p in flat_geometry]
        geometry_arr["lat"] = [p[1] for p in flat_geometry]

    binfmt.save_array(out_dir / "records.npy", records_arr)
    binfmt.save_array(out_dir / "geometry.npy", geometry_arr)
    if write_edge_ids:
        binfmt.save_array(out_dir / "edge_ids.npy", np.array(flat_edge_ids, dtype="i4"))


def fold_endpoint_snaps(path, src_snap, tgt_snap) -> tuple:
    """Prices the hub-to-trail gap at both ends into distance/ascent/descent (spec E3 of
    2026-08-19-pipeline-v2-design.md): a routed path only sums routed edges, so the snap gap
    contributes zero to distance/ascent/descent unless folded in here. Shared by
    build_hub_edges.py's compute_hub_edges_for_cell and match_tour_edges.py's per-leg accumulation
    (spec 2026-08-29-official-tours-integration-design.md §2.6: "apply the SAME endpoint treatment
    build_hub_edges.py applies").

    Departure (src): climbing from the hub up to the trail (hub below its snap point, gap_dz_m < 0)
    is ascent; descending down to the trail (gap_dz_m > 0) is descent. Arrival (tgt): climbing from
    the trail up to the hub (gap_dz_m > 0) is ascent; descending down off the trail to the hub
    (gap_dz_m < 0) is descent. Returns (snap_m, ascent_m, descent_m) - distance_m folding is the
    caller's own `path.distance_m + snap_m`, since callers differ in whether distance_m already
    includes other terms."""
    snap_m = src_snap.gap_m + tgt_snap.gap_m
    ascent_m = path.ascent_m + max(0.0, -src_snap.gap_dz_m) + max(0.0, tgt_snap.gap_dz_m)
    descent_m = path.descent_m + max(0.0, src_snap.gap_dz_m) + max(0.0, -tgt_snap.gap_dz_m)
    return snap_m, ascent_m, descent_m
