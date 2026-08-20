import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

import downloads.dem_providers as dem_providers  # noqa: E402
from downloads.dem_providers import composite  # noqa: E402
from lib import pipeline as pipeline_lib  # noqa: E402


def test_fetch_regions_calls_each_region_provider_and_returns_manifest(tmp_path, monkeypatch):
    calls = []

    fake_provider = MagicMock()
    fake_provider.fetch.side_effect = lambda cfg, raw_dir: calls.append(("fetch", cfg)) or [
        raw_dir / "tile.tif"
    ]

    monkeypatch.setattr(composite, "get_provider", lambda name: fake_provider)

    provider_config = {
        "regions": [
            {"provider": "at-bev-dgm", "bbox": {"minLng": 0, "maxLng": 1, "minLat": 0, "maxLat": 1}},
            {"provider": "bavaria-dgm5", "bbox": {"minLng": 1, "maxLng": 2, "minLat": 0, "maxLat": 1}},
        ]
    }

    manifest = composite.fetch_regions(provider_config, tmp_path)

    assert sum(1 for c in calls if c[0] == "fetch") == 2
    assert len(manifest) == 2
    assert manifest[0]["provider"] == "at-bev-dgm"
    assert manifest[1]["provider"] == "bavaria-dgm5"
    assert manifest[0]["tile_paths"] == [str(tmp_path / "raw" / "region_0_at-bev-dgm" / "tile.tif")]


def test_build_dem_vrt_reprojects_each_region_and_merges(tmp_path, monkeypatch):
    calls = []

    fake_provider = MagicMock()
    fake_provider.to_4326_vrt.side_effect = lambda paths, out: calls.append(
        ("to_4326_vrt", paths, out)
    ) or out

    monkeypatch.setattr(dem_providers, "get_provider", lambda name: fake_provider)
    monkeypatch.setattr(pipeline_lib, "normalize_colorinterp", lambda p: p)

    merge_calls = []
    monkeypatch.setattr(
        pipeline_lib.subprocess, "run",
        lambda args, **kwargs: merge_calls.append(args)
    )

    manifest = [
        {
            "provider": "at-bev-dgm",
            "raw_dir": str(tmp_path / "raw" / "region_0_at-bev-dgm"),
            "region_vrt": str(tmp_path / "region_0_at-bev-dgm.vrt"),
            "tile_paths": [str(tmp_path / "raw" / "region_0_at-bev-dgm" / "tile.tif")],
        },
        {
            "provider": "bavaria-dgm5",
            "raw_dir": str(tmp_path / "raw" / "region_1_bavaria-dgm5"),
            "region_vrt": str(tmp_path / "region_1_bavaria-dgm5.vrt"),
            "tile_paths": [str(tmp_path / "raw" / "region_1_bavaria-dgm5" / "tile.tif")],
        },
    ]

    out_vrt = tmp_path / "dem.vrt"
    result = pipeline_lib.build_dem_vrt(manifest, tmp_path)

    assert result == out_vrt
    assert sum(1 for c in calls if c[0] == "to_4326_vrt") == 2
    assert len(merge_calls) == 1  # final gdalbuildvrt over the two regional VRTs
    assert merge_calls[0][0] == "gdalbuildvrt"
