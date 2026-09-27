"""Paths, seasons, HTTP and caching helpers shared by the tour-huts study scripts."""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import date
from pathlib import Path
from typing import Callable, NamedTuple

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "analysis" / "tour-huts"
HUTS_GEOJSON = ROOT / "huts" / "public" / "data" / "huts.geojson"
OHRS = "https://www.hut-reservation.org"
TOURS_URL = "https://caa.alpenverein.at/service/server/tourSelection.php"
USER_AGENT = "open-alps-analysis/1.0"
REQUEST_GAP_S = 0.3


class Season(NamedTuple):
    start: date
    end: date
    fetch_end: date


SEASONS: dict[int, Season] = {
    2025: Season(date(2025, 5, 1), date(2025, 10, 31), date(2025, 10, 31)),
    2026: Season(date(2026, 5, 1), date(2026, 9, 23), date(2026, 10, 10)),
}


def fmt_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def read_json(path: Path):
    return json.loads(path.read_text())


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False))


def request_json(url, body=None, *, method=None, retries=3, sleep=time.sleep,
                 urlopen=urllib.request.urlopen) -> dict:
    """One JSON request with retries and backoff; returns an ok record or an error record."""
    method = method or ("GET" if body is None else "POST")
    data = None if body is None else json.dumps(body).encode()
    if method == "POST" and data is None:
        data = b""
    headers = {"User-Agent": USER_AGENT}
    if body is not None:
        headers["Content-Type"] = "application/json"
    error = ""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data, headers, method=method)
            with urlopen(req, timeout=30) as resp:
                return {"ok": True, "body": json.load(resp)}
        except Exception as e:  # noqa: BLE001 - any failure becomes a stored error record
            error = f"{type(e).__name__}: {e}"[:200]
            sleep(1 + attempt * 2)
    return {"ok": False, "error": error}


def fetch_cached(path: Path, fetch: Callable[[], dict], refresh=False,
                 gap=REQUEST_GAP_S, sleep=time.sleep) -> str:
    """Runs `fetch` and stores its record unless an ok record is already on disk."""
    if path.exists() and not refresh and read_json(path).get("ok"):
        return "cached"
    rec = fetch()
    write_json(path, rec)
    sleep(gap)
    return "ok" if rec["ok"] else "error"


def hut_scope(features: list[dict]) -> list[int]:
    """Sorted unique OHRS ids of every hut feature that has one."""
    return sorted({int(f["properties"]["ohrsHutId"]) for f in features
                   if f["properties"].get("ohrsHutId")})
