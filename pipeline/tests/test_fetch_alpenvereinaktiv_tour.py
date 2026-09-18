import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.fetch_alpenvereinaktiv_tour import resolve_legs  # noqa: E402

STAGE_HTML = """
<option value="13450377">Etappe 1: X - Y</option>
<option value="13450444">Etappe 2: Y - Z</option>
"""


def test_resolve_legs_uses_stage_select_when_present():
    with patch("tools.fetch_alpenvereinaktiv_tour._fetch", return_value=STAGE_HTML):
        legs = resolve_legs("https://www.alpenvereinaktiv.com/de/tour/x/13444525/")
    assert legs == [(1, "13450377"), (2, "13450444")]


def test_resolve_legs_falls_back_to_tour_id_for_single_leg_tour():
    with patch("tools.fetch_alpenvereinaktiv_tour._fetch", return_value="<html></html>"):
        legs = resolve_legs("https://www.alpenvereinaktiv.com/de/tour/x/13444525/")
    assert legs == [(1, "13444525")]
