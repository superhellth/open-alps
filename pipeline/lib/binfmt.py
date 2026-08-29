"""Shared binary array formats for the base graph (build_base_graph.py) and edge outputs
(build_hub_edges.py / add_elevation.py / build_edge_tiles.py). Every array is a plain
structured-dtype numpy array saved via np.save (one file per array) so it's directly
memory-mappable (np.load(path, mmap_mode="r")) with zero new dependencies - no hand-rolled
binary layout needed. Kept as one file per array (not one blob) so a single array can be
re-read/rewritten (e.g. add_elevation.py only rewrites records/profiles) without touching the
rest of the directory."""

import json
from pathlib import Path

import numpy as np

NODE_DTYPE = np.dtype([("lon", "f8"), ("lat", "f8"), ("cell_id", "i4")])
CELL_INDEX_DTYPE = np.dtype([("start_offset", "i8"), ("count", "i4")])
NODE_EDGE_INDEX_DTYPE = np.dtype([("start_offset", "i8"), ("count", "i4")])
EDGE_DTYPE = np.dtype([
    ("u", "i8"), ("v", "i8"), ("dist", "f8"), ("road_m", "f8"),
    ("ungraded_m", "f8"), ("inferred_m", "f8"),
    ("time_s", "f8"), ("ascent_m", "f4"), ("descent_m", "f4"),
    ("sac_rank", "i1"), ("via_ferrata", "bool"), ("constrained_ok", "bool"),
    ("interior_offset", "i8"), ("interior_count", "i4"), ("edge_id", "i8"),
])
COORD_DTYPE = np.dtype([("lon", "f8"), ("lat", "f8")])

RECORD_DTYPE = np.dtype([
    ("from_id", "i8"), ("to_id", "i8"), ("from_type", "u1"), ("to_type", "u1"),
    ("variant", "u1"), ("distance_m", "f4"), ("road_m", "f4"),
    ("ascent_m", "f4"), ("descent_m", "f4"),
    ("max_ele_m", "f4"),   # scalar, so the client never scans a profile to apply an altitude cap
    ("ungraded_m", "f4"),  # zero by construction on every constrained row (spec C4)
    ("inferred_m", "f4"),  # separate from ungraded_m: they support different claims
    ("snap_m", "f4"),      # hub-to-trail gap, both ends; already folded into distance/ascent
    ("sac_rank", "i1"), ("via_ferrata", "bool"),
    ("geom_offset", "i8"), ("geom_count", "i4"),
    ("profile_offset", "i8"), ("profile_count", "i4"),
    # Trail-segment identity for the "avoid overlapping tracks" check (docs/superpowers/specs/
    # 2026-08-29-avoid-overlapping-tracks-design.md). edge_id_offset/count index a per-record
    # ascending-sorted slice of hut_edges/edge_ids.npy (the FULL base-edge-id set, for the
    # non-adjacent-leg overlap check). prefix_ids/suffix_ids are the first/last K_TRAVERSAL ids in
    # TRAVERSAL order (prefix: outward from from_id: suffix: outward from to_id, i.e. the last-K
    # run reversed) - needed because the shared-hub exemption (spec §4) has to walk inward from a
    # specific endpoint, which the sorted set can't do. -1-padded past *_count when a record has
    # fewer than K_TRAVERSAL base edges. Only ever populated for hut_edges records - start_edges
    # keeps these zeroed (spec §1: gated on a parameter, hut-edges-only).
    ("edge_id_offset", "i8"), ("edge_id_count", "i4"),
    ("prefix_ids", "i4", (8,)), ("prefix_count", "u1"),
    ("suffix_ids", "i4", (8,)), ("suffix_count", "u1"),
])
PROFILE_DTYPE = np.dtype("f4")

