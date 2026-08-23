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
])
PROFILE_DTYPE = np.dtype("f4")

TYPE_HUT = 0
TYPE_STATION = 1
TYPE_PARKING = 2

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
VARIANT_NAMES = {
    VARIANT_FAST_ANY: "FAST_ANY", VARIANT_FAST_T2: "FAST_T2", VARIANT_FAST_T3: "FAST_T3",
    VARIANT_FAST_T3_UNGRADED: "FAST_T3_UNGRADED",
}

UNSET = -1.0  # sentinel for time_s/ascent_m/descent_m before compute_edge_profiles.py runs


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
