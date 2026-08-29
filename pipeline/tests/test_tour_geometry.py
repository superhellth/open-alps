import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.tour_geometry import reassemble_fragments  # noqa: E402


def test_two_fragments_join_head_to_tail():
    # Fragment B's start (10.001, 47.0) is ~74m from fragment A's end (10.0, 47.0) - within
    # break_threshold_m, should join into one 4-point chain in A-then-B order.
    a = [(9.998, 47.0), (10.0, 47.0)]
    b = [(10.001, 47.0), (10.003, 47.0)]
    chains = reassemble_fragments([a, b], break_threshold_m=150.0)
    assert len(chains) == 1
    assert chains[0] == a + b


def test_reversed_fragment_is_flipped_before_joining():
    # b's TAIL (not head) is near a's end - must be reversed before appending.
    a = [(9.998, 47.0), (10.0, 47.0)]
    b = [(10.003, 47.0), (10.001, 47.0)]
    chains = reassemble_fragments([a, b], break_threshold_m=150.0)
    assert len(chains) == 1
    assert chains[0] == a + list(reversed(b))


def test_real_break_stays_two_chains():
    # b's start is ~11km from a's end - far past any reasonable break_threshold_m, must NOT join.
    a = [(9.998, 47.0), (10.0, 47.0)]
    b = [(10.1, 47.0), (10.103, 47.0)]
    chains = reassemble_fragments([a, b], break_threshold_m=150.0)
    assert len(chains) == 2


def test_scrambled_order_still_reassembles():
    # Three fragments given out of route order (a, c, b) still join into one ordered chain.
    a = [(9.998, 47.0), (10.0, 47.0)]
    b = [(10.001, 47.0), (10.003, 47.0)]
    c = [(10.0031, 47.0), (10.005, 47.0)]
    chains = reassemble_fragments([a, c, b], break_threshold_m=150.0)
    assert len(chains) == 1
    assert chains[0][0] == a[0] and chains[0][-1] == c[-1]


def test_single_point_fragments_are_dropped():
    a = [(9.998, 47.0), (10.0, 47.0)]
    degenerate = [(11.0, 48.0)]
    chains = reassemble_fragments([a, degenerate], break_threshold_m=150.0)
    assert chains == [a]


from lib.tour_geometry import orient_chain  # noqa: E402


def test_open_chain_already_forward_is_unchanged():
    chain = [(10.0, 47.0), (10.01, 47.0), (10.02, 47.0)]
    huts = [(10.0, 47.0), (10.02, 47.0)]  # first hut near chain start
    assert orient_chain(chain, huts, is_loop=False) == chain


def test_open_chain_backward_gets_reversed():
    chain = [(10.0, 47.0), (10.01, 47.0), (10.02, 47.0)]
    huts = [(10.02, 47.0), (10.0, 47.0)]  # first hut near chain END
    assert orient_chain(chain, huts, is_loop=False) == list(reversed(chain))


def test_loop_chain_picks_direction_matching_hut_order():
    # A 4-point loop; huts visit it in FORWARD point order (0, 1, 2, 3) - orienting forward should
    # win over reversed, which would visit them 3, 2, 1, 0 (all "violations").
    chain = [(10.0, 47.0), (10.01, 47.0), (10.02, 47.0), (10.03, 47.0)]
    huts = [(10.0, 47.0), (10.01, 47.0), (10.02, 47.0), (10.03, 47.0)]
    assert orient_chain(chain, huts, is_loop=True) == chain


def test_loop_chain_reverses_when_huts_visit_backward():
    chain = [(10.0, 47.0), (10.01, 47.0), (10.02, 47.0), (10.03, 47.0)]
    huts = [(10.03, 47.0), (10.02, 47.0), (10.01, 47.0), (10.0, 47.0)]
    assert orient_chain(chain, huts, is_loop=True) == list(reversed(chain))


def test_empty_hut_list_returns_chain_unchanged():
    chain = [(10.0, 47.0), (10.01, 47.0)]
    assert orient_chain(chain, [], is_loop=False) == chain


from lib.tour_geometry import assign_hut_position, leg_chain_slice  # noqa: E402


def test_assign_hut_position_finds_nearest_index():
    chain = [(10.0, 47.0), (10.01, 47.0), (10.02, 47.0)]
    result = assign_hut_position(chain, (10.0095, 47.0), max_hut_trace_m=250.0)
    assert result is not None
    idx, dist_m = result
    assert idx == 1
    assert dist_m < 250.0


def test_assign_hut_position_rejects_beyond_threshold():
    # KHW-style gap (spec §0.3): a hut far from every chain point (~9km scale reproduced small
    # here) must come back None, not the nearest-anyway index.
    chain = [(10.0, 47.0), (10.01, 47.0)]
    result = assign_hut_position(chain, (11.0, 48.0), max_hut_trace_m=250.0)
    assert result is None


def test_leg_chain_slice_normal_leg():
    chain = [(10.0, 47.0), (10.01, 47.0), (10.02, 47.0), (10.03, 47.0)]
    assert leg_chain_slice(chain, 1, 3) == chain[1:4]


def test_leg_chain_slice_wraps_for_rundtour_closing_leg():
    # Closing leg: last hut sits at position 3, first hut at position 0 - the slice must wrap
    # rather than come back empty or run backward through the whole tour.
    chain = [(10.0, 47.0), (10.01, 47.0), (10.02, 47.0), (10.03, 47.0)]
    assert leg_chain_slice(chain, 3, 0) == [chain[3], chain[0]]
