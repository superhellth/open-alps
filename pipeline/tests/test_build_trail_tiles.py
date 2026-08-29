import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from postprocessing.build_trail_tiles import filter_trail_feature  # noqa: E402


def test_filter_trail_feature_keeps_only_highway():
    feat = {
        "type": "Feature",
        "properties": {"highway": "path", "name": "Steig", "surface": "gravel"},
        "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 1.0]]},
    }
    out = filter_trail_feature(feat)
    assert out["properties"] == {"highway": "path"}
    assert out["geometry"] == feat["geometry"]


def test_filter_trail_feature_handles_missing_properties():
    feat = {"type": "Feature", "properties": None, "geometry": {"type": "LineString"}}
    out = filter_trail_feature(feat)
    assert out["properties"] == {"highway": None}
