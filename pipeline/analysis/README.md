# pipeline/analysis/ — standalone measurement scripts

Read-only scripts that answer a specific question about the pipeline with hard numbers, so a
design decision is made from measurement instead of from a plausible-sounding story about where
the cost is. Not part of the `doit` task DAG (`pipeline/dodo.py`), never imported by anything
under `phases/`, run by hand:

```bash
python pipeline/analysis/<script>.py
```

**The contract every script here obeys:**

- **Import and call the real phase functions.** Never reimplement the logic under measurement — a
  reimplementation drifts and then measures itself. `snap_stats.py` calls `build_hub_edges.py`'s
  `snap_hub_to_subgraph()`; `contraction_scaling.py` calls `lib/contraction.py`'s
  `contract_structural()`. Making a phase importable so this is possible is a legitimate
  refactor of that phase (see `build_base_graph.py`'s `stream_osm`/`contract`/`pack_and_write`
  split), but it must be behaviour-identical.
- **Never modify `phases/` or `dodo.py`.** Findings feed a spec or a plan; the code change is a
  separate commit, judged on its own.
- **Read already-persisted `data/` outputs.** These scripts assume the expensive phases have
  already run, and say so in their docstring under "Requires".
- **Write into `data/`** (gitignored), so nothing here dirties the tracked half of the repo. The
  numbers that matter get copied into a findings doc under `docs/superpowers/specs/`.
- **Print progress** as you go, `flush=True` — see the root `pipeline/CLAUDE.md`'s "Progress
  logging". These are run interactively and some take an hour.
- **State the runtime in the module docstring.** A script whose cost is unstated will be launched
  by someone who assumed it was cheap.

## `snap_stats.py` — how hubs attach to the base graph

Quantifies `snap_hub_to_subgraph()`'s three outcomes (existing-node, mid-chain split, unsnapped)
over the real hub set, and how many already-computed `hut_edges`/`start_edges` would lose an
endpoint if mid-chain snapping were replaced by a simpler node-or-drop rule.

Requires `data/osm/base_graph/`, plus `hut_edges/` + `start_edges/` for the edge-impact section.
Writes `data/analysis/snap_stats.json`.

## `reconstruct_raw_graph.py` — un-contract `base_graph/` back to raw

Rebuilds the pre-contraction node/edge arrays from the persisted `base_graph/`, by expanding each
chain edge back into its `u -> interior[...] -> v` segments. Exists so contraction can be measured
at any graph size without re-running `stream_osm` (914s per attempt, `data/timings.jsonl`).

Both a script (running it directly prints a size/consistency report) and a library
(`contraction_scaling.py` imports `reconstruct_raw` and `select_edges_in_cells`) — the only module
in this directory that is imported rather than only run.

**Timing fixture, not an equivalence fixture.** Topology, coordinates, per-segment distances,
`sac_rank` and `via_ferrata` are exact; per-segment *road* flags are not recoverable (162,169
chain edges are only partially road, and only the chain total `road_m` survives contraction), so
reconstructed `road_m` totals differ from the originals. Fine for measuring what contraction
costs; wrong for asserting that two graphs are the same graph.

## `contraction_scaling.py` — is `contract_structural` CPU-bound or memory-bound?

Contracts increasingly large, densest-cell-first *nested* subsets of the reconstructed raw graph
and records seconds-per-raw-edge next to peak RSS, to separate "the walk is slow" from "the box is
swapping". Flat µs/edge with RSS well under RAM means CPU-bound; µs/edge climbing as RSS
approaches RAM means memory-bound, and a parallelism fix would be aimed at the wrong bottleneck.
`--profile-fraction` swaps the sweep for one `cProfile` run at a small fraction, to attribute the
walk's cost to specific call sites.

Requires `data/osm/base_graph/`. Appends to `data/contraction_scaling.jsonl` (one JSON line per
subset, so a killed run keeps its completed measurements) and writes `data/contraction.prof`.

Background: `docs/superpowers/plans/2026-08-20-contraction-measurement-spike.md`, and the design
it was written to test, `docs/superpowers/specs/2026-08-20-tiled-contraction-design.md`.

## `grading_coverage.py` — how much of the network, and of the hut edges, is ungraded

Streams `trails.osm.pbf` once, classifies every way into the explicit / physically-implied /
ungraded tiers proposed in `docs/superpowers/specs/2026-08-22-tour-suggestion-backend.md` §C4, and
reports the tier mass **by length** network-wide *and* attributed onto the stored `hut_edges/`
paths by exact OSM-node-pair matching. The output that matters is the connectivity gate: how many
huts lose their last connection when the constrained rows' `ungraded_m == 0` rule is added on top
of a plain `sac_rank` cap. That is the cheap preview of the sizing probe's "ungraded blocker rate",
and a small value retires the fourth-passability-row risk before any constrained-routing code
exists.

The one script here whose classifier has no production counterpart to call — the rule is the thing
being proposed, not something under `phases/` to measure. If adopted, it moves into
`build_base_graph.py`'s way handler and this script should import it from there instead.

Requires `data/osm/trails.osm.pbf` and `data/osm/hut_edges/`; `--start-edges` also needs
`start_edges/`. Writes `data/analysis/grading_coverage.json`. **~20-25 min** (the osmium pass
dominates), peak RSS ~3-4 GB; `--no-attribution` drops to ~17 min and ~1 GB.

## `road_share.py` — is the `ROAD_*` variant column worth building?

`road_m / distance_m` distribution over the stored `hut_edges/` and `start_edges/` records,
length-weighted and cross-tabbed by `sac_rank`. Bounds the regression from dropping
`roadPenaltyFactor` (spec §A3), which currently has no number under it at all.

Measured under the *distance* cost with the penalty still active, so it is a **floor** — the
time-based cost both removes the penalty and rewards roads for being fast. Re-run unchanged after
the Part 1 rebuild for the real figure; the two runs are directly comparable.

Requires `hut_edges/records.npy` + `start_edges/records.npy`. Writes `data/analysis/road_share.json`.
Seconds.

## `payload_sizing.py` — how big are the three client payloads really?

Builds the spec §F hut-edge column set, the §E1 k-best-per-hut approach table, and the §E2
loop-closure reverse index for real — narrowing ids, laying columns out contiguously, gzipping with
and without a byte-shuffle filter — instead of multiplying a row count by an assumed row width.
Also reports how many huts still get `k` approaches once the `access` rule deletes private and
gated trailheads.

Every gzip figure is a floor: the four not-yet-computed columns are materialised as zeros, and the
variant copies are identical. `motor_vehicle` is not measurable — `fetch_stations_parking.py`'s
`keep_fields` does not let it through, which the script reports as a build prerequisite rather than
silently ignoring.

Requires `hut_edges/records.npy`, `start_edges/records.npy`, `parking.geojson`, `stations.geojson`.
Writes `data/analysis/payload_sizing.json`. Seconds.
