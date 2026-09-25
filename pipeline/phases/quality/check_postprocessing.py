#!/usr/bin/env python3
"""Read-only checks over phases/postprocessing/ output (spec docs/superpowers/specs/
2026-09-02-data-quality-monitoring-design.md §4.4): approach-table coverage, shipped
manifest/array agreement, shipped-geometry straightness, and public-copy freshness. Never
mutates its inputs; always exits 0 (spec §3).

Usage: python pipeline/phases/quality/check_postprocessing.py
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import binfmt  # noqa: E402
from lib.anchors import ANCHOR_FRACTIONS, decode_row, distance_to_polyline_m  # noqa: E402
from lib.geo import haversine_m, hut_points  # noqa: E402
from lib.pipeline import (  # noqa: E402
    BUILD_DIR, EDGE_LAYER_DIRNAMES, PUBLIC_DATA_DIR, QUALITY_DIR, RAW_DIR, load_config,
)  # noqa: E402
from lib.quality_report import build_check, write_report  # noqa: E402
from lib.timing import phase  # noqa: E402
from postprocessing.build_approach_table import gather_candidates, parse_variant_names  # noqa: E402

SCRIPT_NAME = "check_postprocessing.py"

_SOURCE_TYPE_NAME = {
    binfmt.TYPE_PARKING: "parking", binfmt.TYPE_STATION: "station",
    binfmt.TYPE_PARTNER: "partner_betrieb",
}

EDGE_PAYLOAD_LAYERS = [
    ("hut_edges", "payload.json", "geometry.json", "geometry.bin"),
    ("start_edges", None, "geometry.json", "geometry.bin"),
    ("tour_edges", None, "geometry.json", "geometry.bin"),
]


ANCHOR_SAMPLE_ROWS = 500


def check_anchors_on_path(layer_name: str, anchors: list, polylines: list, tolerance_m: float,
                          max_flagged: int) -> dict:
    """Every sampled decoded anchor lies within tolerance_m of its edge's full-resolution polyline.
    anchors[i] is (k, 2) lon/lat, polylines[i] is (n, 2) lon/lat."""
    flagged = []
    for i, (points, poly) in enumerate(zip(anchors, polylines)):
        for k, (lon, lat) in enumerate(points):
            d = distance_to_polyline_m(lon, lat, poly)
            if d > tolerance_m:
                flagged.append({"layer": layer_name, "sample": i, "anchor": k, "distance_m": d})
    return build_check(
        f"anchors_on_path_{layer_name}", {"tolerance_m": tolerance_m}, checked=len(anchors),
        flagged_rows=flagged, baseline=0, max_flagged_rows=max_flagged,
        sort_key=lambda r: r["distance_m"],
    )


def _polyline(records, geometry, row):
    off, cnt = int(records[row]["geom_offset"]), int(records[row]["geom_count"])
    piece = geometry[off:off + cnt]
    return np.column_stack([piece["lon"], piece["lat"]])


def _sample_rows(n_rows: int) -> range:
    return range(0, n_rows, max(1, n_rows // ANCHOR_SAMPLE_ROWS))


def _present_fractions(columns: dict) -> tuple:
    return tuple(f for f in ANCHOR_FRACTIONS if f"a{int(round(f * 100))}_dlat" in columns)


def check_approach_coverage(candidates_by_hut: dict, approach_columns: dict, n_huts: int,
                             max_flagged: int) -> dict:
    """§4.4.1: flag any hut with zero approach rows, and any hut missing a source type that was
    available among its candidates but didn't survive selection. `approach_columns` holds the
    already-unpacked approaches.bin arrays: {"hut_id": u2[], "source_type": u1[]}."""
    selected_by_hut = {}
    for hut_id, source_type in zip(approach_columns["hut_id"].tolist(), approach_columns["source_type"].tolist()):
        selected_by_hut.setdefault(int(hut_id), set()).add(int(source_type))

    flagged = []
    for hut_id in range(n_huts):
        candidates = candidates_by_hut.get(hut_id)
        if not candidates:
            continue  # no candidates at all is not this check's concern - only huts WITH candidates
        selected_types = selected_by_hut.get(hut_id, set())
        if not selected_types:
            flagged.append({"hut_id": hut_id, "reason": "zero_approach_rows"})
            continue
        available_types = {int(c["source_type"]) for c in candidates}
        for source_type in available_types - selected_types:
            flagged.append({
                "hut_id": hut_id, "reason": "dropped_source_type",
                "source_type": _SOURCE_TYPE_NAME.get(source_type, str(source_type)),
            })

    return build_check(
        "approach_coverage", {}, checked=n_huts, flagged_rows=flagged, baseline=233 + 160,
        max_flagged_rows=max_flagged,
    )


def check_manifest_agreement(layer_name: str, n_records: int, payload_rows: int,
                              point_counts: list, geometry_byte_len: int, max_flagged: int) -> dict:
    """§4.4.2: records.npy row count == <layer>-payload.json's rows == len(point_counts), and
    geometry.bin byte length == 8 * sum(point_counts) (build_edge_tiles.py's build_stats packs the
    simplified geometry as an (n, 2) f4 array - 4 bytes/coord * 2 coords = 8 bytes/point - mirrored
    here verbatim rather than re-derived)."""
    flagged = []
    if payload_rows is not None and n_records != payload_rows:
        flagged.append({
            "layer": layer_name, "reason": "payload_rows_mismatch",
            "records_rows": n_records, "payload_rows": payload_rows,
        })
    if n_records != len(point_counts):
        flagged.append({
            "layer": layer_name, "reason": "geometry_manifest_row_mismatch",
            "records_rows": n_records, "geometry_manifest_rows": len(point_counts),
        })
    expected_bytes = 8 * sum(point_counts)
    if geometry_byte_len != expected_bytes:
        flagged.append({
            "layer": layer_name, "reason": "geometry_byte_length_mismatch",
            "geometry_byte_len": geometry_byte_len, "expected_bytes": expected_bytes,
        })
    return build_check(
        f"manifest_agreement_{layer_name}", {}, checked=n_records, flagged_rows=flagged,
        baseline=0, max_flagged_rows=max_flagged,
    )


def check_tours_json_geometry(tours: list, point_counts: list, max_flagged: int) -> dict:
    """tours.json's matched legs (edgeId != null) equal the tour geometry manifest's row count."""
    matched = sum(1 for t in tours for leg in t["legs"] if leg.get("edgeId") is not None)
    flagged = [] if matched == len(point_counts) else [{
        "reason": "matched_legs_vs_geometry_rows", "matched_legs": matched,
        "geometry_rows": len(point_counts)}]
    return build_check("tours_json_geometry", {}, checked=matched, flagged_rows=flagged,
                       baseline=0, max_flagged_rows=max_flagged)


def check_shipped_straightness(layer_name: str, point_counts: list, geometry_points: list,
                                lengths_m: list, min_length_m: float, straightness_threshold: float,
                                max_points: int, max_flagged: int) -> dict:
    """§4.4.3: over the SIMPLIFIED shipped geometry (build_edge_tiles.py's output, not the raw
    hut-edges/geometry.npy), flag edges >= min_length_m with straightness >= straightness_threshold
    and fewer than max_points points. straightness = endpoint-to-endpoint distance / edge length."""
    flagged = []
    for i in range(len(point_counts)):
        length_m = lengths_m[i]
        if length_m < min_length_m:
            continue
        points = geometry_points[i]
        if len(points) < 2:
            continue
        end_to_end_m = haversine_m(points[0][0], points[0][1], points[-1][0], points[-1][1])
        straightness = end_to_end_m / length_m if length_m > 0 else 0.0
        if straightness >= straightness_threshold and point_counts[i] < max_points:
            flagged.append({
                "layer": layer_name, "row": i, "length_m": length_m, "straightness": straightness,
                "point_count": point_counts[i],
            })
    return build_check(
        f"shipped_straightness_{layer_name}",
        {"min_length_m": min_length_m, "straightness_threshold": straightness_threshold,
         "max_points": max_points},
        checked=len(point_counts), flagged_rows=flagged, baseline=4 if layer_name == "hut_edges" else 10,
        max_flagged_rows=max_flagged, sort_key=lambda r: r["straightness"],
    )


def check_public_copy_freshness(public_files: list, public_dir: Path, max_flagged: int) -> dict:
    """§4.4.4: every public file present in huts/public/data/ and byte-identical (via hash, not a
    full diff) to its source in data/. public_files: (source path, public file name) pairs."""
    flagged = []
    for src, name in public_files:
        src = Path(src)
        dst = public_dir / name
        if not src.exists():
            continue  # not built yet - not this check's concern (copy_public_data already skips it)
        if not dst.exists():
            flagged.append({"file": name, "reason": "missing_in_public"})
            continue
        src_hash = hashlib.sha256(src.read_bytes()).hexdigest()
        dst_hash = hashlib.sha256(dst.read_bytes()).hexdigest()
        if src_hash != dst_hash:
            flagged.append({"file": name, "reason": "content_mismatch"})
    return build_check(
        "public_copy_freshness", {}, checked=len(public_files), flagged_rows=flagged, baseline=0,
        max_flagged_rows=max_flagged,
    )


def _unpack_columns(payload: bytes, manifest: dict, rows: int) -> dict:
    out = {}
    for name, col in manifest.items():
        out[name] = np.frombuffer(payload, dtype=col["dtype"], count=rows, offset=col["offset"])
    return out


def main(argv=None):
    config = load_config()
    q = config.get("quality", {})
    max_flagged_default = q.get("maxFlaggedRows", 500)
    pp_cfg = q.get("postprocessing", {})

    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default=str(RAW_DIR))
    parser.add_argument("--build-dir", default=str(BUILD_DIR))
    parser.add_argument("--public-dir", default=str(PUBLIC_DATA_DIR))
    parser.add_argument("--out", default=str(QUALITY_DIR / "postprocessing.json"))
    parser.add_argument("--max-flagged-rows", type=int, default=max_flagged_default)
    parser.add_argument("--min-length-m", type=float, default=pp_cfg.get("minLengthM", 300))
    parser.add_argument("--straightness-threshold", type=float,
                         default=pp_cfg.get("straightnessThreshold", 0.97))
    parser.add_argument("--anchor-tolerance-m", type=float, default=pp_cfg.get("anchorToleranceM", 25.0))
    parser.add_argument("--max-points-for-straightness-flag", type=int,
                         default=pp_cfg.get("maxPointsForStraightnessFlag", 4))
    args = parser.parse_args(argv)

    raw_dir, build_dir, public_dir = Path(args.raw_dir), Path(args.build_dir), Path(args.public_dir)

    with phase(SCRIPT_NAME, "check_postprocessing"):
        checks = []

        with open(raw_dir / "huts.geojson", encoding="utf-8") as f:
            n_huts = len(json.load(f)["features"])
        start_records = binfmt.load_array(build_dir / "start-edges" / "records.npy", mmap=False)
        with open(build_dir / "start-points" / "start-points-id-table.json", encoding="utf-8") as f:
            id_table = json.load(f)
        variant_ids = parse_variant_names(",".join(config["approach"]["variants"]))
        candidates_by_hut = gather_candidates(start_records, id_table, variant_ids)

        with open(build_dir / "start-edges" / "approaches.json", encoding="utf-8") as f:
            approach_manifest = json.load(f)
        with open(build_dir / "start-edges" / "approaches.bin", "rb") as f:
            approach_payload = f.read()
        approach_columns = _unpack_columns(approach_payload, approach_manifest["columns"],
                                            approach_manifest["rows"])
        c = check_approach_coverage(candidates_by_hut, approach_columns, n_huts, args.max_flagged_rows)
        print(f"approach_coverage: {c['summary']['flagged']:,} / {c['summary']['checked']:,} flagged", flush=True)
        checks.append(c)

        huts_lonlat = np.array(hut_points(raw_dir / "huts.geojson"))

        def report_anchors(layer_name, anchors, polylines):
            c = check_anchors_on_path(layer_name, anchors, polylines, args.anchor_tolerance_m,
                                      args.max_flagged_rows)
            print(f"anchors_on_path[{layer_name}]: {c['summary']['flagged']:,} / "
                  f"{c['summary']['checked']:,} flagged", flush=True)
            checks.append(c)

        hut_dir = build_dir / "hut-edges"
        if (hut_dir / "payload.json").exists() and (hut_dir / "payload.bin").exists() \
                and (hut_dir / "geometry.npy").exists():
            manifest = json.loads((hut_dir / "payload.json").read_text(encoding="utf-8"))
            cols = _unpack_columns((hut_dir / "payload.bin").read_bytes(), manifest["columns"], manifest["rows"])
            if "a50_dlat" in cols:
                recs = binfmt.load_array(hut_dir / "records.npy", mmap=False)
                geom = binfmt.load_array(hut_dir / "geometry.npy", mmap=False)
                rows = _sample_rows(manifest["rows"])
                fractions = _present_fractions(cols)
                report_anchors(
                    "hut_edges",
                    [decode_row(cols, i, huts_lonlat[int(cols["from_id"][i])], fractions) for i in rows],
                    [_polyline(recs, geom, i) for i in rows])

        start_geometry_path = build_dir / "start-edges" / "geometry.npy"
        if "a50_dlat" in approach_columns and start_geometry_path.exists():
            geom = binfmt.load_array(start_geometry_path, mmap=False)
            rows = _sample_rows(approach_manifest["rows"])
            fractions = _present_fractions(approach_columns)
            report_anchors(
                "start_edges",
                [decode_row(approach_columns, i, huts_lonlat[int(approach_columns["hut_id"][i])], fractions)
                 for i in rows],
                [_polyline(start_records, geom, int(approach_columns["edge_id"][i])) for i in rows])

        tour_dir = build_dir / "tour-edges"
        if (tour_dir / "tours.json").exists() and (tour_dir / "geometry.npy").exists() \
                and (tour_dir / "records.npy").exists():
            with open(tour_dir / "tours.json", encoding="utf-8") as f:
                legs = [leg for t in json.load(f) for leg in t["legs"] if leg.get("anchors")]
            if legs:
                recs = binfmt.load_array(tour_dir / "records.npy", mmap=False)
                geom = binfmt.load_array(tour_dir / "geometry.npy", mmap=False)
                rows = _sample_rows(len(legs))
                report_anchors(
                    "tour_edges",
                    [np.array([[lng, lat] for lat, lng in legs[i]["anchors"]]) for i in rows],
                    [_polyline(recs, geom, legs[i]["edgeId"]) for i in rows])

        for layer_name, payload_manifest_name, geometry_manifest_name, geometry_bin_name in EDGE_PAYLOAD_LAYERS:
            layer_dir = build_dir / EDGE_LAYER_DIRNAMES[layer_name]
            records_path = layer_dir / "records.npy"
            if not records_path.exists():
                continue
            n_records = len(binfmt.load_array(records_path, mmap=False))

            payload_rows = None
            if payload_manifest_name and (layer_dir / payload_manifest_name).exists():
                with open(layer_dir / payload_manifest_name, encoding="utf-8") as f:
                    payload_rows = json.load(f)["rows"]

            geometry_manifest_path = layer_dir / geometry_manifest_name
            geometry_bin_path = layer_dir / geometry_bin_name
            if not geometry_manifest_path.exists() or not geometry_bin_path.exists():
                continue
            with open(geometry_manifest_path, "rb") as f:
                import orjson
                geometry_manifest = orjson.loads(f.read())
            point_counts = geometry_manifest["point_counts"]
            geometry_byte_len = geometry_bin_path.stat().st_size

            c = check_manifest_agreement(layer_name, n_records, payload_rows, point_counts,
                                          geometry_byte_len, args.max_flagged_rows)
            print(f"manifest_agreement[{layer_name}]: {c['summary']['flagged']:,} / "
                  f"{c['summary']['checked']:,} flagged", flush=True)
            checks.append(c)

            # geometry_points.npy is written by build_edge_tiles.py's build_stats as an (n, 2) f4
            # array (4 bytes/coord), flattened lon,lat,lon,lat,... - walk point_counts to recover
            # each edge's slice, mirroring build_stats itself rather than re-deriving the layout.
            geometry_bin = np.frombuffer(geometry_bin_path.read_bytes(), dtype="f4")
            geometry_points = []
            cursor = 0
            for count in point_counts:
                chunk = geometry_bin[cursor:cursor + 2 * count]
                geometry_points.append(list(zip(chunk[0::2].tolist(), chunk[1::2].tolist())))
                cursor += 2 * count
            records = binfmt.load_array(records_path, mmap=False)
            lengths_m = records["distance_m"].tolist()

            c = check_shipped_straightness(
                layer_name, point_counts, geometry_points, lengths_m, args.min_length_m,
                args.straightness_threshold, args.max_points_for_straightness_flag,
                args.max_flagged_rows,
            )
            print(f"shipped_straightness[{layer_name}]: {c['summary']['flagged']:,} / "
                  f"{c['summary']['checked']:,} flagged", flush=True)
            checks.append(c)

            if layer_name == "tour_edges" and (build_dir / "tour-edges" / "tours.json").exists():
                with open(build_dir / "tour-edges" / "tours.json", encoding="utf-8") as f:
                    tours = json.load(f)
                c = check_tours_json_geometry(tours, point_counts, args.max_flagged_rows)
                print(f"tours_json_geometry: {c['summary']['flagged']:,} / {c['summary']['checked']:,} flagged",
                      flush=True)
                checks.append(c)

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        import dodo  # local import: avoids a module-load-order cycle with dag/quality.py at
                     # import time, since dodo.py itself imports dag.quality
        c = check_public_copy_freshness(dodo.PUBLIC_FILES, public_dir, args.max_flagged_rows)
        print(f"public_copy_freshness: {c['summary']['flagged']:,} / {c['summary']['checked']:,} flagged",
              flush=True)
        checks.append(c)

        write_report(Path(args.out), "postprocessing", checks)
        print(f"written {args.out}", flush=True)


if __name__ == "__main__":
    main()
