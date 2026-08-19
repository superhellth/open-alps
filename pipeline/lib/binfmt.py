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
    ("u", "i8"), ("v", "i8"), ("dist", "f8"), ("weight", "f8"), ("road_m", "f8"),
    ("sac_rank", "i1"), ("via_ferrata", "bool"),
    ("interior_offset", "i8"), ("interior_count", "i4"), ("edge_id", "i8"),
])
COORD_DTYPE = np.dtype([("lon", "f8"), ("lat", "f8")])

RECORD_DTYPE = np.dtype([
    ("from_id", "i8"), ("to_id", "i8"), ("from_type", "u1"), ("to_type", "u1"),
    ("variant", "u1"), ("distance_m", "f4"), ("road_m", "f4"),
    ("ascent_m", "f4"), ("descent_m", "f4"), ("sac_rank", "i1"), ("via_ferrata", "bool"),
    ("geom_offset", "i8"), ("geom_count", "i4"),
    ("profile_offset", "i8"), ("profile_count", "i4"),
])
PROFILE_DTYPE = np.dtype("f4")

TYPE_HUT = 0
TYPE_STATION = 1
TYPE_PARKING = 2
VARIANT_SHORTEST = 0

UNSET = -1.0  # sentinel for ascent_m/descent_m before add_elevation.py runs


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
