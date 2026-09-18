import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.pipeline import load_config  # noqa: E402


def test_config_has_no_road_penalty_factor():
    assert "roadPenaltyFactor" not in load_config()["graph"]


def test_quality_section_has_expected_defaults():
    config = load_config()
    q = config["quality"]
    assert q["maxFlaggedRows"] == 500
    assert q["elevation"]["plausibleRangeM"] == [-50, 4300]
    assert q["elevation"]["minSpeedMs"] == 0.05
    assert q["graphBuilding"]["maxVertexGapM"] == 500
    assert q["graphBuilding"]["snapToleranceM"] == 5
    assert q["graphBuilding"]["minRetraceSeparationM"] == 200
    assert q["graphBuilding"]["ascentCapM"] == 5000
    assert q["postprocessing"]["minLengthM"] == 300
    assert q["postprocessing"]["straightnessThreshold"] == 0.97
    assert q["postprocessing"]["maxPointsForStraightnessFlag"] == 4


def test_quality_dir_constant_exists():
    from lib.pipeline import DATA_DIR, QUALITY_DIR
    assert QUALITY_DIR == DATA_DIR / "quality"
