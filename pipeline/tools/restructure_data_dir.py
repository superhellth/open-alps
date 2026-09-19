#!/usr/bin/env python3
"""One-shot migration of data/ from the flat data/osm + data/dem layout to data/raw + data/build
(spec docs/superpowers/specs/2026-09-03-data-directory-restructure-design.md).

Moves files with os.rename (same filesystem, so mtime/size/content - and therefore doit's stored
[mtime, size, md5] per path - are preserved), deletes orphaned files, and rewrites the path strings
in data/.doit.json.db so doit does not consider any task stale. Idempotent: files already moved are
skipped and an already-rewritten db is left as it is.

Usage: python tools/restructure_data_dir.py [--dry-run]     (run from pipeline/)
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.pipeline import DATA_DIR  # noqa: E402

DB_PREFIX = "../data/"  # doit db keys are relative to pipeline/ (lib/doit_support.py's rel())
BACKUP_SUFFIX = ".pre-restructure"

# moved as whole directories, contents unchanged
DIR_MOVES = {"dem": "raw/dem", "osm/route_subgraphs": "build/route-subgraphs"}

# tasks that no longer exist in dodo.py; their db entries are inert
DROPPED_TASKS = ("fetch_tour_oa_geometry", "build_tour_edge_payload")

DELETE = [
    "osm/austria-parking.osm.pbf", "osm/austria-stations.osm.pbf",
    "osm/bayern-parking.osm.pbf", "osm/bayern-stations.osm.pbf",
    "osm/tour-fetch-gaps.json",
    "osm/tour-edge-payload.bin", "osm/tour-edge-payload.json",
    "osm/tour_edges/tour_meta.npy", "osm/tour_edges/edge_ids.npy",
]


def _hyphenated(old_dir: str, new_dir: str, names: list) -> dict:
    return {f"osm/{old_dir}/{n}": f"build/{new_dir}/{n.replace('_', '-')}" for n in names}


def _edge_set_outputs(old_prefix: str, new_dir: str, kinds: list) -> dict:
    """old_prefix e.g. 'hut-edge' -> osm/hut-edges.pmtiles, osm/hut-edge-<kind>.<ext> ..."""
    moves = {f"osm/{old_prefix}s.pmtiles": f"build/{new_dir}/edges.pmtiles"}
    for kind in kinds:
        moves[f"osm/{old_prefix}-{kind}"] = f"build/{new_dir}/{kind}"
    return moves


def _build_exact_moves() -> dict:
    moves = {}
    for region in ("austria", "bayern"):
        moves[f"osm/raw/{region}-latest.osm.pbf"] = f"raw/osm/{region}-latest.osm.pbf"
        moves[f"osm/raw/{region}.poly"] = f"raw/osm/{region}.poly"
        moves[f"osm/{region}-trails.osm.pbf"] = f"build/trails/{region}-trails.osm.pbf"
    for name in ("huts", "partner_betriebe", "stations", "parking"):
        moves[f"osm/{name}.geojson"] = f"raw/{name}.geojson"
    moves.update({
        "osm/trails.osm.pbf": "build/trails/trails.osm.pbf",
        "osm/verify_trails.stamp": "build/trails/verify-trails.stamp",
        "osm/trails.pmtiles": "build/trails/trails.pmtiles",
        "osm/hub_range.geojson": "build/hub-range/hub-range.geojson",
        "osm/start_points.npy": "build/start-points/start-points.npy",
        "osm/start_points_id_table.json": "build/start-points/start-points-id-table.json",
        "osm/hub_snaps.npy": "build/snapping/hub-snaps.npy",
        "osm/hub_snap_interior.npy": "build/snapping/hub-snap-interior.npy",
        "osm/unsnapped_huts.json": "build/snapping/unsnapped-huts.json",
        "osm/access_distances.npy": "build/access-edges/access-distances.npy",
        "osm/selected_access_pairs.npy": "build/access-edges/selected-access-pairs.npy",
        "osm/approaches.bin": "build/start-edges/approaches.bin",
        "osm/approaches.json": "build/start-edges/approaches.json",
        "osm/tours.json": "build/tour-edges/tours.json",
        "osm/tour-match-gaps.json": "build/tour-edges/tour-match-gaps.json",
        "osm/hubs.json": "build/tour-edges/hubs.json",
    })
    moves.update(_hyphenated("base_graph", "base-graph", [
        "manifest.json", "nodes.npy", "edges.npy", "cell_index.npy", "interior.npy",
        "interior_ele.npy", "node_ele.npy", "node_edge_ids.npy", "node_edge_index.npy",
        "edge_profiles.stamp",
    ]))
    moves.update(_hyphenated("hut_edges", "hut-edges",
                             ["records.npy", "profiles.npy", "geometry.npy", "edge_ids.npy"]))
    moves.update(_hyphenated("start_edges", "start-edges",
                             ["records.npy", "profiles.npy", "geometry.npy", "edge_ids.npy"]))
    moves.update(_hyphenated("tour_edges", "tour-edges",
                             ["records.npy", "profiles.npy", "geometry.npy"]))
    both = ["geometry.bin", "geometry.json", "elevation.bin", "elevation.json"]
    moves.update(_edge_set_outputs("hut-edge", "hut-edges", ["stats.json", *both,
                                   "payload.bin", "payload.json", "ids.bin", "ids.json"]))
    moves.update(_edge_set_outputs("start-edge", "start-edges", ["stats.json", *both,
                                   "ids.bin", "ids.json"]))
    moves.update(_edge_set_outputs("tour-edge", "tour-edges", ["stats.json", *both]))
    return moves


EXACT_MOVES = _build_exact_moves()


def map_path(rel: str):
    """New path (relative to data/) for an old one, or None if this script does not know it."""
    if rel in EXACT_MOVES:
        return EXACT_MOVES[rel]
    for old, new in DIR_MOVES.items():
        if rel == old or rel.startswith(old + "/"):
            return new + rel[len(old):]
    return None


def rewrite_db(db: dict):
    """Returns (new_db, strays). Keys and `deps:` entries under ../data/{osm,dem}/ are remapped;
    their [mtime, size, md5] values are kept as they are. strays = old-layout paths this script
    cannot place."""
    strays = []

    def remap(key: str):
        if not key.startswith(DB_PREFIX):
            return key
        rel = key[len(DB_PREFIX):]
        if rel in DELETE:
            return None
        new = map_path(rel)
        if new is None:
            if rel.startswith(("osm/", "dem/")):
                strays.append(key)
            return key
        return DB_PREFIX + new

    new_db = {}
    for task, entry in db.items():
        if task in DROPPED_TASKS:
            continue
        new_entry = {}
        for key, value in entry.items():
            if key == "deps:":
                new_entry[key] = [n for n in (remap(d) for d in value) if n is not None]
                continue
            new_key = remap(key)
            if new_key is not None:
                new_entry[new_key] = value
        new_db[task] = new_entry
    return new_db, strays


def _is_under_dir_move(rel: str) -> bool:
    return any(rel == old or rel.startswith(old + "/") for old in DIR_MOVES)


def _plan_files(data_dir: Path):
    """(moves, deletes, strays) for files still under data/osm."""
    moves, deletes, strays = [], [], []
    osm = data_dir / "osm"
    if not osm.exists():
        return moves, deletes, strays
    for root, dirs, files in os.walk(osm):
        root_path = Path(root)
        dirs[:] = sorted(d for d in dirs
                         if not _is_under_dir_move((root_path / d).relative_to(data_dir).as_posix()))
        for name in sorted(files):
            rel = (root_path / name).relative_to(data_dir).as_posix()
            if rel in DELETE:
                deletes.append(rel)
            elif rel in EXACT_MOVES:
                moves.append((rel, EXACT_MOVES[rel]))
            else:
                strays.append(rel)
    return moves, deletes, strays


def _plan_dirs(data_dir: Path):
    return [(old, new) for old, new in DIR_MOVES.items() if (data_dir / old).exists()]


def run(data_dir: Path, db_path: Path, dry_run: bool = False) -> None:
    data_dir, db_path = Path(data_dir), Path(db_path)
    moves, deletes, strays = _plan_files(data_dir)
    dir_moves = _plan_dirs(data_dir)

    new_db = None
    if db_path.exists():
        with open(db_path, encoding="utf-8") as f:
            new_db, db_strays = rewrite_db(json.load(f))
        strays += [f"(db) {s}" for s in db_strays]

    collisions = [new for _, new in [*moves, *dir_moves] if (data_dir / new).exists()]
    if strays or collisions:
        lines = []
        if strays:
            lines.append("paths this script cannot place:\n  " + "\n  ".join(strays))
        if collisions:
            lines.append("destinations that already exist:\n  " + "\n  ".join(collisions))
        raise SystemExit("aborting, nothing was changed.\n" + "\n".join(lines))

    print(f"{len(dir_moves)} directory moves, {len(moves)} file moves, {len(deletes)} deletes")
    for old, new in [*dir_moves, *moves]:
        print(f"  move   {old} -> {new}")
    for rel in deletes:
        print(f"  delete {rel}")
    if dry_run:
        print("dry run: nothing changed")
        return

    if db_path.exists():
        backup = db_path.with_name(db_path.name + BACKUP_SUFFIX)
        if not backup.exists():
            shutil.copy2(db_path, backup)

    for old, new in [*dir_moves, *moves]:
        dest = data_dir / new
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.rename(data_dir / old, dest)
    for rel in deletes:
        (data_dir / rel).unlink()

    if new_db is not None:
        tmp = db_path.with_name(db_path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(new_db, f)
        os.replace(tmp, db_path)

    osm = data_dir / "osm"
    if osm.exists():
        for root, _dirs, _files in os.walk(osm, topdown=False):
            if not os.listdir(root):
                os.rmdir(root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--db", type=Path, default=None,
                        help="doit dep file (default: <data-dir>/.doit.json.db)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.data_dir, args.db or args.data_dir / ".doit.json.db", dry_run=args.dry_run)
