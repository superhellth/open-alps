import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.alpenvereinaktiv import (  # noqa: E402
    extract_tour_id, gpx_download_url, parse_stage_ids,
)

STAGE_SELECT_HTML = """
<select>
<option value="#" selected="selected">Etappe auswählen</option>
<option value="13450377">Etappe 1: Lechquellenrunde - Etappe 1: Bregenzerwald - Biberacher Hütte</option>
<option value="13450444">Etappe 2: Lechquellenrunde - Etappe 2: Biberacher Hütte - Göppinger Hütte</option>
<option value="13450498">Etappe 3: Lechquellenrunde - Etappe 3: Göppinger Hütte - Freiburger Hütte</option>
</select>
"""


def test_parse_stage_ids_extracts_leg_number_and_tour_id_in_order():
    assert parse_stage_ids(STAGE_SELECT_HTML) == [
        (1, "13450377"), (2, "13450444"), (3, "13450498"),
    ]


def test_parse_stage_ids_returns_empty_for_single_leg_tour():
    assert parse_stage_ids("<html><body>no stages here</body></html>") == []


def test_extract_tour_id_from_tour_url():
    url = "https://www.alpenvereinaktiv.com/de/tour/lechquellenrunde/13444525/?utm_medium=referral"
    assert extract_tour_id(url) == "13444525"


def test_gpx_download_url_builds_alpenverein_project_link():
    assert gpx_download_url("13450377") == (
        "https://www.alpenvereinaktiv.com/de/download.tour.gpx?i=13450377&project=alpenverein"
    )
