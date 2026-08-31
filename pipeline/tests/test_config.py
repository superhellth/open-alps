import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.pipeline import load_config  # noqa: E402


def test_config_has_no_road_penalty_factor():
    assert "roadPenaltyFactor" not in load_config()["graph"]


def test_tour_match_config_has_the_two_kept_thresholds():
    config = load_config()
    tm = config["tourMatch"]
    assert set(tm.keys()) == {"corridorBufferM", "lengthDivergenceRatio"}
    assert tm["corridorBufferM"] == 150.0
    assert tm["lengthDivergenceRatio"] == 2.0
