#!/usr/bin/env python3
"""Matches each official AV tour's legs (hutIndices[i] -> hutIndices[i+1], plus the closing leg
for a Rundtour) onto the persisted base graph, constrained to the AV's own published route
geometry rather than routed freely - see docs/superpowers/specs/2026-08-29-official-tours-
integration-design.md. Produces data/osm/tour_edges/{records.npy, geometry.npy, edge_ids.npy,
tour_meta.npy} (same shape as hut_edges/, plus the tour_meta.npy sidecar) and
tour-match-gaps.json (spec §2.5's never-faked gap reasons).

Usage: python pipeline/phases/graph_building/match_tour_edges.py
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import binfmt  # noqa: E402
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "match_tour_edges.py"


def build_tour_legs(tour: dict) -> list:
    """(leg_index, from_hut_index, to_hut_index) triples in tour order, plus the Rundtour closing
    leg (spec §2.1). A leg touching fetch_tours.py's -1 unresolved-GUID sentinel is dropped -
    BOTH legs on either side of a -1 entry are skipped, since neither has a real hut on both ends
    (spec §1's "split the chain" convention)."""
    huts = tour["hutIndices"]
    pairs = list(zip(huts, huts[1:]))
    if tour.get("isLoop") and len(huts) >= 2:
        pairs.append((huts[-1], huts[0]))
    legs = []
    for i, (a, b) in enumerate(pairs):
        if a == -1 or b == -1:
            continue
        legs.append((i, a, b))
    return legs
