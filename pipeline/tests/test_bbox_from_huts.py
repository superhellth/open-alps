import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.pipeline import bbox_from_huts  # noqa: E402


def _write_huts(tmp_path, coords):
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": c}}
            for c in coords
        ],
    }
    path = tmp_path / "huts.geojson"
    path.write_text(json.dumps(fc), encoding="utf-8")
    return path


def test_bbox_from_huts_covers_all_points_with_buffer(tmp_path):
    huts_path = _write_huts(tmp_path, [(10.0, 47.0), (10.5, 47.3), (10.2, 47.1)])

    bbox = bbox_from_huts(huts_path, buffer_deg=0.05)

    assert bbox == {
        "minLng": 10.0 - 0.05,
        "maxLng": 10.5 + 0.05,
        "minLat": 47.0 - 0.05,
        "maxLat": 47.3 + 0.05,
    }


def test_bbox_from_huts_filters_to_filter_bbox_first(tmp_path):
    # One hut in Austria-ish territory, one far away in Bavaria-ish territory - filter_bbox
    # should exclude the far one, same as composite.py using it to split huts.geojson (which
    # covers the whole pipeline scope) into a single region's huts.
    huts_path = _write_huts(tmp_path, [(11.0, 47.5), (99.0, 89.0)])
    filter_bbox = {"minLng": 8.9, "maxLng": 17.2, "minLat": 46.3, "maxLat": 50.6}

    bbox = bbox_from_huts(huts_path, filter_bbox=filter_bbox, buffer_deg=0.0)

    assert bbox == {"minLng": 11.0, "maxLng": 11.0, "minLat": 47.5, "maxLat": 47.5}


def test_bbox_from_huts_raises_when_filter_excludes_everything(tmp_path):
    huts_path = _write_huts(tmp_path, [(11.0, 47.5)])
    filter_bbox = {"minLng": 0.0, "maxLng": 1.0, "minLat": 0.0, "maxLat": 1.0}

    try:
        bbox_from_huts(huts_path, filter_bbox=filter_bbox)
        assert False, "expected ValueError"
    except ValueError:
        pass
