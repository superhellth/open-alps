#!/usr/bin/env python3
"""Packs hut_edges/records.npy + hut_edges/edge_ids.npy (build_hub_edges.py) into the client-
facing hut-edge-ids.bin/.json sibling of hut-edge-payload.bin - the trail-segment identity the
"avoid overlapping tracks" search-time check needs (docs/superpowers/specs/
2026-08-29-avoid-overlapping-tracks-design.md §2). Follows hut-edge-geometry.json's flat-counts-
array manifest shape (build_edge_tiles.py), not hut-edge-payload.json's columnar {dtype,offset}
map - this is a different kind of file (ragged per-row arrays, not fixed-width columns).

Usage: python pipeline/phases/postprocessing/build_edge_ids.py
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import binfmt  # noqa: E402
from lib.pipeline import OSM_DIR  # noqa: E402
from lib.timing import phase  # noqa: E402

K_TRAVERSAL = 8


def pack_edge_ids(records: np.ndarray, flat_edge_ids: np.ndarray) -> tuple:
    """flat_edge_ids: hut_edges/edge_ids.npy as-is - already the per-record sorted-ascending runs
    concatenated in record order (build_hub_edges.py's _write_edge_output), so no re-gathering is
    needed here, just a straight-through byte copy."""
    rows = len(records)
    sorted_bytes_arr = flat_edge_ids.astype("i4").tobytes()
    prefix_bytes_arr = records["prefix_ids"].astype("i4").tobytes()
    suffix_bytes_arr = records["suffix_ids"].astype("i4").tobytes()

    payload = sorted_bytes_arr + prefix_bytes_arr + suffix_bytes_arr
    manifest = {
        "rows": rows,
        "k": K_TRAVERSAL,
        "edge_id_count": records["edge_id_count"].tolist(),
        "prefix_count": records["prefix_count"].tolist(),
        "suffix_count": records["suffix_count"].tolist(),
        "sorted_bytes": len(sorted_bytes_arr),
        "prefix_bytes": len(prefix_bytes_arr),
        "suffix_bytes": len(suffix_bytes_arr),
    }
    return payload, manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--edges-dir", default=str(OSM_DIR / "hut_edges"),
                        help="directory holding hut_edges/ records (build_hub_edges.py's output)")
    parser.add_argument("--out-bin", default=str(OSM_DIR / "hut-edge-ids.bin"),
                        help="path to write the packed hut-edge-id binary")
    parser.add_argument("--out-manifest", default=str(OSM_DIR / "hut-edge-ids.json"),
                        help="path to write the hut-edge-id manifest")
    args = parser.parse_args()

    with phase("build_edge_ids.py", "build_edge_ids"):
        records = binfmt.load_array(Path(args.edges_dir) / "records.npy", mmap=False)
        flat_edge_ids = binfmt.load_array(Path(args.edges_dir) / "edge_ids.npy", mmap=False)
        payload, manifest = pack_edge_ids(records, flat_edge_ids)

        out_bin = Path(args.out_bin)
        out_bin.parent.mkdir(parents=True, exist_ok=True)
        out_bin.write_bytes(payload)
        with open(args.out_manifest, "w") as f:
            json.dump(manifest, f)
        print(f"wrote {out_bin} ({len(payload)} bytes) and {args.out_manifest}", flush=True)
