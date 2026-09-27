# open-alps

A map-first planner for multi-day hut tours in the Austrian and Bavarian Alps. Say how you get
there, how many nights and how long you want to walk each day; open-alps suggests hut-to-hut tours over
real trails, lets you reshape them stage by stage, checks bed availability for your dates and hands
you a share link.

Everything runs in the browser off static files. There is no backend: tour search happens in a Web
Worker over a precomputed routing graph, and bed availability comes live from the Alpine Clubs'
public booking API.

## What it does

- **Discover** — say how you arrive (train, car, or from a village), how many stages, how long each
  day may be, and optionally cap SAC grade, ascent per stage, maximum elevation, via ferratas and
  hut type (serviced/self-catering). Results appear as signposts on the map and as a ranked list.
- **Customize** — turn a suggestion into a trip, then swap huts, extend or trim either end, or change
  the start and exit points. Each stage shows walking time, distance, ascent/descent and a height
  profile of the whole tour.
- **Plan nights** — choose an arrival day and see, per night, whether the hut has beds free, with a
  booking link for each hut. Huts that only take direct bookings are marked as such.
- **Take along** — trips autosave locally ("Meine Touren") and can be shared as a link.

Coverage: the trail network of Austria and Bavaria, with the huts from the Alpenverein hut
directory (ÖAV/DAV and other operators) that lie inside it.

## Repository layout

| Path | What lives there |
| --- | --- |
| `huts/` | The React + Vite + Leaflet app (MUI, TypeScript). |
| `pipeline/` | Offline Python pipeline: OSM trails + DEM → hut-to-hut routing graph, start-point approaches, elevation profiles and map tiles. A [doit](https://pydoit.org) task DAG. |
| `data/` | Pipeline inputs and outputs (gitignored, disposable). |
| `docs/` | Data source reference, payload contract, backlog, design specs. |
| `analysis/` | One-off studies outside the pipeline DAG (e.g. hut booking patterns). |

## Running the app

```bash
cd huts
npm install
npm run dev
```

The app loads its graph, hut, station and parking data from `huts/public/data/`. **Those files are
not checked in** — on a fresh clone the directory is empty until the pipeline has run once (see
below). Its last task, `copy_public_data`, fills it.

Other scripts: `npm test` (Vitest), `npm run typecheck`, `npm run lint` (oxlint), `npm run build`.
The tests include architecture and design-token checks that enforce import direction and forbid
hardcoded colors/spacing.

The `#admin` route is an internal debugging view of the raw routing graph, not part of the product.

## Building the data

The pipeline downloads everything it needs from public sources and is fully reproducible:
delete `data/` and rerun to get the same result (modulo upstream changes). All tunables — regions,
trail tag filter, graph limits, DEM providers, tile zooms — live in
`pipeline/pipeline.config.json`.

**Setup** (Linux, macOS or WSL) — the environment is managed with [pixi](https://pixi.sh):

```bash
curl -fsSL https://pixi.sh/install.sh | sh
cd pipeline
pixi install
```

**Run**:

```bash
pixi run doit list          # every task and whether it is up to date
pixi run doit info <task>   # why a task would (not) run
pixi run doit               # run everything that is stale
pixi run test               # fast unit tests, no data needed
```

A first full run takes hours (hut snapping alone is ~1 h; measured timings accumulate in
`data/timings.jsonl`). Read `pipeline/README.md` before running anything — it documents every task,
every config key and the native-Windows setup.

## Data sources

| Data | Source |
| --- | --- |
| Hut master data and coordinates | Alpenverein ArcGIS feature layer (public, no auth) |
| Bed availability (live, in the browser) | Alpenverein online booking system (OHRS) |
| Trails, train stations, parking | [OpenStreetMap](https://www.openstreetmap.org/copyright) via Geofabrik extracts (ODbL) |
| Elevation | Copernicus GLO-30, BEV DGM (Austria), Bavarian DGM5 |
| Base map | [OpenTopoMap](https://opentopomap.org) (CC-BY-SA) |

API details and gotchas: `docs/alpenverein-api.md`. Payload format the app reads:
`docs/tour-suggestion-payload.md`.

## Further reading

- `pipeline/README.md` — pipeline tasks, config and setup
- `docs/backlog.md` — open cross-cutting problems
- `docs/known-data-issues.md` — known data quality issues
- `docs/superpowers/STATUS.md` — index of design specs and their status
- `.claude/CLAUDE.md` — detailed app architecture
