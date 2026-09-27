"""Official-tour hut order, stage distance and validation of the API order against the pipeline's tours."""
from __future__ import annotations

import re

MIN_SHARED = 3


def load_tours(tours: list[dict], huts: list[dict]) -> list[dict]:
    """Tours with at least one hut; `ohrs[i]` is the OHRS id of `guids[i]`, None for a GUID without a hut."""
    by_guid = {g.upper(): h["ohrs_id"] for h in huts for g in h["guids"]}
    out = []
    for i, t in enumerate(tours):
        if not t["guids"]:
            continue
        out.append({"name": t["name"] or f"tour-{i}", "circular": bool(t["circular"]),
                    "guids": t["guids"], "ohrs": [by_guid.get(g) for g in t["guids"]]})
    return out


def positions(tour: dict) -> dict[int, int]:
    """OHRS id to first index in the tour's order."""
    pos: dict[int, int] = {}
    for i, o in enumerate(tour["ohrs"]):
        if o is not None:
            pos.setdefault(o, i)
    return pos


def stage_distance(i: int, j: int, n: int, circular: bool) -> int:
    """Nights between two positions of a tour with n huts; a circular tour takes the shorter way round."""
    d = abs(i - j)
    return min(d, n - d) if circular else d


def _norm(name: str) -> str:
    return re.sub(r"[^a-zäöüß0-9]", "", name.lower())


def pipeline_sequence(tour: dict, hut_ids: list[str]) -> list[str]:
    """Hut GUIDs in leg order, consecutive repeats collapsed."""
    seq: list[str] = []
    for leg in tour["legs"]:
        for end in (leg["from"], leg["to"]):
            if end["type"] == "hut":
                g = hut_ids[end["id"]]
                if not seq or seq[-1] != g:
                    seq.append(g)
    return seq


def order_agreement(api: list[str], pipeline: list[str]) -> dict:
    """Compares the relative order of the huts both lists contain."""
    api_set, pipe_set = set(api), set(pipeline)
    a = [g for g in api if g in pipe_set]
    p = [g for g in pipeline if g in api_set]
    if len(a) < MIN_SHARED:
        verdict = "too_few_shared"
    elif a == p:
        verdict = "same"
    elif a == p[::-1]:
        verdict = "reversed"
    else:
        verdict = "disagree"
    return {"verdict": verdict, "shared": len(a),
            "api_only": [g for g in api if g not in pipe_set],
            "pipeline_only": [g for g in pipeline if g not in api_set]}


def validate_orders(tours: list[dict], pipeline_tours: list[dict], hut_ids: list[str]) -> list[dict]:
    """One row per pipeline tour: the API tour whose name starts with it and how the orders compare."""
    rows = []
    for p in pipeline_tours:
        match = [t for t in tours if _norm(t["name"]).startswith(_norm(p["name"]))]
        if len(match) != 1:
            rows.append({"pipeline": p["name"], "api": None, "verdict": "no_api_match"})
            continue
        rows.append({"pipeline": p["name"], "api": match[0]["name"],
                     **order_agreement(match[0]["guids"], pipeline_sequence(p, hut_ids))})
    return rows


def orders_validated(rows: list[dict]) -> bool:
    return all(r["verdict"] in ("same", "reversed") for r in rows)
