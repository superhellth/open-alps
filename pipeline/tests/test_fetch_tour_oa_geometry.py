import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib.oa_geometry import oa_chain  # noqa: E402


def test_oa_chain_survives_a_cached_content_round_trip(tmp_path):
    # Guards the shape fetch_tour_oa_geometry.py writes: {tourId, points} with points already
    # 2-D, so match_tour_edges.py never has to know about OA's [lon, lat, ele] triples.
    content = {"id": "999", "geoJson": {"type": "LineString",
                                         "coordinates": [[10.0, 47.0, 1200.0], [10.1, 47.1, 1300.0]]}}
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(json.dumps({"999": content}), encoding="utf-8")

    from lib.oa_geometry import fetch_oa_contents
    with patch("urllib.request.urlopen") as mock_urlopen:
        contents = fetch_oa_contents(["999"], cache_path, allow_fetch=True)
    mock_urlopen.assert_not_called()
    assert oa_chain(contents["999"]) == [(10.0, 47.0), (10.1, 47.1)]
