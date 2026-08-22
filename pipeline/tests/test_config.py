import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.pipeline import load_config  # noqa: E402


def test_config_has_no_road_penalty_factor():
    assert "roadPenaltyFactor" not in load_config()["graph"]
