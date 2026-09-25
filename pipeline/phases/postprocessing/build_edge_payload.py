#!/usr/bin/env python3
"""Packs hut-edges/records.npy (spec F) into the columnar payload the client loads once, up front.

Measured, not assumed (data/analysis/payload_sizing.json): 3 variants x 6,067 edges x 13 columns =
693 KB raw, 43.4 KB gzipped; a byte-shuffle filter made it WORSE (46.4 KB), so this does not add
one. Both figures cover the scalar columns and are floors - four columns were zeros and the variant copies identical - but even
at 5x this is far under any budget, which is why quantisation is out of scope (spec F's caveat
says measure after packing, and the measurement says the straightforward packing is fine).

Six i2 anchor columns (lib/anchors.py) are appended after the scalar columns; their measured
gzipped growth is recorded in docs/tour-suggestion-payload.md §1.

Geometry is NOT shipped here - it stays in hut-edges.pmtiles, fetched lazily only for tours the
user opens (already how GraphPage.jsx renders edges). No duration column ships either (spec D3):
the client computes DIN itself at load, from distance_m/ascent_m/descent_m.

Columns are laid out per-column (not interleaved) so gzip sees each column's own byte pattern
uninterrupted - that per-column layout is what the measured 43.4 KB figure depends on.

Usage: python pipeline/phases/postprocessing/build_edge_payload.py
"""

import argparse
import gzip
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import binfmt  # noqa: E402
from lib.anchors import edge_anchor_columns  # noqa: E402
from lib.geo import hut_points  # noqa: E402
from lib.pipeline import HUT_EDGES_DIR, RAW_DIR  # noqa: E402
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


def hut_guids(features: list) -> list:
    """Each hut feature's GUID (properties.id), in feature order. The client persists these as the
    stable hut identity, so a feature without one is an error, never an index stand-in."""
    guids = [feat["properties"].get("id") for feat in features]
    missing = [i for i, g in enumerate(guids) if not g]
    if missing:
        raise ValueError(f"huts without a GUID at feature indices {missing[:10]}")
    return guids


def anchor_columns_for_payload(records: np.ndarray, geometry: np.ndarray, hut_lonlat: np.ndarray) -> dict:
    """Anchor columns for every payload row, offset from the row's from_id hut coordinate."""
    ref = hut_lonlat[records["from_id"].astype(np.int64)]
    return edge_anchor_columns(records, geometry, np.arange(len(records)), ref)


def pack_edges(records: np.ndarray, hut_ids: list, anchors: dict | None = None) -> tuple:
    columns = {name: (dtype, records[name]) for name, dtype in COLUMNS}
    for name, values in (anchors or {}).items():
        columns[name] = ("i2", values)
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
    parser.add_argument("--edges-dir", default=str(HUT_EDGES_DIR),
                        help="directory holding hut-edges/ records (build_hub_edges.py's output)")
    parser.add_argument("--huts", default=str(RAW_DIR / "huts.geojson"),
                        help="path to the hut master-data GeoJSON")
    parser.add_argument("--out-bin", default=str(HUT_EDGES_DIR / "payload.bin"),
                        help="path to write the packed hut-edge-payload binary")
    parser.add_argument("--out-manifest", default=str(HUT_EDGES_DIR / "payload.json"),
                        help="path to write the hut-edge-payload manifest")
    args = parser.parse_args()

    with phase("build_edge_payload.py", "build_edge_payload"):
        records = binfmt.load_array(Path(args.edges_dir) / "records.npy", mmap=False)
        # build_hub_edges.py's hut ids are the enumeration index over huts.geojson's own feature
        # order (see its hut_coords_by_id = {i: coord ...}), so the same enumeration recovers each
        # index's real hut id here without re-deriving anything.
        with open(args.huts, encoding="utf-8") as f:
            hut_ids = hut_guids(json.load(f)["features"])

        geometry = binfmt.load_array(Path(args.edges_dir) / "geometry.npy")
        hut_lonlat = np.array(hut_points(args.huts))
        anchors = anchor_columns_for_payload(records, geometry, hut_lonlat)
        plain, _ = pack_edges(records, hut_ids)
        payload, manifest = pack_edges(records, hut_ids, anchors)
        plain_gz = len(gzip.compress(plain, compresslevel=9))
        gz_size = len(gzip.compress(payload, compresslevel=9))
        print(f"hut edges: {len(records):,} rows", flush=True)
        print(f"payload: {len(payload):,} B raw, {gz_size:,} B gzipped", flush=True)
        print(f"anchor growth: {gz_size - plain_gz:+,} B gzipped", flush=True)

        Path(args.out_bin).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out_bin, "wb") as f:
            f.write(payload)
        with open(args.out_manifest, "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        print(f"written {args.out_bin} and {args.out_manifest}", flush=True)
