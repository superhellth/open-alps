import json

import numpy as np

import approach_time


def test_din_minutes_matches_din_33466():
    # 4 km flat: t_h = 1 h, t_v = 0 -> 1 h
    assert approach_time.din_minutes(4000, 0, 0) == 60
    # 4 km, +300 m: t_h = 1, t_v = 1 -> 1 + 0.5 = 1.5 h
    assert approach_time.din_minutes(4000, 300, 0) == 90


def test_approach_minutes_takes_min_per_hut():
    hut_id = np.array([0, 0, 1], dtype="<u2")
    dist = np.array([4000, 2000, 8000], dtype="<f4")
    asc = np.zeros(3, dtype="<f4")
    desc = np.zeros(3, dtype="<f4")
    blob = b""
    cols = {}
    for name, arr in [("hut_id", hut_id), ("distance_m", dist), ("ascent_m", asc), ("descent_m", desc)]:
        cols[name] = {"dtype": arr.dtype.str.lstrip("<|"), "offset": len(blob)}
        blob += arr.tobytes()
    manifest = {"rows": 3, "columns": cols}
    out = approach_time.approach_minutes(manifest, blob, ["{aaa}", "{bbb}"])
    assert out == {"{AAA}": 30.0, "{BBB}": 120.0}
