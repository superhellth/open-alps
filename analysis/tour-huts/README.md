# Tour-hut booking study

Are huts on official Alpenverein tours booked more than other huts? Design:
`docs/superpowers/specs/2026-09-23-tour-hut-booking-study-design.md`. Results: `docs/tour-hut-booking-analysis.md`.

Outputs go to `data/analysis/tour-huts/` (gitignored). This code is independent of `pipeline/` and doit.

```bash
cd analysis/tour-huts
pixi install
pixi run pytest                        # no network needed
pixi run python fetch_tours.py         # ~1 request
pixi run python fetch_capacity.py      # ~239 requests, 0.3 s apart
pixi run python fetch_calendars.py     # ~480 requests; --season 2025|2026, --refresh
pixi run python link_huts.py           # huts.json
pixi run python build_hut_days.py      # hut-days.csv
pixi run python analyze.py             # results.json, plots/
pixi run python run_bottleneck.py      # bottleneck-results.json, bottleneck-candidates.csv, plots/ (no network)
```

The bottleneck study (docs/superpowers/specs/2026-09-23-tour-bottleneck-design.md) reads hut-days.csv, huts.json and raw/tours.json; it needs no new fetch.

Fetch scripts skip files that already hold an ok record and retry error records. `--refresh` refetches all.
Requests need an explicit `User-Agent`: Python's default one gets HTTP 403.
