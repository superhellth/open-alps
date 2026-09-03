import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import grading  # noqa: E402


def test_explicit_sac_scale_wins():
    g = grading.classify_way({"highway": "path", "sac_scale": "alpine_hiking"})
    assert g.sac_rank == 4
    assert g.tier == grading.TIER_EXPLICIT


def test_track_is_physically_implied_t1_even_at_grade5():
    g = grading.classify_way({"highway": "track", "tracktype": "grade5"})
    assert g.sac_rank == 1
    assert g.tier == grading.TIER_INFERRED


def test_steps_imply_t2():
    assert grading.classify_way({"highway": "steps"}).sac_rank == 2


def test_paved_path_implies_t1():
    g = grading.classify_way({"highway": "path", "surface": "asphalt"})
    assert g.sac_rank == 1
    assert g.tier == grading.TIER_INFERRED


def test_bare_path_is_ungraded():
    g = grading.classify_way({"highway": "path"})
    assert g.sac_rank == -1
    assert g.tier == grading.TIER_UNGRADED


def test_good_trail_visibility_is_not_an_upgrade():
    # rejected as an upgrade signal: subjective, on only 8.8% of untagged paths (spec C4)
    g = grading.classify_way({"highway": "path", "trail_visibility": "excellent"})
    assert g.tier == grading.TIER_UNGRADED


def test_downgrade_tags_hard_exclude_from_constrained_rows():
    assert grading.excluded_from_constrained({"highway": "path", "trail_visibility": "horrible"})
    assert grading.excluded_from_constrained({"highway": "path", "informal": "yes"})
    assert grading.excluded_from_constrained({"highway": "path", "ladder": "yes"})
    assert grading.excluded_from_constrained({"highway": "track", "access": "private"})
    assert not grading.excluded_from_constrained({"highway": "path", "sac_scale": "hiking"})


def test_explicit_grade_still_excluded_by_a_downgrade_tag():
    # a downgrade is always honoured, even over an explicit sac_scale (spec C4, "asymmetric")
    assert grading.excluded_from_constrained(
        {"highway": "path", "sac_scale": "hiking", "trail_visibility": "no"}
    )


def test_access_no_is_impassable():
    assert grading.is_impassable({"highway": "service", "access": "no"})


def test_access_no_with_foot_override_is_passable():
    assert not grading.is_impassable({"highway": "service", "access": "no", "foot": "yes"})


def test_access_private_is_not_impassable():
    # unlike excluded_from_constrained, private tracks stay in the graph - see is_impassable's
    # docstring
    assert not grading.is_impassable({"highway": "track", "access": "private"})
