# Hut catalog uses a rectangular bbox, pulling in huts outside AT+Bavaria trail coverage

**Priority:** Medium

`fetch_huts.py` filters the Alpenverein hut catalog to `pipeline.config.json`'s rectangular
`bbox` (8.9–17.2°E, 46.3–50.6°N), not to actual country borders. That rectangle also covers
slices of South Tyrol/Dolomites (Italy), the Julian Alps/Karawanken (Slovenia), and Graubünden
(Switzerland). Trail data, by contrast, comes only from the `austria-latest` + `bayern-latest`
Geofabrik extracts, which *are* clipped to real admin boundaries — so huts in those
neighboring-country slices get pulled into `huts.geojson` with zero trail data anywhere near
them.

**Concrete evidence:** the 2026-09-03 `check_graph_building` quality run
(`data/quality/graph_building.json`) flagged 725 `snap_health` failures, of which 205 are
hub_type 0 (HUT) with reason `gap_too_far`. Every one of those 205 is a hut physically outside
Austria/Bavaria — e.g. **Schlernhaus, Grasleitenhütte, Toni-Demetz-Hütte** (South Tyrol),
**Frischaufov dom, Kranjska koča, Planinski dom Košenjak** (Slovenia), **Sasc Fura Hütte,
Marco-e-Rosa Hütte** (Switzerland/Italy border) — with `gap_m` (distance to nearest trail data)
ranging from 161 m (just over the border) to **69 km** (deep in Italy/Slovenia).

This is a **data-coverage/scoping problem, not a snapping bug** — no amount of retuning
`maxSnapM`/`maxSnapAscentM` fixes a hut with no trail data anywhere near it. It has existed since
`fetch_huts.py` was written; it surfaced clearly now only because `e8603b0` (fixed spurious
`vertical_offset` false positives) stopped drowning it out in the `snap_health` report.

**Fix options:**
- Filter `fetch_huts.py`'s hut catalog to an actual AT+Bavaria polygon (mirroring
  `compute_hub_range.py`'s hub-range-polygon approach) instead of the coarse bbox.
- Or: keep the bbox fetch, but have the data-quality layer classify/suppress these as
  "known out-of-coverage" rather than reporting them as unexplained `gap_too_far` snap failures.
- Scope will only grow — this needs deciding before pipeline scope extends past AT+Bayern
  (`pipeline/CLAUDE.md`'s "Current status" note).
