import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dem_providers import composite  # noqa: E402


def test_fetch_and_build_calls_each_region_provider_and_merges(tmp_path, monkeypatch):
    calls = []

    fake_provider = MagicMock()
    fake_provider.fetch.side_effect = lambda cfg, raw_dir: calls.append(("fetch", cfg)) or [
        raw_dir / "tile.tif"
    ]
    fake_provider.to_4326_vrt.side_effect = lambda paths, out: calls.append(
        ("to_4326_vrt", paths, out)
    ) or out

    monkeypatch.setattr(composite, "get_provider", lambda name: fake_provider)

    merge_calls = []
    monkeypatch.setattr(
        composite.subprocess, "run",
        lambda args, **kwargs: merge_calls.append(args)
    )

    provider_config = {
        "regions": [
            {"provider": "at-bev-dgm", "bbox": {"minLng": 0, "maxLng": 1, "minLat": 0, "maxLat": 1}},
            {"provider": "bavaria-dgm5", "bbox": {"minLng": 1, "maxLng": 2, "minLat": 0, "maxLat": 1}},
        ]
    }

    out_vrt = tmp_path / "dem.vrt"
    result = composite.fetch_and_build(provider_config, tmp_path)

    assert result == out_vrt
    assert sum(1 for c in calls if c[0] == "fetch") == 2
    assert sum(1 for c in calls if c[0] == "to_4326_vrt") == 2
    assert len(merge_calls) == 1  # final gdalbuildvrt over the two regional VRTs
    assert merge_calls[0][0] == "gdalbuildvrt"
