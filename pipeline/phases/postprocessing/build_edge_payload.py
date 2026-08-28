#!/usr/bin/env python3
"""Packs hut_edges/records.npy (spec F) into the columnar payload the client loads once, up front.

Measured, not assumed (data/analysis/payload_sizing.json): 3 variants x 6,067 edges x 13 columns =
693 KB raw, 43.4 KB gzipped; a byte-shuffle filter made it WORSE (46.4 KB), so this does not add
one. Both figures are floors - four columns were zeros and the variant copies identical - but even
at 5x this is far under any budget, which is why quantisation is out of scope (spec F's caveat
says measure after packing, and the measurement says the straightforward packing is fine).

Geometry is NOT shipped here - it stays in hut-edges.pmtiles, fetched lazily only for tours the
user opens (already how GraphPage.jsx renders edges). No duration column ships either (spec D3):
the client computes DIN itself at load, from distance_m/ascent_m/descent_m.

Columns are laid out per-column (not interleaved) so gzip sees each column's own byte pattern
uninterrupted - that per-column layout is what the measured 43.4 KB figure depends on.

Usage: python pipeline/phases/postprocessing/build_edge_payload.py
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import binfmt  # noqa: E402
from lib.geo import hut_points  # noqa: E402
from lib.pipeline import OSM_DIR  # noqa: E402
from lib.timing import phase  # noqa: E402

# (column name, packed dtype) - hut ids narrow i8 -> u2 (huts.geojson is well under 65536 huts);
# f4/i1/u1 for the rest, same narrowing RECORD_DTYPE itself doesn't do since it's an internal
# working format shared with add_elevation/build_hub_edges, not the shipped one.
COLUMNS = [
    ("from_id", "u2"), ("to_id", "u2"), ("variant", "u1"),
    ("distance_m", "f4"), ("ascent_m", "f4"), ("descent_m", "f4"),
    ("max_ele_m", "f4"), ("sac_rank", "i1"), ("via_ferrata", "u1"),
    ("road_m", "f4"), ("ungraded_m", "f4"), ("inferred_m", "f4"), ("snap_m", "f4"),
]


def pack_edges(records: np.ndarray, hut_ids: list) -> tuple:
    columns = {name: (dtype, records[name]) for name, dtype in COLUMNS}
    payload, column_manifest = binfmt.pack_columns(columns)
    manifest = {
        "rows": len(records),
        "columns": column_manifest,
        "variants": binfmt.VARIANT_NAMES,
        "hut_ids": hut_ids,
    }
    return payload, manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--edges-dir", default=str(OSM_DIR / "hut_edges"))
    parser.add_argument("--huts", default=str(OSM_DIR / "huts.geojson"))
    parser.add_argument("--out-bin", default=str(OSM_DIR / "hut-edge-payload.bin"))
    parser.add_argument("--out-manifest", default=str(OSM_DIR / "hut-edge-payload.json"))
    args = parser.parse_args()

    with phase("build_edge_payload.py", "build_edge_payload"):
        records = binfmt.load_array(Path(args.edges_dir) / "records.npy", mmap=False)
        # build_hub_edges.py's hut ids are the enumeration index over huts.geojson's own feature
        # order (see its hut_coords_by_id = {i: coord ...}), so the same enumeration recovers each
        # index's real hut id here without re-deriving anything.
        with open(args.huts, encoding="utf-8") as f:
            hut_ids = [
                feat["properties"].get("id", i)
                for i, feat in enumerate(json.load(f)["features"])
            ]

        payload, manifest = pack_edges(records, hut_ids)

        import gzip
        gz_size = len(gzip.compress(payload, compresslevel=9))
        print(f"hut edges: {len(records):,} rows", flush=True)
        print(f"payload: {len(payload):,} B raw, {gz_size:,} B gzipped", flush=True)

        Path(args.out_bin).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out_bin, "wb") as f:
            f.write(payload)
        with open(args.out_manifest, "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        print(f"written {args.out_bin} and {args.out_manifest}", flush=True)