# Persisted hub->base-graph snap (snap_hubs.py's output, consumed by build_hub_edges.py). Keyed
# by global ids that stay valid across ANY subgraph gather - node/edge local indices (as returned
# by snap_hub_to_subgraph) are only meaningful within the one LocalSubgraph they were computed
# against, but global_node_id (a row index into base_graph/nodes.npy, same as
# LocalSubgraph.global_node_ids) and global_edge_id (EDGE_DTYPE's own "edge_id" field) are stable
# regardless of which cell/buffer gathered them - see lib/hub_snap.py's reconstruct_local_snaps.
SNAP_KIND_NODE = 0
SNAP_KIND_EDGE = 1
HUB_SNAP_DTYPE = np.dtype([
    ("hub_type", "u1"), ("hub_id", "i8"), ("kind", "u1"),
    ("global_node_id", "i8"),  # valid iff kind == SNAP_KIND_NODE, else -1
    ("global_edge_id", "i8"),  # valid iff kind == SNAP_KIND_EDGE, else -1
    ("split_lon", "f8"), ("split_lat", "f8"),
    ("dist_to_u", "f8"), ("dist_to_v", "f8"),
    ("road_m_to_u", "f8"), ("road_m_to_v", "f8"),
    ("ungraded_m_to_u", "f8"), ("ungraded_m_to_v", "f8"),
    ("inferred_m_to_u", "f8"), ("inferred_m_to_v", "f8"),
    ("interior_to_u_offset", "i8"), ("interior_to_u_count", "i4"),
    ("interior_to_v_offset", "i8"), ("interior_to_v_count", "i4"),
    ("gap_m", "f8"), ("gap_dz_m", "f8"),
])

# tour_edges/tour_meta.npy - row-aligned 1:1 with tour_edges/records.npy (NOT folded into
# RECORD_DTYPE itself, spec §2.6: avoids touching the shared dtype every other consumer depends
# on). 25 tours x <=9 legs each fits u1 comfortably.
TOUR_META_DTYPE = np.dtype([("tour_id", "u1"), ("leg_index", "u1")])

TYPE_HUT = 0
TYPE_STATION = 1
TYPE_PARKING = 2
# Bergsteigerdörfer partner businesses / ÖAV Vertragshaus (docs/superpowers/specs/
# 2026-08-28-hut-classification-design.md) - private guesthouses/pensions, not Alpine Club huts.
# Routed one-directionally to huts exactly like TYPE_STATION/TYPE_PARKING (fetch_huts.py splits
# them out of huts.geojson into partner_betriebe.geojson; filter_start_points.py loads that file
# as a third access-point layer). start_points.npy's "osm_id" field holds the ArcGIS layer's
# OBJECTID for this type, not a real OSM id - see filter_start_points.py's _load_arcgis_layer docstring.
TYPE_PARTNER = 3

# Variant grid rows (spec C2/C3). Phase 1 builds the "fastest" objective column only; a ROAD_*
# column appends here if the post-rebuild road-share measurement justifies it.
VARIANT_FAST_ANY = 0
VARIANT_FAST_T2 = 1
VARIANT_FAST_T3 = 2
# Fourth row (spec H fallback), added by Task 11 per docs/superpowers/specs/
# 2026-08-22-tour-suggestion-findings.md: the ungraded connectivity gate measured 31.7%/36.9% of
# huts losing their last T2/T3 connection under the strict ungraded_m==0 rule, both far over the
# 5% threshold that would have kept the grid at three rows.
VARIANT_FAST_T3_UNGRADED = 3
# A tour leg is not a member of the graph.variants search grid (spec 2026-08-29-official-tours-
# integration-design.md §5) - it is the ONE route the AV publishes, nothing to search among - so
# it gets its own sentinel rather than reusing a FAST_* row.
VARIANT_OFFICIAL = 4
VARIANT_NAMES = {
    VARIANT_FAST_ANY: "FAST_ANY", VARIANT_FAST_T2: "FAST_T2", VARIANT_FAST_T3: "FAST_T3",
    VARIANT_FAST_T3_UNGRADED: "FAST_T3_UNGRADED", VARIANT_OFFICIAL: "OFFICIAL",
}

UNSET = -1.0  # sentinel for time_s/ascent_m/descent_m before compute_edge_profiles.py runs

