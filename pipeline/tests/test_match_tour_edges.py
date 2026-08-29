import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from graph_building.match_tour_edges import build_tour_legs  # noqa: E402


def _tour(hut_indices, is_loop=False):
    return {"tourId": 0, "hutIndices": hut_indices, "isLoop": is_loop}


def test_open_tour_yields_n_minus_one_legs():
    legs = build_tour_legs(_tour([0, 1, 2, 3]))
    assert legs == [(0, 0, 1), (1, 1, 2), (2, 2, 3)]


def test_loop_tour_yields_n_legs_with_contiguous_leg_index():
    # spec §2.1 / Testing: a loop tour yields N legs, not N-1, and leg_index is contiguous -
    # the closing leg (last hut -> first hut) is appended.
    legs = build_tour_legs(_tour([0, 1, 2], is_loop=True))
    assert legs == [(0, 0, 1), (1, 1, 2), (2, 2, 0)]
    assert [leg[0] for leg in legs] == [0, 1, 2]


def test_unresolved_hut_sentinel_splits_the_chain():
    # -1 (fetch_tours.py's unresolved-GUID sentinel) drops BOTH legs touching it, not just one -
    # never silently fuses the two real stages on either side into one leg (spec §1).
    legs = build_tour_legs(_tour([0, 1, -1, 3, 4]))
    assert legs == [(0, 0, 1), (3, 3, 4)]


def test_empty_hut_list_yields_no_legs():
    assert build_tour_legs(_tour([])) == []


def test_single_hut_yields_no_legs():
    assert build_tour_legs(_tour([0])) == []
