import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.pipeline import load_config  # noqa: E402


def test_config_has_no_road_penalty_factor():
    assert "roadPenaltyFactor" not in load_config()["graph"]


def test_tour_match_config_has_all_four_thresholds():
    config = load_config()
    tm = config["tourMatch"]
    assert tm["fragmentBreakM"] == 150.0
    assert tm["corridorBufferM"] == 150.0
    assert tm["maxHutTraceM"] == 250.0
    assert tm["lengthDivergenceRatio"] == 2.0
