"""Outdooractive geometry helpers shared by match_tour_edges.py's OA-sourced corridor input
(pipeline/analysis/2026-08-30-tour-reproducibility.md Task 4) and
pipeline/analysis/oa_corridor_spike.py's measurement of it (spec 2026-08-29-official-tours-
integration-design.md sec 2.7). alpenvereinaktiv.com is an Outdooractive white-label - no auth,
CORS *, `display=verbose` is what makes the response carry `geoJson` at all
(docs/www.alpenvereinaktiv.com.har)."""

import json
import re
import time
import urllib.request
from pathlib import Path

OA_ENDPOINT = "https://www.alpenvereinaktiv.com/api/v2/project/alpenverein/contents/{ids}/"
OA_KEY = "RXCRENVR-EMWGKTZ4-4OSSWDJU"
OA_QUERY = "?jsapi=1&key={key}&lang=de&display=verbose&format=json"
OA_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36")

# alpenvereinaktiv tour-page URL -> tour id. Anchored on the alpenvereinaktiv host deliberately:
# some tours link to a DIFFERENT Outdooractive project (e.g. touren.montafon.at) whose ids do not
# resolve under project/alpenverein, so a looser pattern would silently mismatch. Captures the
# LAST digits-only path segment (not the first) so a URL with extra intervening segments (a stage
# id after a parent id, e.g. "thw/12345/6789/") still resolves to the trailing, most-specific id.
OA_URL_RE = re.compile(r"alpenvereinaktiv\.com/de/tour/[^\"'<>\s]*/(\d+)/?(?=[\"'<>\s#]|$)")


def oa_ids_by_tour(tours: list) -> dict:
    """{tourId: outdooractive_id} for the tours whose own homepage field carries one."""
    out = {}
    for tour in tours:
        match = OA_URL_RE.search(tour.get("homepage") or "")
        if match:
            out[tour["tourId"]] = match.group(1)
    return out


def oa_chain(content: dict) -> list:
    """The tour's line as the 2-D (lon, lat) tuples lib/tour_geometry.py works in. OA ships
    [lon, lat, ele] triples; the third component is dropped rather than carried - elevation here
    is OA's, not our DEM's, and every downstream consumer (assign_hut_position, corridor_bounds,
    haversine_m) indexes [0]/[1] only."""
    geo = content.get("geoJson") or {}
    if geo.get("type") != "LineString":
        return []
    return [(p[0], p[1]) for p in geo["coordinates"]]


def fetch_oa_contents(oa_ids: list, cache_path: Path, allow_fetch: bool) -> dict:
    """{oa_id: content} from `cache_path`, fetching once (one batched request) if it's missing.
    The endpoint drops ids it cannot serve SILENTLY - 41 stage ids came back as 39 objects, no
    error, no null - so callers must diff requested against returned rather than trusting the
    count."""
    cache_path = Path(cache_path)
    if cache_path.exists():
        with open(cache_path, encoding="utf-8") as fh:
            cached = json.load(fh)
        if all(i in cached for i in oa_ids):
            print(f"oa: {len(cached)} tours from cache {cache_path}", flush=True)
            return cached
        print(f"oa: cache is missing {sorted(set(oa_ids) - set(cached))}", flush=True)
    if not allow_fetch:
        raise SystemExit(f"--no-fetch and {cache_path} does not cover {len(oa_ids)} ids")

    url = OA_ENDPOINT.format(ids=",".join(oa_ids)) + OA_QUERY.format(key=OA_KEY)
    print(f"oa: GET {len(oa_ids)} ids ...", flush=True)
    started = time.time()
    request = urllib.request.Request(url, headers={"accept": "application/json",
                                                     "user-agent": OA_UA})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    contents = {c["id"]: c for c in payload["answer"]["contents"]}
    missing = [i for i in oa_ids if i not in contents]
    print(f"oa: {len(contents)}/{len(oa_ids)} in {time.time() - started:.1f}s"
          + (f", MISSING {missing}" if missing else ""), flush=True)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as fh:
        json.dump(contents, fh)
    return contents
