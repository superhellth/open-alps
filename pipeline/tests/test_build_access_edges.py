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


def _two_edge_line_subgraph():
    nodes = np.zeros(3, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.0045, 0.0, 0)
    nodes[2] = (0.009, 0.0, 0)
    edges = np.zeros(2, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 500.0, 0.0, 0.0, 0.0, 500.0, binfmt.UNSET, binfmt.UNSET, -1, False, True,
                0, 0, 0)
    edges[1] = (1, 2, 500.0, 0.0, 0.0, 0.0, 500.0, binfmt.UNSET, binfmt.UNSET, -1, False, True,
                0, 0, 1)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    return LocalSubgraph(
        global_node_ids=np.array([100, 101, 102]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.zeros(len(nodes), dtype=np.float32),
        interior_ele=np.zeros(len(interior), dtype=np.float32),
    )


def test_base_edge_ids_are_reversed_into_access_to_hut_traversal_order():
    subgraph = _two_edge_line_subgraph()
    # Hut/station coincide exactly with nodes 2/0 (same reasoning as
    # test_ascent_descent_are_swapped_relative_to_the_hut_sourced_walk above): snap_hub_to_subgraph
    # has no node preference, so anything off-node snaps mid-edge instead, which would pull in
    # cell_igraph.py's *3/*3+1/*3+2 split-edge id disambiguation and obscure the plain edge ids this
    # test wants to assert on.
    hut = {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.009, "lat": 0.0}
    station = {"id": 2, "type": binfmt.TYPE_STATION, "lon": 0.0, "lat": 0.0}
    snaps = snap_hubs_for_cell(subgraph, [hut], [hut, station], max_snap_m=50.0)
    selected_targets_by_hut = {1: [station]}

    records, unreachable_skipped = route_selected_pairs_for_cell(
        subgraph, [hut], selected_targets_by_hut, snaps, variants=FAST_ANY_ONLY, max_edge_km=5.0,
    )

    assert unreachable_skipped == 0
    assert len(records) == 1
    # The router walks hut -> access (edge_id 1, near the hut at node 2, then edge_id 0, near the
    # access point at node 0). A3 (2026-09-02 spec) reverses this into the access -> hut storage
    # order every start_edges consumer expects - access-nearest edge first, hut-nearest edge last -
    # which is what makes turning write_edge_ids on for start_edges safe. (base_edge_id values are
    # each raw edge id * 3 - cell_igraph.py's disambiguation scheme for unsplit edges, see its
    # build_base_igraph_arrays docstring - so edge_id 0 -> 0 and edge_id 1 -> 3.)
    assert records[0]["base_edge_ids"] == [0, 3]


def test_materializes_geometry_only_for_selected_targets():
    subgraph = _line_subgraph()
    hut = {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0}
    station = {"id": 2, "type": binfmt.TYPE_STATION, "lon": 0.0089, "lat": 0.0}
    all_hubs = [hut, station]
    snaps = snap_hubs_for_cell(subgraph, [hut], all_hubs, max_snap_m=50.0)
    selected_targets_by_hut = {1: [station]}

    records, unreachable_skipped = route_selected_pairs_for_cell(
        subgraph, [hut], selected_targets_by_hut, snaps, variants=FAST_ANY_ONLY, max_edge_km=5.0,
    )

    assert unreachable_skipped == 0
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

    records, unreachable_skipped = route_selected_pairs_for_cell(
        subgraph, [hut], selected_targets_by_hut={1: []}, snaps=snaps, variants=FAST_ANY_ONLY,
        max_edge_km=5.0,
    )

    assert records == []
    assert unreachable_skipped == 0


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
    # hub coincides exactly with node 0, not just "near" it - snap_hub_to_subgraph has no node
    # preference, so anywhere off that exact point on this straight edge is genuinely closer to
    # the edge's interior than to the node and would snap mid-chain instead, losing this edge's
    # ascent_m/descent_m to the (documented, spec C9) split-edge elevation-apportionment gap this
    # test isn't exercising.
    hut = {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0, "lat": 0.0}
    station = {"id": 2, "type": binfmt.TYPE_STATION, "lon": 0.009, "lat": 0.0}
    snaps = snap_hubs_for_cell(subgraph, [hut], [hut, station], max_snap_m=50.0)

    records, _ = route_selected_pairs_for_cell(
        subgraph, [hut], {1: [station]}, snaps, variants=FAST_ANY_ONLY, max_edge_km=5.0,
    )

    # the edge is 80m of ascent walking 0->1 (hut's side); reversed to access(2)->hut(1) storage
    # the SAME physical climb is now traversed 1->0, so it must land in descent, not ascent.
    assert records[0]["descent_m"] >= 80.0
    assert records[0]["ascent_m"] < 80.0


def test_unreachable_selected_target_is_skipped_not_emitted_as_zero_distance():
    # selected_targets_by_hut is variant-agnostic (a pair select_approach_pairs.py kept because it
    # was reachable under ONE variant can be genuinely disconnected under another's edge mask) - a
    # station on its own, disconnected island must be dropped, not accumulate_path's empty-epath
    # fallthrough silently emitting a phantom zero-distance/zero-geometry edge for it.
    subgraph = _line_subgraph()
    hut = {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0}
    station = {"id": 2, "type": binfmt.TYPE_STATION, "lon": 0.0089, "lat": 0.0}
    island_nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    island_nodes[0] = (1.0, 0.0, 0)
    island_nodes[1] = (1.009, 0.0, 0)
    island_edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    # u=2, v=3: the island's own local node indices once concatenated after the 2-node line above.
    island_edges[0] = (2, 3, 1000.0, 0.0, 0.0, 0.0, 1000.0, binfmt.UNSET, binfmt.UNSET, -1, False,
                        True, 0, 0, 1)
    island = {"id": 3, "type": binfmt.TYPE_STATION, "lon": 1.0001, "lat": 0.0}
    nodes = np.concatenate([subgraph.local_nodes, island_nodes])
    edges = np.concatenate([subgraph.local_edges, island_edges])
    disconnected_subgraph = LocalSubgraph(
        global_node_ids=np.array([100, 101, 200, 201]), local_nodes=nodes, local_edges=edges,
        interior=subgraph.interior,
        local_node_ele=np.zeros(4, dtype=np.float32),
        interior_ele=subgraph.interior_ele,
    )
    snaps = snap_hubs_for_cell(disconnected_subgraph, [hut], [hut, station, island],
                                max_snap_m=50.0)

    records, unreachable_skipped = route_selected_pairs_for_cell(
        disconnected_subgraph, [hut], {1: [station, island]}, snaps, variants=FAST_ANY_ONLY,
        max_edge_km=5.0,
    )

    assert len(records) == 1
    assert records[0]["from_id"] == station["id"]
    assert unreachable_skipped == 1


def test_route_exceeding_max_edge_km_is_dropped():
    # same C8 divergence as build_hub_edges.py's test_route_exceeding_max_edge_km_is_dropped: the
    # materialized path here is TIME-shortest and can exceed the cap even though
    # select_approach_pairs.py's dist-weighted cutoff would not have allowed it through.
    subgraph = _line_subgraph()
    hut = {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0}
    station = {"id": 2, "type": binfmt.TYPE_STATION, "lon": 0.0089, "lat": 0.0}
    snaps = snap_hubs_for_cell(subgraph, [hut], [hut, station], max_snap_m=50.0)

    records, _ = route_selected_pairs_for_cell(
        subgraph, [hut], {1: [station]}, snaps, variants=FAST_ANY_ONLY, max_edge_km=0.5,
    )

    assert records == []
