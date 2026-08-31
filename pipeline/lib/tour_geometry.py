"""Reassembles an AV tour's scrambled polyline fragments into ordered chains, and orients/
positions huts along the result - the ground-truth-shape work `match_tour_edges.py` needs before
any leg can be routed (spec 2026-08-29-official-tours-integration-design.md §2.2, §0.1: the AV's
own `paths` field is an unordered bag of fragments, not one ordered polyline per tour, but the
fragments chain by nearest endpoint with a measured median join gap of 0-14m)."""

from lib.geo import haversine_m as _haversine_m


def reassemble_fragments(fragments: list, break_threshold_m: float) -> list:
    """Greedily joins fragments by nearest endpoint (reversing a fragment when it joins tail-to-
    tail or head-to-head), stopping when the nearest remaining join exceeds break_threshold_m -
    spec §2.2 step 1. O(n^2) per merge / O(n^3) worst case over the whole fragment set, fine at
    this pipeline's real scale (max 51 fragments per tour, spec §0.2's SVR7T).

    Fragments with fewer than 2 points are dropped (can't be joined or meaningfully routed)."""
    remaining = [list(f) for f in fragments if len(f) >= 2]
    chains = []
    while remaining:
        chain = remaining.pop(0)
        merged = True
        while merged and remaining:
            merged = False
            head, tail = chain[0], chain[-1]
            best = None  # (dist_m, index_into_remaining, join_kind)
            for i, frag in enumerate(remaining):
                fh, ft = frag[0], frag[-1]
                for d, kind in (
                    (_haversine_m(*tail, *fh), "tail_head"),
                    (_haversine_m(*tail, *ft), "tail_tail"),
                    (_haversine_m(*head, *fh), "head_head"),
                    (_haversine_m(*head, *ft), "head_tail"),
                ):
                    if best is None or d < best[0]:
                        best = (d, i, kind)
            if best is not None and best[0] <= break_threshold_m:
                _, idx, kind = best
                frag = remaining.pop(idx)
                if kind == "tail_head":
                    chain = chain + frag
                elif kind == "tail_tail":
                    chain = chain + list(reversed(frag))
                elif kind == "head_head":
                    chain = list(reversed(frag)) + chain
                else:  # head_tail
                    chain = frag + chain
                merged = True
        chains.append(chain)
    return chains


def _nearest_chain_index(chain: list, point: tuple) -> int:
    dists = [_haversine_m(*p, *point) for p in chain]
    return dists.index(min(dists))


def orient_chain(chain: list, hut_coords_in_order: list, is_loop: bool) -> list:
    """Orients a reassembled chain (Task 3) so its point order matches the tour's own hut visit
    order (spec §2.2 step 3). For an open chain, whichever end sits nearer the first hut becomes
    index 0. For a Rundtour the chain closes on itself, so both directions are valid geometric
    walks - the one that visits the hut list with fewer order violations (a later hut assigned to
    an earlier chain position than the one before it) wins."""
    if not hut_coords_in_order:
        return chain
    if not is_loop:
        start_d = _haversine_m(*chain[0], *hut_coords_in_order[0])
        end_d = _haversine_m(*chain[-1], *hut_coords_in_order[0])
        return chain if start_d <= end_d else list(reversed(chain))

    def violations(oriented_chain):
        positions = [_nearest_chain_index(oriented_chain, h) for h in hut_coords_in_order]
        return sum(1 for a, b in zip(positions, positions[1:]) if b < a)

    reversed_chain = list(reversed(chain))
    return chain if violations(chain) <= violations(reversed_chain) else reversed_chain


def assign_hut_position(chain: list, hut_coord: tuple, max_hut_trace_m: float):
    """Nearest chain point to a hut's own coordinate, as a (chain_index, dist_m) pair - or None
    when even the nearest point exceeds max_hut_trace_m (spec §0.3: "huts sit right on the trail"
    is false, e.g. KHW's Zollnersee-Hütte at 9,178m; this is the hut_far_from_trace gap case,
    spec §2.5)."""
    idx = _nearest_chain_index(chain, hut_coord)
    dist_m = _haversine_m(*chain[idx], *hut_coord)
    if dist_m > max_hut_trace_m:
        return None
    return idx, dist_m


def leg_chain_slice(chain: list, pos_a: int, pos_b: int) -> list:
    """Sub-chain between two chain-position indices, order-agnostic. Handles the Rundtour closing
    leg's wraparound (pos_a > pos_b, e.g. last hut's position > first hut's position on an oriented
    loop chain) by concatenating the tail and the head instead of returning an empty/reversed
    slice."""
    if pos_a <= pos_b:
        return chain[pos_a:pos_b + 1]
    return chain[pos_a:] + chain[:pos_b + 1]
