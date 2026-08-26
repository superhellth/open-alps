import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))

import routing_probe  # noqa: E402


def test_substitution_is_geometry_identity_not_cost_equality():
    # a column earns its build cost by producing a DIFFERENT ROUTE, not a different number
    # (spec C2) - equal-cost different geometry is still a substitution
    baseline = [(0.0, 0.0), (0.001, 0.0), (0.002, 0.0)]
    same = [(0.0, 0.0), (0.001, 0.0), (0.002, 0.0)]
    other = [(0.0, 0.0), (0.001, 0.001), (0.002, 0.0)]
    assert not routing_probe.is_substitution(baseline, same)
    assert routing_probe.is_substitution(baseline, other)


def test_blocker_classification_separates_ungraded_from_difficulty():
    # spec H.3 - the one open question in the passability design
    assert routing_probe.classify_blocker(True, False) == "ungraded"
    assert routing_probe.classify_blocker(False, True) == "difficulty"
    assert routing_probe.classify_blocker(False, False) == "disconnected"
