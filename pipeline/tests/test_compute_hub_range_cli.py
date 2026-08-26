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
    osm_dir = tmp_path / "data" / "osm"
    osm_dir.mkdir(parents=True)
    _write_huts(osm_dir / "huts.geojson", [(11.0, 47.0), (11.2, 47.1)])

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--max-edge-km", "30",
         "--osm-dir", str(osm_dir)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    out_path = osm_dir / "hub_range.geojson"
    assert out_path.exists()
    with open(out_path, encoding="utf-8") as f:
        geojson = json.load(f)
    assert geojson["type"] in ("Polygon", "MultiPolygon")
