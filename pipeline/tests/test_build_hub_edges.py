import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import binfmt  # noqa: E402
from lib.grid import Grid  # noqa: E402
from lib.subgraph import LocalSubgraph  # noqa: E402
from graph_building.build_hub_edges import (  # noqa: E402
    compute_hub_edges_for_cell, merge_and_dedup, snap_hub_to_subgraph,
)

BBOX = {"minLng": 0.0, "maxLng": 1.0, "minLat": 0.0, "maxLat": 1.0}


def _line_subgraph():
    # Two nodes 1000m apart (roughly, at these latitudes), one edge, no interior points -
    # a hub snapping anywhere on it lands mid-chain (segment_index=0).
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.009, 0.0, 0)  # ~1000m east at the equator
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 1000.0, 1000.0, 0.0, -1, False, 0, 0, 0)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    return LocalSubgraph(
        global_node_ids=np.array([100, 101]), local_nodes=nodes, local_edges=edges,
        interior=interior,
    )


def test_snap_hub_to_existing_node():
    subgraph = _line_subgraph()
    result = snap_hub_to_subgraph(subgraph, hub_lon=0.0001, hub_lat=0.0, max_snap_m=50.0)
    assert result is not None
    assert result.node_index == 0


def test_snap_hub_mid_chain_returns_split():
    subgraph = _line_subgraph()
    result = snap_hub_to_subgraph(subgraph, hub_lon=0.0045, hub_lat=0.0002, max_snap_m=50.0)
    assert result is not None
    assert result.split is not None
    assert result.edge_local_index == 0


def test_snap_returns_none_when_out_of_range():
    subgraph = _line_subgraph()
    result = snap_hub_to_subgraph(subgraph, hub_lon=0.5, hub_lat=0.5, max_snap_m=50.0)
    assert result is None


def test_compute_hub_edges_for_cell_connects_two_huts_on_the_line():
    subgraph = _line_subgraph()
    core_hubs = [
        {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0},
        {"id": 2, "type": binfmt.TYPE_HUT, "lon": 0.0089, "lat": 0.0},
    ]
    records = compute_hub_edges_for_cell(
        subgraph, core_hubs, all_hubs=core_hubs, max_edge_km=5.0, max_snap_m=50.0,
    )
    assert len(records) == 1
    assert records[0]["distance_m"] < 5000


def test_compute_hub_edges_for_cell_returns_full_path_geometry():
    subgraph = _line_subgraph()
    core_hubs = [
        {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0},
        {"id": 2, "type": binfmt.TYPE_HUT, "lon": 0.0089, "lat": 0.0},
    ]
    records = compute_hub_edges_for_cell(
        subgraph, core_hubs, all_hubs=core_hubs, max_edge_km=5.0, max_snap_m=50.0,
    )
    assert len(records) == 1
    geometry = records[0]["geometry"]
    assert len(geometry) >= 2
    assert geometry[0] == (core_hubs[0]["lon"], core_hubs[0]["lat"])
    assert geometry[-1] == (core_hubs[1]["lon"], core_hubs[1]["lat"])


def test_merge_and_dedup_drops_duplicate_hut_pairs():
    shard_a = [{"from_id": 1, "to_id": 2, "from_type": binfmt.TYPE_HUT,
                "to_type": binfmt.TYPE_HUT, "distance_m": 100.0}]
    shard_b = [{"from_id": 2, "to_id": 1, "from_type": binfmt.TYPE_HUT,
                "to_type": binfmt.TYPE_HUT, "distance_m": 100.0}]
    merged = merge_and_dedup([shard_a, shard_b])
    assert len(merged) == 1


def test_merge_and_dedup_keeps_directional_start_edges():
    shard = [
        {"from_id": 1, "to_id": 2, "from_type": binfmt.TYPE_PARKING,
         "to_type": binfmt.TYPE_HUT, "distance_m": 100.0},
        {"from_id": 1, "to_id": 3, "from_type": binfmt.TYPE_PARKING,
         "to_type": binfmt.TYPE_HUT, "distance_m": 200.0},
    ]
    merged = merge_and_dedup([shard])
    assert len(merged) == 2
