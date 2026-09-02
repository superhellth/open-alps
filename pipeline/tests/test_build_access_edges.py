import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from lib import variants  # noqa: E402
from lib.subgraph import LocalSubgraph  # noqa: E402
from graph_building.build_hub_edges import snap_hubs_for_cell  # noqa: E402
from graph_building.build_access_edges import route_selected_pairs_for_cell  # noqa: E402

FAST_ANY_ONLY = [variants.VARIANTS[binfmt.VARIANT_FAST_ANY]]


def _line_subgraph():
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.009, 0.0, 0)
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 1000.0, 0.0, 0.0, 0.0, 1000.0, binfmt.UNSET, binfmt.UNSET, -1, False, True,
                0, 0, 0)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    return LocalSubgraph(
        global_node_ids=np.array([100, 101]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.zeros(len(nodes), dtype=np.float32),
        interior_ele=np.zeros(len(interior), dtype=np.float32),
    )


def test_materializes_geometry_only_for_selected_targets():
    subgraph = _line_subgraph()
    hut = {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0}
    station = {"id": 2, "type": binfmt.TYPE_STATION, "lon": 0.0089, "lat": 0.0}
    all_hubs = [hut, station]
    snaps = snap_hubs_for_cell(subgraph, [hut], all_hubs, max_snap_m=50.0)
    selected_targets_by_hut = {1: [station]}

    records = route_selected_pairs_for_cell(
        subgraph, [hut], selected_targets_by_hut, snaps, variants=FAST_ANY_ONLY,
    )

    assert len(records) == 1
    r = records[0]
    # A3: stored access -> hut, even though the router walked hut -> access.
    assert r["from_id"] == station["id"] and r["from_type"] == binfmt.TYPE_STATION
    assert r["to_id"] == hut["id"] and r["to_type"] == binfmt.TYPE_HUT
    assert r["geometry"][0] == (station["lon"], station["lat"])
    assert r["geometry"][-1] == (hut["lon"], hut["lat"])


def test_unselected_target_is_never_routed():
    subgraph = _line_subgraph()
    hut = {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0}
    station = {"id": 2, "type": binfmt.TYPE_STATION, "lon": 0.0089, "lat": 0.0}
    snaps = snap_hubs_for_cell(subgraph, [hut], [hut, station], max_snap_m=50.0)

    records = route_selected_pairs_for_cell(
        subgraph, [hut], selected_targets_by_hut={1: []}, snaps=snaps, variants=FAST_ANY_ONLY,
    )

    assert records == []


def test_ascent_descent_are_swapped_relative_to_the_hut_sourced_walk():
    # hut sits ABOVE its own snap point (climbing down FROM the hut to the trail is descent from
    # the hut's perspective); once reoriented to access->hut storage, that same physical drop must
    # read as the ACCESS side's ascent (climbing UP from the trail to the hut).
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.009, 0.0, 0)
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 1000.0, 0.0, 0.0, 0.0, 1000.0, 80.0, 0.0, -1, False, True, 0, 0, 0)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    subgraph = LocalSubgraph(
        global_node_ids=np.array([100, 101]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.zeros(2, dtype=np.float32),
        interior_ele=np.zeros(0, dtype=np.float32),
    )
    hut = {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0}
    station = {"id": 2, "type": binfmt.TYPE_STATION, "lon": 0.0089, "lat": 0.0}
    snaps = snap_hubs_for_cell(subgraph, [hut], [hut, station], max_snap_m=50.0)

    records = route_selected_pairs_for_cell(
        subgraph, [hut], {1: [station]}, snaps, variants=FAST_ANY_ONLY,
    )

    # the edge is 80m of ascent walking 0->1 (hut's side); reversed to access(2)->hut(1) storage
    # the SAME physical climb is now traversed 1->0, so it must land in descent, not ascent.
    assert records[0]["descent_m"] >= 80.0
    assert records[0]["ascent_m"] < 80.0
