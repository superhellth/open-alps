import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.oa_geometry import fetch_oa_contents, oa_chain, oa_ids_by_tour  # noqa: E402


def test_oa_ids_by_tour_matches_alpenvereinaktiv_urls_only():
    tours = [
        {"tourId": 0, "homepage": "https://www.alpenvereinaktiv.com/de/tour/thw/12345/6789/"},
        # a DIFFERENT Outdooractive white-label project - must NOT match (spike's docstring:
        # tour 22 / MontafonerSilvrettarunde links to touren.montafon.at, ids don't resolve
        # under project/alpenverein)
        {"tourId": 1, "homepage": "https://touren.montafon.at/de/tour/fernwanderweg/x/43535278/"},
        {"tourId": 2, "homepage": None},
        {"tourId": 3, "homepage": "https://www.karnischer-hoehenweg.com/"},
    ]
    assert oa_ids_by_tour(tours) == {0: "6789"}


def test_oa_chain_drops_elevation_and_handles_missing_geojson():
    assert oa_chain({"geoJson": {"type": "LineString",
                                  "coordinates": [[10.1, 47.2, 1500.0], [10.2, 47.3, 1600.0]]}}) \
        == [(10.1, 47.2), (10.2, 47.3)]
    assert oa_chain({}) == []
    assert oa_chain({"geoJson": {"type": "Point", "coordinates": [10.1, 47.2]}}) == []


def test_fetch_oa_contents_uses_cache_without_network(tmp_path):
    cache_path = tmp_path / "oa_cache.json"
    cache_path.write_text(json.dumps({"111": {"id": "111", "geoJson": None}}), encoding="utf-8")
    with patch("urllib.request.urlopen") as mock_urlopen:
        result = fetch_oa_contents(["111"], cache_path, allow_fetch=True)
    mock_urlopen.assert_not_called()
    assert result == {"111": {"id": "111", "geoJson": None}}


def test_fetch_oa_contents_raises_when_not_allowed_to_fetch(tmp_path):
    cache_path = tmp_path / "oa_cache.json"
    with patch("urllib.request.urlopen") as mock_urlopen:
        try:
            fetch_oa_contents(["111"], cache_path, allow_fetch=False)
            assert False, "expected SystemExit"
        except SystemExit:
            pass
    mock_urlopen.assert_not_called()
