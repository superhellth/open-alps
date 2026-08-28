#!/usr/bin/env python3
"""
Downloads raw Geofabrik regional extracts listed in pipeline.config.json.
Re-run to refresh to the latest Geofabrik snapshot (they regenerate daily, not pinned/versioned).
Usage: python pipeline/phases/downloads/download_extracts.py
"""

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.timing import StepTimer, phase  # noqa: E402

SCRIPT_NAME = "download_extracts.py"

config = load_config()
raw_dir = OSM_DIR / "raw"
raw_dir.mkdir(parents=True, exist_ok=True)

timer = StepTimer()
with phase(SCRIPT_NAME, "download_extracts") as meta:
    for region in config["regions"]:
        out_path = raw_dir / f"{region['name']}-latest.osm.pbf"
        print(f"downloading {region['url']} -> {out_path}")
        with timer.step("download"):
            urllib.request.urlretrieve(region["url"], out_path)

    for f in sorted(raw_dir.iterdir()):
        print(f.name, f.stat().st_size)
    meta.update(timer.as_meta())
print(f"step totals: {timer.summary()}", flush=True)
