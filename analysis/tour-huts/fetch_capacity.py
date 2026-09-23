"""Fetches hutInfo (capacity, coordinates) for every hut in scope."""
from __future__ import annotations

import argparse
from collections import Counter

import common


def info_url(ohrs_id: int) -> str:
    return f"{common.OHRS}/api/v1/reservation/hutInfo/{ohrs_id}"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args(argv)
    feats = common.read_json(common.HUTS_GEOJSON)["features"]
    ids = common.hut_scope(feats)
    counts: Counter = Counter()
    for i in ids:
        path = common.OUT / "raw" / "hut-info" / f"{i}.json"
        counts[common.fetch_cached(path, lambda i=i: common.request_json(info_url(i)), args.refresh)] += 1
    print(f"hut-info for {len(ids)} huts: {dict(counts)}")


if __name__ == "__main__":
    main()
