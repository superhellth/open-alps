import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.geo import haversine_m
from lib.hmm_match import resample_trace


def _line_points(n, spacing_m):
    # straight east-west line at the equator; 1 degree of longitude ~= 111320m there
    step_deg = spacing_m / 111320.0
    return [(i * step_deg, 0.0) for i in range(n)]


def test_resample_decimates_a_dense_trace_to_target_spacing():
    dense = _line_points(300, spacing_m=3.0)  # ~900m total, 3m/point
    out = resample_trace(dense, resample_m=25.0)
    assert out[0] == dense[0]
    assert out[-1] == dense[-1]
    for a, b in zip(out, out[1:]):
        d = haversine_m(a[0], a[1], b[0], b[1])
        assert d >= 25.0 - 1e-6 or (a, b) == (out[-2], out[-1])
    assert len(out) < len(dense)


def test_resample_leaves_a_sparse_trace_unchanged():
    sparse = _line_points(5, spacing_m=100.0)  # 100m/point, sparser than the 25m target
    out = resample_trace(sparse, resample_m=25.0)
    assert out == sparse


def test_resample_preserves_endpoints_of_a_dense_trace():
    dense = _line_points(50, spacing_m=5.0)
    out = resample_trace(dense, resample_m=25.0)
    assert out[0] == dense[0]
    assert out[-1] == dense[-1]


def test_inmem_map_round_trips_lon_lat_through_the_lat_lon_boundary():
    from lib.hmm_match import build_inmem_map

    nodes = {0: (11.123, 47.456), 1: (11.130, 47.460)}
    m = build_inmem_map(nodes)
    lat0, lon0 = m.node_coordinates(0)
    assert (lon0, lat0) == nodes[0]
    lat1, lon1 = m.node_coordinates(1)
    assert (lon1, lat1) == nodes[1]
