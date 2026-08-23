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

Variant = namedtuple("Variant", "code name max_sac_rank require_graded")

VARIANTS = {
    binfmt.VARIANT_FAST_ANY: Variant(binfmt.VARIANT_FAST_ANY, "FAST_ANY", None, False),
    binfmt.VARIANT_FAST_T2: Variant(binfmt.VARIANT_FAST_T2, "FAST_T2", 2, True),
    binfmt.VARIANT_FAST_T3: Variant(binfmt.VARIANT_FAST_T3, "FAST_T3", 3, True),
}


def edge_mask(local_edges, variant):
    mask = np.ones(len(local_edges), dtype=bool)
    if variant.require_graded:
        # constrained_ok already folds ungraded / via ferrata / downgrade tags, AND-ed along
        # every contracted chain (lib/contraction.py) - one bad segment poisons the edge.
        mask &= local_edges["constrained_ok"]
    if variant.max_sac_rank is not None:
        mask &= local_edges["sac_rank"] >= 0          # spec C5: -1 never satisfies a ceiling
        mask &= local_edges["sac_rank"] <= variant.max_sac_rank
    return mask


def enabled_variants(config):
    by_name = {v.name: v for v in VARIANTS.values()}
    return [by_name[n] for n in config["graph"]["variants"]]
