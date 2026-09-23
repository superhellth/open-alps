"""Builds hut-days.csv (one row per hut and calendar day, all seasons) from raw calendars."""
from __future__ import annotations

from collections import Counter

import pandas as pd

import common
import hutdays


def main(argv=None) -> None:
    huts = common.read_json(common.OUT / "huts.json")["huts"]
    frames = []
    statuses: Counter = Counter()
    for season, s in common.SEASONS.items():
        for h in huts:
            if h["error"]:
                continue
            rec = common.read_json(common.OUT / "raw" / f"calendar-{season}" / f"{h['ohrs_id']}.json")
            statuses.update(r["hutStatus"] for r in rec["body"])
            df = hutdays.hut_days(rec["body"], h["capacity"], h["ohrs_id"], s.start, s.end)
            df.insert(1, "season", season)
            frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(common.OUT / "hut-days.csv", index=False)
    print(f"{len(out)} hut-days; hutStatus values: {dict(statuses)}")


if __name__ == "__main__":
    main()
