"""Parses pipeline/tours/<TourName>/<N>.gpx folders into ordered per-leg point lists - the
reproducible-by-construction tour input format (docs/superpowers/specs/
2026-08-30-tour-folder-ingestion-design.md §1). One tour = one folder; one leg = one GPX file,
numbered by filename, sorted numerically - never lexicographically, never readdir order."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

_GPX_NS = {"gpx": "http://www.topografix.com/GPX/1/1"}
_LEG_NUMBER_RE = re.compile(r"\d+")


def parse_leg_gpx(path: Path) -> list:
    """Ordered (lon, lat) list from a GPX file's <trk>/<trkseg>/<trkpt> points. <ele> and <wpt>
    are ignored - elevation comes from the graph's own profiles, like every other edge (spec §1)."""
    root = ET.parse(path).getroot()
    return [
        (float(pt.get("lon")), float(pt.get("lat")))
        for pt in root.findall(".//gpx:trk/gpx:trkseg/gpx:trkpt", _GPX_NS)
    ]


def _leg_number(path: Path) -> int:
    if not _LEG_NUMBER_RE.fullmatch(path.stem):
        raise ValueError(f"tour leg filename must be a plain integer, got: {path}")
    return int(path.stem)


def load_tour_folder(folder: Path) -> list:
    """[(leg_number, points), ...] for one tour folder, sorted numerically by filename (spec §1).
    leg_number is the raw integer from the filename; legIndex = leg_number - 1 (spec §4)."""
    numbered = [(_leg_number(f), f) for f in folder.glob("*.gpx")]
    numbered.sort(key=lambda t: t[0])
    return [(n, parse_leg_gpx(f)) for n, f in numbered]


def load_all_tour_folders(tours_dir: Path) -> list:
    """[(tour_name, folder_path), ...] sorted by folder name - spec §4's tourId assignment order
    ("iterating pipeline/tours/ sorted by folder name")."""
    return sorted(
        ((p.name, p) for p in Path(tours_dir).iterdir() if p.is_dir()),
        key=lambda t: t[0],
    )
