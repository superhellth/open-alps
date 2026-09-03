"""Per-way passability grading (spec 2026-08-22-tour-suggestion-backend.md C4).

sac_scale is absent on most of the network, and sac_rank is a MAX over a path with untagged
encoded as -1, which max ignores - so an edge can contain kilometres of ungraded terrain and
still report sac_rank 2. Under a user-stated difficulty ceiling that is a safety defect, not an
accuracy one. This module gives every way a TIER as well as a rank, so "ungraded" becomes a
positive fact that can be summed along a path (ungraded_m) instead of a silence.

Inference is asymmetric on purpose: UPGRADES require physics (a tag that makes alpine terrain
impossible by construction); DOWNGRADES are always honoured. Measured 2026-08-21 over
data/osm/austria-trails.osm.pbf (2.33M ways / 23.1M segments): the implication table below covers
91.3% of untagged segment mass, leaving genuinely unknown terrain at 7.9% of the network - not the
95% a naive sac_scale-coverage figure suggests.
"""

from collections import namedtuple

WayGrade = namedtuple("WayGrade", "sac_rank tier")

TIER_EXPLICIT = "explicit"
TIER_INFERRED = "inferred"
TIER_UNGRADED = "ungraded"

SAC_SCALE_RANK = {
    "strolling": 0, "hiking": 1, "mountain_hiking": 2, "demanding_mountain_hiking": 3,
    "alpine_hiking": 4, "demanding_alpine_hiking": 5, "difficult_alpine_hiking": 6,
}

# highway value -> implied rank. Car-drivable or built surfaces only; each entry is a
# construction fact, not a guess about terrain.
IMPLIED_BY_HIGHWAY = {
    "residential": 1, "service": 1, "unclassified": 1, "tertiary": 1,
    "track": 1,      # including tracktype=grade5 - still a vehicle track
    "footway": 1,
    "steps": 2,
}
PAVED_SURFACES = {"asphalt", "paving_stones", "concrete"}

_BAD_VISIBILITY = {"bad", "horrible", "no"}
_BLOCKED_ACCESS = {"private", "no"}
_FOOT_OVERRIDE = {"yes", "permissive", "designated"}


def is_impassable(tags: dict) -> bool:
    """access=no (closed paths, restricted service tunnels/tracks) with no foot-specific
    override - these aren't legal or physical hiking routes at all and must never enter the
    graph in any variant, unlike excluded_from_constrained's difficulty-based exclusions.
    access=private is left alone: in this dataset it's routinely used for alpine hut-access
    tracks that are legally private for vehicles but walkable, so excluding it would drop real
    approaches, not just closed ones."""
    return tags.get("access", "") == "no" and tags.get("foot", "") not in _FOOT_OVERRIDE


def classify_way(tags: dict) -> WayGrade:
    explicit = SAC_SCALE_RANK.get(tags.get("sac_scale", ""))
    if explicit is not None:
        return WayGrade(explicit, TIER_EXPLICIT)
    highway = tags.get("highway", "")
    implied = IMPLIED_BY_HIGHWAY.get(highway)
    if implied is not None:
        return WayGrade(implied, TIER_INFERRED)
    if highway == "path" and tags.get("surface", "") in PAVED_SURFACES:
        return WayGrade(1, TIER_INFERRED)
    return WayGrade(-1, TIER_UNGRADED)


def excluded_from_constrained(tags: dict) -> bool:
    """Hard-exclude from every constrained row, regardless of grade. A downgrade signal always
    wins: the constrained rows exist to support the claim "every metre of this route is graded T3
    or easier", and that claim cannot survive a ladder or an unmarked line."""
    if tags.get("trail_visibility", "") in _BAD_VISIBILITY:
        return True
    if tags.get("informal", "") == "yes" or tags.get("ladder", "") == "yes":
        return True
    if tags.get("access", "") in _BLOCKED_ACCESS:
        return True
    return False
