import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "phases" / "preprocessing" / "compute_hub_range.py"


def _write_huts(path, coords):
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": c}}
            for c in coords
        ],
    }
    path.write_text(json.dumps(fc), encoding="utf-8")


def test_compute_hub_range_writes_geojson_polygon_containing_every_hut(tmp_path):
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    _write_huts(raw / "huts.geojson", [(11.0, 47.0), (11.2, 47.1)])
    out_path = tmp_path / "data" / "build" / "hub-range" / "hub-range.geojson"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--max-edge-km", "30",
         "--huts", str(raw / "huts.geojson"), "--out", str(out_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    assert out_path.exists()
    with open(out_path, encoding="utf-8") as f:
        geojson = json.load(f)
    assert geojson["type"] in ("Polygon", "MultiPolygon")
