"""The variant grid (spec C2). Rows are hard ROUTING CONSTRAINTS; columns are what "best" means
among the paths that obey them. The axes do not interact.

Why rows are worth their build cost when a client-side filter is not: a per-edge filter can only
DELETE an edge. If the stored A->B path crosses T5 and the user caps at T3, filtering deletes A->B
entirely - even when a T3 path exists 400 m longer. Variants SUBSTITUTE. Measured: applying
sac_rank <= 3 to edges already inside a 12 km leg budget cuts 1,418 edges to 1,006 and leaves 23%
of huts with NO connection at all; under sac_rank <= 2, 39%.

Why columns are cheaper to justify: a column only earns its cost if its path DIFFERS from the
fastest one, otherwise the client re-sorts what it already holds. ASC_* is predicted near-redundant
(the speed model already prices climb steeply) and is not planned. ROAD_*, if the post-rebuild road
share justifies it, is a MULTIPLICATIVE penalty on the time of road-tagged segments (factor ~3-5) -
not lexicographic (buys 40 km detours), not additive time + lambda*road_m (lambda needs cross-unit
calibration). A multiplier is scale-free and its detour is bounded by m x the road's own time.
"""

from collections import namedtuple

import numpy as np

from lib import binfmt

# allow_ungraded defaults False for every existing row - only FAST_T3_UNGRADED sets it.
Variant = namedtuple("Variant", "code name max_sac_rank require_graded allow_ungraded",
                      defaults=(False,))

VARIANTS = {
    binfmt.VARIANT_FAST_ANY: Variant(binfmt.VARIANT_FAST_ANY, "FAST_ANY", None, False),
    binfmt.VARIANT_FAST_T2: Variant(binfmt.VARIANT_FAST_T2, "FAST_T2", 2, True),
    binfmt.VARIANT_FAST_T3: Variant(binfmt.VARIANT_FAST_T3, "FAST_T3", 3, True),
    # spec H fallback / findings doc §4: relaxes ONLY the ungraded_m==0 guarantee. Still forbids
    # T4+ terrain and via ferrata - FAST_T3's own strict definition is untouched, this is a
    # separate, honestly-labelled row for users who'd rather have a route than a guarantee.
    binfmt.VARIANT_FAST_T3_UNGRADED: Variant(
        binfmt.VARIANT_FAST_T3_UNGRADED, "FAST_T3_UNGRADED", 3, True, True,
    ),
}


def edge_mask(local_edges, variant):
    mask = np.ones(len(local_edges), dtype=bool)
    sac_rank = local_edges["sac_rank"]
    is_ungraded = sac_rank < 0
    if variant.require_graded:
        if variant.allow_ungraded:
            # constrained_ok is unconditionally False for every ungraded-tier edge (it folds
            # tier != ungraded together with via-ferrata/downgrade-tag exclusion into one flag),
            # so it can't tell "genuinely ungraded, otherwise fine" apart from "graded but
            # safety-excluded". Handled separately here: ungraded-tier edges are let through
            # (except via ferrata, always forbidden); a GRADED edge still needs constrained_ok -
            # a downgrade tag on a known grade is still honoured, only "we don't know the grade
            # at all" is relaxed by this row.
            mask &= ~local_edges["via_ferrata"]
            mask &= local_edges["constrained_ok"] | is_ungraded
        else:
            # constrained_ok already folds ungraded / via ferrata / downgrade tags, AND-ed along
            # every contracted chain (lib/contraction.py) - one bad segment poisons the edge.
            mask &= local_edges["constrained_ok"]
    if variant.max_sac_rank is not None:
        if variant.allow_ungraded:
            mask &= is_ungraded | (sac_rank <= variant.max_sac_rank)
        else:
            mask &= sac_rank >= 0          # spec C5: -1 never satisfies a ceiling
            mask &= sac_rank <= variant.max_sac_rank
    return mask


def enabled_variants(config):
    by_name = {v.name: v for v in VARIANTS.values()}
    return [by_name[n] for n in config["graph"]["variants"]]
