"""Fetches the Alpenverein tour catalogue (26 tours) into raw/tours.json."""
from __future__ import annotations

import argparse
import re

import common


def parse_tours(payload: dict) -> list[dict]:
    """Tours as {name, guids, circular}; GUIDs keep their braces and are upper-cased, in the catalogue's order."""
    tours = []
    for feat in payload.get("features", []):
        a = feat["attributes"]
        guids = [g.upper() for g in re.findall(r"\{[^}]+\}", a.get("Huettenliste") or "")]
        tours.append({"name": a.get("Bezeichnung") or None, "guids": guids,
                      "circular": bool(a.get("Rundtour"))})
    return tours


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args(argv)
    path = common.OUT / "raw" / "tours.json"
    status = common.fetch_cached(
        path, lambda: common.request_json(common.TOURS_URL, method="POST"), args.refresh)
    print(f"tours: {status}")
    if status == "error":
        raise SystemExit(common.read_json(path)["error"])


if __name__ == "__main__":
    main()
