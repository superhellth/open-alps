"""Scrapes alpenvereinaktiv.com multi-day tour pages for their per-leg (Etappe) tour IDs, so
each leg's GPX can be downloaded separately (see tools/fetch_alpenvereinaktiv_tour.py). The
tour's own GPX export is one unbroken track for the whole route with no leg boundaries - the
stage <select> on the tour page is the only place the leg split is exposed."""

import re

_STAGE_OPTION_RE = re.compile(r'<option value="(\d+)">Etappe (\d+):')
_TOUR_ID_RE = re.compile(r"/tour/[^/]+/(\d+)/")


def parse_stage_ids(html: str) -> list:
    """[(leg_number, tour_id), ...] sorted by leg number. Empty for a single-leg tour, which
    has no stage <select> at all."""
    stages = [(int(num), tid) for tid, num in _STAGE_OPTION_RE.findall(html)]
    return sorted(stages, key=lambda s: s[0])


def extract_tour_id(url: str) -> str:
    match = _TOUR_ID_RE.search(url)
    if not match:
        raise ValueError(f"could not find tour id in url: {url}")
    return match.group(1)


def gpx_download_url(tour_id: str) -> str:
    return f"https://www.alpenvereinaktiv.com/de/download.tour.gpx?i={tour_id}&project=alpenverein"
