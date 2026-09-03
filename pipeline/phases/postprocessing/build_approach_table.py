#!/usr/bin/env python3
"""Reduces start_edges/records.npy (spec E1/E2) to a shippable approach/exit table.

27,261 parkings and 3,025 stations exist and start_edges/records.npy holds 92,426 records - neither
is shippable or seedable as-is. This writes two things instead:

1. The k-best-per-hut approach table (E1): "k fastest" is wrong on purpose - the fastest edge into
   a hut is systematically the highest, most remote trailhead (forest road, toll road, summer-only
   pass parking), while a driver wants the valley trailhead they can actually reach. Private/
   gated/disused points are hard-dropped upstream, in filter_start_points.py's is_usable() - by
   the time records reach here every candidate is already usable, so selection is purely
   time-ranked, with one slot reserved per source type (parking/station) where both exist, so the
   client's car/transit split has something to work with. maxApproachTime is NOT reintroduced - an
   approach is a full leg, bounded by the same range cap as any hut-hut edge and filtered
   client-side by maxLegTime.

2. The loop-closure reverse index (E2): the client's car mode requires exit start-point == entry
   start-point, and the k~=3 tables of the first and last hut essentially never share a start id -
   a post-filter would annihilate the result set. So every start_edges record whose start point
   appears in ANY hut's retained approach ships too, keyed both hut->starts and start->huts. Size
   is bounded above by the whole start_edges table (~92,426 rows), which cannot break the payload
   budget even unfiltered.

Only variant FAST_ANY records are candidates for the approach table (an approach is a fastest,
unconstrained leg to the hub, not a difficulty-graded one) - the reverse index ships every variant
of a retained start point's records, since closure needs whatever the client already has open.

Usage: python pipeline/phases/postprocessing/build_approach_table.py
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import binfmt  # noqa: E402
from lib import speed  # noqa: E402
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.timing import phase  # noqa: E402

config = load_config()

_SOURCE_TYPE_NAME = {
    binfmt.TYPE_PARKING: "parking", binfmt.TYPE_STATION: "station",
    binfmt.TYPE_PARTNER: "partner_betrieb",
}


def gather_candidates(records: np.ndarray, id_table: dict, variant_ids: set) -> dict:
    by_hut = defaultdict(list)
    for edge_id, r in enumerate(records):
        variant = int(r["variant"])
        if variant not in variant_ids:
            continue
        type_name = _SOURCE_TYPE_NAME.get(int(r["from_type"]))
        if type_name is None:
            continue

        start_id = int(r["from_id"])
        tags = id_table.get(type_name, {}).get(str(start_id), {})
        access = tags.get("access")

        duration_h = speed.din_duration_h(
            float(r["distance_m"]), float(r["ascent_m"]), float(r["descent_m"])
        )
        by_hut[int(r["to_id"])].append({
            "hut_id": int(r["to_id"]),
            "start_id": start_id,
            "source_type": int(r["from_type"]),
            "variant": variant,
            "edge_id": edge_id,
            "access": access,
            "access_unknown": access is None,
            "distance_m": float(r["distance_m"]),
            "ascent_m": float(r["ascent_m"]),
            "descent_m": float(r["descent_m"]),
            "duration_h": duration_h,
        })
    return dict(by_hut)


def bucket_index(duration_h: float, boundaries: list) -> int:
    for i, b in enumerate(boundaries):
        if duration_h <= b:
            return i
    return len(boundaries)


def select_approaches(records: np.ndarray, id_table: dict, duration_buckets: list,
                       variant_ids: set) -> list:
    by_hut = gather_candidates(records, id_table, variant_ids)

    rows = []
    for candidates in by_hut.values():
        by_cell = defaultdict(list)
        for c in candidates:
            cell = (c["source_type"], c["variant"], bucket_index(c["duration_h"], duration_buckets))
            by_cell[cell].append(c)
        for cell_candidates in by_cell.values():
            rows.append(min(cell_candidates, key=lambda c: c["duration_h"]))
    return rows


def build_tables(records: np.ndarray, id_table: dict, duration_buckets: list,
                  variant_ids: set) -> tuple:
    approaches = select_approaches(records, id_table, duration_buckets, variant_ids)
    retained_start_ids = {row["start_id"] for row in approaches}

    hut_to_starts = defaultdict(list)
    start_to_huts = defaultdict(list)
    for edge_id, r in enumerate(records):
        type_name = _SOURCE_TYPE_NAME.get(int(r["from_type"]))
        if type_name is None:
            continue
        start_id = int(r["from_id"])
        if start_id not in retained_start_ids:
            continue
        hut_id = int(r["to_id"])
        row = {
            "hut_id": hut_id, "start_id": start_id, "source_type": int(r["from_type"]),
            "edge_id": edge_id,
            "variant": int(r["variant"]), "distance_m": float(r["distance_m"]),
            "ascent_m": float(r["ascent_m"]), "descent_m": float(r["descent_m"]),
        }
        hut_to_starts[hut_id].append(row)
        start_to_huts[start_id].append(row)

    index = {"hut_to_starts": dict(hut_to_starts), "start_to_huts": dict(start_to_huts)}
    return approaches, index


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--edges-dir", default=str(OSM_DIR / "start_edges"),
                        help="directory holding start_edges/ records (build_hub_edges.py's output)")
    parser.add_argument("--id-table", default=str(OSM_DIR / "start_points_id_table.json"),
                        help="path to the start-point id table (build_edge_ids.py's output)")
    parser.add_argument("--k", type=int, default=config["approach"]["k"],
                        help="best approach edges retained per hut (see pipeline.config.json's approach.k)")
    parser.add_argument("--out-bin", default=str(OSM_DIR / "approaches.bin"),
                        help="path to write the packed approach-table binary")
    parser.add_argument("--out-manifest", default=str(OSM_DIR / "approaches.json"),
                        help="path to write the approach-table manifest")
    args = parser.parse_args()

    with phase("build_approach_table.py", "build_approach_table"):
        records = binfmt.load_array(Path(args.edges_dir) / "records.npy", mmap=False)
        with open(args.id_table, encoding="utf-8") as f:
            id_table = json.load(f)

        approaches, index = build_tables(records, id_table, args.k)
        print(f"start_edges records: {len(records):,}", flush=True)
        print(f"approach rows (k={args.k}): {len(approaches):,}", flush=True)
        print(f"reverse index: {len(index['hut_to_starts']):,} huts, "
              f"{len(index['start_to_huts']):,} start points, "
              f"{sum(len(v) for v in index['start_to_huts'].values()):,} rows", flush=True)

        columns = {
            "hut_id": ("u2", np.array([r["hut_id"] for r in approaches], dtype="u2")),
            "start_id": ("u8", np.array([r["start_id"] for r in approaches], dtype="u8")),
            "source_type": ("u1", np.array([r["source_type"] for r in approaches], dtype="u1")),
            "edge_id": ("u4", np.array([r["edge_id"] for r in approaches], dtype="u4")),
            "access_unknown": (
                "u1", np.array([r["access_unknown"] for r in approaches], dtype="u1")
            ),
            "distance_m": ("f4", np.array([r["distance_m"] for r in approaches], dtype="f4")),
            "ascent_m": ("f4", np.array([r["ascent_m"] for r in approaches], dtype="f4")),
            "descent_m": ("f4", np.array([r["descent_m"] for r in approaches], dtype="f4")),
        }
        payload, column_manifest = binfmt.pack_columns(columns)
        Path(args.out_bin).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out_bin, "wb") as f:
            f.write(payload)

        # access values are strings (e.g. "customers", "permit") a UI can surface verbatim -
        # interned into a small table rather than packed as a fixed-width binary column, since
        # the row count (~7k) makes JSON cheap and the value set open-ended (any OSM access= tag).
        access_values = [r["access"] for r in approaches]
        manifest = {
            "rows": len(approaches),
            "columns": column_manifest,
            "access_values": access_values,
            "reverse_index": index,
        }
        with open(args.out_manifest, "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        print(f"written {args.out_bin} and {args.out_manifest}", flush=True)