# Split into three independent tracking params (one per dtype each cares about) so bumping one
# doesn't force-rerun tasks that don't touch that dtype - see pipeline/dag/graph_building.py.
EDGE_SCHEMA_VERSION = 2
SNAP_SCHEMA_VERSION = 2
RECORD_SCHEMA_VERSION = 3  # bumped: RECORD_DTYPE gained edge_id_offset/count + prefix/suffix ids


def save_array(path: Path, array: np.ndarray) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, array, allow_pickle=False)


def load_array(path: Path, mmap: bool = True) -> np.ndarray:
    return np.load(path, mmap_mode="r" if mmap else None, allow_pickle=False)


def save_manifest(path: Path, manifest: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def load_manifest(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def ragged_positions(counts: np.ndarray) -> np.ndarray:
    """0-indexed position within each ragged group - e.g. counts=[3,0,2] -> [0,1,2,0,1]. Split out
    from gather_ragged (below) since some callers need true within-group order (e.g.
    build_hub_edges.py's _build_edge_spatial_index reconstructing real polyline point order)
    without needing to gather a values array."""
    counts = np.asarray(counts)
    total = int(counts.sum())
    if total == 0:
        return np.zeros(0, dtype=np.int64)
    return np.arange(total) - np.repeat(np.cumsum(counts) - counts, counts)


def gather_ragged(values: np.ndarray, starts: np.ndarray, counts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Vectorized equivalent of `for i, (s, c) in enumerate(zip(starts, counts)): yield from
    ((i, values[j]) for j in range(s, s + c))` - gathers every group's slice of `values` in one
    pass instead of a per-group Python loop + numpy slice (was the hot path in both
    lib/subgraph.py's incidence closure and build_hub_edges.py's per-edge interior-point
    reconstruction, each doing this once per node/edge in a 60km cell). Returns (gathered_values,
    group_ids) - group_ids[k] says which group gathered_values[k] came from, and within a group
    the original values order is preserved (ragged_positions walks start..start+count-1 in order)."""
    counts = np.asarray(counts)
    total = int(counts.sum())
    if total == 0:
        return values[:0], np.zeros(0, dtype=np.int64)
    group_ids = np.repeat(np.arange(len(counts)), counts)
    flat_idx = np.repeat(np.asarray(starts), counts).astype(np.int64) + ragged_positions(counts)
    return values[flat_idx], group_ids


def build_csr_index(group_ids: np.ndarray, n_groups: int) -> tuple[np.ndarray, np.ndarray]:
    """Sorts positions by group_ids (stable) and returns (order, index) where order is the
    sorted position array and index[g] = (start_offset, count) into `order` for group g. Same
    "sort once, bincount+cumsum for offsets" CSR-adjacency pattern already used in
    build_hut_graph.py's contract_chains - shared here for both nodes-by-cell (cell_index) and
    edges-by-node (node_edge_index) construction."""
    order = np.argsort(group_ids, kind="stable")
    sorted_groups = np.asarray(group_ids)[order]
    counts = np.bincount(sorted_groups, minlength=n_groups)
    offsets = np.zeros(n_groups + 1, dtype=np.int64)
    np.cumsum(counts, out=offsets[1:])
    index = np.zeros(n_groups, dtype=CELL_INDEX_DTYPE)
    index["start_offset"] = offsets[:-1]
    index["count"] = counts
    return order, index


def pack_columns(columns: dict) -> tuple[bytes, dict]:
    """Packs named columns (in insertion order) into one flat buffer, per-column rather than
    interleaved (so a downstream gzip sees each column's own byte pattern uninterrupted), plus a
    manifest recording each column's dtype and byte offset for unpacking. `columns` maps name ->
    (dtype_str, array). Shared by build_approach_table.py and build_edge_payload.py, which both
    ship a small columnar binary this way - kept here rather than duplicated so an offset bug only
    has one place to hide."""
    payload = bytearray()
    column_manifest = {}
    for name, (dtype, array) in columns.items():
        col = np.asarray(array, dtype=dtype)
        column_manifest[name] = {"dtype": dtype, "offset": len(payload)}
        payload.extend(col.tobytes())
    return bytes(payload), column_manifest
