"""Reassembles an AV tour's scrambled polyline fragments into ordered chains, and orients/
positions huts along the result - the ground-truth-shape work `match_tour_edges.py` needs before
any leg can be routed (spec 2026-08-29-official-tours-integration-design.md §2.2, §0.1: the AV's
own `paths` field is an unordered bag of fragments, not one ordered polyline per tour, but the
fragments chain by nearest endpoint with a measured median join gap of 0-14m)."""

import math


def _haversine_m(lon1, lat1, lon2, lat2):
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


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
