import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from lib.hubs import HUB_TYPE_JSON_NAMES  # noqa: E402
from graph_building import match_tour_edges as mte  # noqa: E402

_TYPE_BY_NAME = {v: k for k, v in HUB_TYPE_JSON_NAMES.items()}
_CASES = json.loads((Path(__file__).parent / "fixtures" / "snap_cases.json").read_text())["cases"]


def _hubs(raw):
    return [{"id": h["id"], "type": _TYPE_BY_NAME[h["type"]], "lon": h["lon"], "lat": h["lat"], "name": ""}
            for h in raw]


def _key(hub):
    return {"id": hub["id"], "type": HUB_TYPE_JSON_NAMES[hub["type"]]}


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_resolve_endpoint_matches_shared_fixture(case):
    hubs = _hubs(case["hubs"])
    huts_only = [h for h in hubs if h["type"] == binfmt.TYPE_HUT]
    chosen, nearest, dist = mte._resolve_endpoint(
        hubs, huts_only, tuple(case["point"]), case["maxSnapM"], case["requireHut"])
    exp = case["expect"]
    assert (None if chosen is None else _key(chosen)) == exp["chosen"]
    assert (None if nearest is None else _key(nearest)) == exp["nearest"]
    if exp["nearestDistM"] is not None:
        assert dist == pytest.approx(exp["nearestDistM"], abs=0.5)
