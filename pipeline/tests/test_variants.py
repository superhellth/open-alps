import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import binfmt, variants  # noqa: E402


def _edges(**cols):
    n = len(next(iter(cols.values())))
    arr = np.zeros(n, dtype=binfmt.EDGE_DTYPE)
    for k, v in cols.items():
        arr[k] = v
    return arr


def test_unconstrained_row_keeps_everything():
    edges = _edges(sac_rank=[-1, 2, 6], constrained_ok=[False, True, True],
                   via_ferrata=[False, False, True])
    mask = variants.edge_mask(edges, variants.VARIANTS[binfmt.VARIANT_FAST_ANY])
    assert mask.tolist() == [True, True, True]


def test_t3_row_deletes_ungraded_over_grade_and_via_ferrata():
    edges = _edges(sac_rank=[-1, 2, 3, 4, 3],
                   constrained_ok=[False, True, True, True, False],
                   via_ferrata=[False, False, False, False, True])
    mask = variants.edge_mask(edges, variants.VARIANTS[binfmt.VARIANT_FAST_T3])
    #                       ungraded  T2    T3    T4     via ferrata
    assert mask.tolist() == [False, True, True, False, False]


def test_t2_row_is_strictly_tighter_than_t3():
    edges = _edges(sac_rank=[2, 3], constrained_ok=[True, True], via_ferrata=[False, False])
    t2 = variants.edge_mask(edges, variants.VARIANTS[binfmt.VARIANT_FAST_T2])
    t3 = variants.edge_mask(edges, variants.VARIANTS[binfmt.VARIANT_FAST_T3])
    assert (t2 <= t3).all()


def test_constrained_rows_cannot_admit_an_ungraded_edge():
    # spec C4: `ungraded_m == 0` is what lets the product claim every metre is graded T3 or
    # easier. A row admitting one ungraded edge silently breaks that claim.
    edges = _edges(sac_rank=[2], constrained_ok=[False], via_ferrata=[False], ungraded_m=[500.0])
    for code in (binfmt.VARIANT_FAST_T2, binfmt.VARIANT_FAST_T3):
        assert not variants.edge_mask(edges, variants.VARIANTS[code])[0]


def test_untagged_rank_can_never_satisfy_a_ceiling():
    # spec C5: -1 is "unknown", not "easy" - a <= comparison alone would admit it
    edges = _edges(sac_rank=[-1], constrained_ok=[True], via_ferrata=[False])
    assert not variants.edge_mask(edges, variants.VARIANTS[binfmt.VARIANT_FAST_T3])[0]


def test_fast_t3_ungraded_permits_ungraded_terrain_ft3_forbids():
    # findings doc: FAST_T3_UNGRADED relaxes ONLY the ungraded_m==0 guarantee, not the ceiling
    edges = _edges(sac_rank=[-1], constrained_ok=[False], via_ferrata=[False])
    t3 = variants.edge_mask(edges, variants.VARIANTS[binfmt.VARIANT_FAST_T3])
    t3u = variants.edge_mask(edges, variants.VARIANTS[binfmt.VARIANT_FAST_T3_UNGRADED])
    assert t3.tolist() == [False]
    assert t3u.tolist() == [True]


def test_fast_t3_ungraded_still_forbids_via_ferrata_and_t4_plus():
    edges = _edges(sac_rank=[-1, -1, 4], constrained_ok=[False, False, True],
                   via_ferrata=[True, False, False])
    mask = variants.edge_mask(edges, variants.VARIANTS[binfmt.VARIANT_FAST_T3_UNGRADED])
    #                    via ferrata (even though ungraded)  ungraded, ok   T4 graded, over ceiling
    assert mask.tolist() == [False, True, False]


def test_fast_t3_ungraded_still_forbids_a_graded_edge_excluded_by_downgrade_tag():
    # a KNOWN grade with a downgrade tag (e.g. trail_visibility=horrible) is still safety-excluded
    # - only the "we don't know the grade at all" case is relaxed by this row
    edges = _edges(sac_rank=[2], constrained_ok=[False], via_ferrata=[False])
    mask = variants.edge_mask(edges, variants.VARIANTS[binfmt.VARIANT_FAST_T3_UNGRADED])
    assert mask.tolist() == [False]
