# Approach Table: Duration/Source-Type/Variant Matrix — Design

**Problem:** `select_approaches` (`pipeline/phases/postprocessing/build_approach_table.py:84-106`)
takes each hut's top-`k` approach candidates by DIN duration, then reserves one slot per missing
source type by overwriting `selected[-1]`. When two or more types are missing from the top-k, the
second overwrite clobbers the first — 160 of 613 huts with candidates (26% on the 2026-09-02 run)
end up missing an available source type entirely (see
`docs/backlog/approach-reserved-type-slot-overwrite.md`). The reservation is also orthogonal to
duration: it always picks *fastest of the missing type*, which for a hut needing all three type
slots at `k=3` displaces every duration-ranked candidate — directly hurting duration-window
coverage, since the client (`huts/src/tourSearch/legFilters.ts:20-29`) can only pass/fail-filter
whatever candidates were shipped, never reach back into the full start-edges pool.

**Decision:** Replace the top-k+reservation mechanism with a matrix: for each hut, bucket every
candidate by `(source_type, variant, duration_bucket)` and keep the fastest candidate per cell.
Both axes — source type and variant — are already open-ended dicts in the codebase
(`_SOURCE_TYPE_NAME`, `binfmt.VARIANT_NAMES`); this design makes the *selection* code equally
generic, so introducing a new source type or a new route variant (e.g. a future street-avoidance
variant, tracked in `docs/backlog/approach-urban-walk-unpenalized.md`) needs a config change only,
never a code change.

**Scope:** `build_approach_table.py`'s `select_approaches`/`gather_candidates`, the shipped
`approaches.bin`/`.json` schema, and the frontend read path (`loadApproaches.ts`, `approaches.ts`,
`types.ts`). Everything else — `select_approach_pairs.py`'s upstream `selectK` candidate pool, the
E2 reverse-closure index (`build_tables`'s `hut_to_starts`/`start_to_huts`), exit legs
(`getExitLegs`, which reads the reverse index, not the approach table) — is unaffected.

## 1. Config

`pipeline.config.json`'s `approach.k` is replaced by two new keys:

```json
"approach": {
  "durationBucketsH": [4, 6],
  "variants": ["FAST_ANY"],
  "selectK": 20
}
```

- `durationBucketsH` is a sorted list of bucket-boundary hours. `[4, 6]` produces three buckets:
  `(0, 4]`, `(4, 6]`, `(6, ∞)`. Adding a number adds a bucket; no code change.
- `variants` is a list of `binfmt.VARIANT_NAMES` values eligible as approach candidates, resolved
  through that module's existing name→id table. Today only `"FAST_ANY"` — `FAST_T2`/`FAST_T3`/
  `FAST_T3_UNGRADED` graded-difficulty variants stay excluded (they're the same physical edge
  regraded for hut-to-hut search, not a meaningfully different approach option) until a real
  approach-specific variant (e.g. a low-street-% one) exists and is added here.
- `selectK` (upstream, `select_approach_pairs.py`) is untouched — different table, different
  purpose (candidate-pool cap before `select_approaches` ever runs).

Max rows per hut is now `types_present × len(variants) × (len(durationBucketsH) + 1)` — today
`≤ 3 × 1 × 3 = 9`, up from a hard `3`, entirely config-driven rather than hardcoded.

## 2. Pipeline: `gather_candidates` and `select_approaches`

`gather_candidates` (`build_approach_table.py:53-73`) currently hardcodes
`if int(r["variant"]) != binfmt.VARIANT_FAST_ANY: continue`. That becomes a membership check
against a set resolved from `config["approach"]["variants"]` via `binfmt.VARIANT_NAMES`'s inverse
mapping, passed in as a parameter (not re-read from global `config` inside the function, matching
the existing `k`-as-parameter style). Each candidate dict gains a `"variant": int(r["variant"])`
field (currently implicit/unused since only one variant ever qualified).

`select_approaches` (`build_approach_table.py:82-101`) is rewritten:

```python
def bucket_index(duration_h: float, boundaries: list[float]) -> int:
    for i, b in enumerate(boundaries):
        if duration_h <= b:
            return i
    return len(boundaries)


def select_approaches(records, id_table, duration_buckets, variant_ids) -> list:
    by_hut = gather_candidates(records, id_table, variant_ids)

    rows = []
    for candidates in by_hut.values():
        by_cell = defaultdict(list)
        for c in candidates:
            cell = (c["source_type"], c["variant"], bucket_index(c["duration_h"], duration_buckets))
            by_cell[cell].append(c)
        for cell_candidates in by_cell.values():
            rows.append(min(cell_candidates, key=lambda c: c["duration_h"]))
    return rows
```

No reservation pass, no `k`, no overwrite. An empty cell simply produces no row — no spillover into
adjacent buckets, no fallback logic. A hut with candidates in only one bucket for one type still
gets exactly the rows its real candidate pool supports; nothing manufactures coverage that doesn't
exist.

`build_tables` (`build_approach_table.py:103-124`) is unchanged — it already derives
`retained_start_ids` generically from whatever `approaches` contains, so a larger/differently-shaped
approach list flows through it with no logic change, just more `start_id`s retained on average.

The `--k` CLI arg is replaced by `--duration-buckets-h` (comma-separated floats, default from
config) and `--variants` (comma-separated names, default from config).

## 3. Payload schema

`approaches.bin`/`.json`'s column set (`build_approach_table.py:161-169`) gains one column:

```python
"variant": ("u1", np.array([r["variant"] for r in approaches], dtype="u1")),
```

Row count per hut is now genuinely variable (bounded by §1's formula) rather than the old
near-fixed `{1, 2, 3}`. Nothing else in the binary/manifest format changes — `hut_id`, `start_id`,
`source_type`, `edge_id`, `access_unknown`, `distance_m`, `ascent_m`, `descent_m`, and the
`access_values` side table all keep their current meaning.

## 4. Frontend

- `huts/src/tourSearch/types.ts`'s `ApproachRecord` gains `variant: number`.
- `loadApproaches.ts:16-24` reads `c.variant[i]` into the new field alongside the existing columns.
- `approaches.ts:6-10` (`getApproachLegs`) passes `variant` through unchanged in shape — it doesn't
  filter on it today and doesn't need to while `approach.variants` config lists only `FAST_ANY`;
  the field exists so a future variant is visible/filterable client-side without another schema
  migration. Its stale doc-comment citing `docs/tour-suggestion-payload.md` §6 is corrected per §5
  below.
- No change to `getExitLegs` — it already reads `variant` from the (separately-shaped) reverse
  index and was never part of this bug.

## 5. Documentation

`docs/tour-suggestion-payload.md` is cited as the authoritative payload contract by `CLAUDE.md`,
`approaches.ts:4`, and `build_approach_table.py`'s own module docstring, but was deleted in
`8be1e76` ("docs: bring docs/ in order", 2026-08-31) and never recreated — every one of those
citations is already dangling, independent of this change. Recreate it as part of this work,
covering both `hut-edge-payload.bin`/`.json` and `approaches.bin`/`.json` (the two payload files
that currently have no home), including the new `variant` column and the now-variable row-count
contract described in §3. `CLAUDE.md`'s reference to the doc needs no edit — it already points at
the right (soon to exist again) path.

## 6. Testing

`pipeline/tests/test_build_approach_table.py` currently asserts top-k+reservation behavior
(`test_select_approaches_still_selects_k_best_after_refactor` and the reservation-overwrite cases
around lines 33-77) — these get rewritten for cell selection:

- Two candidates in the same `(type, variant, bucket)` cell → fastest wins, other dropped.
- A hut with only one source type present → one row per bucket that type has candidates in, no
  phantom rows for absent types.
- A bucket with zero candidates → no row, no exception.
- Two candidates in the same type/bucket but different `variant` (using a second synthetic variant
  id in the test fixture, not a real future variant) → both kept as separate rows, proving the
  matrix is genuinely keyed on variant and not silently collapsing it.
- `gather_candidates`'s variant filter driven by a passed-in set rather than a hardcoded constant —
  existing `test_gather_candidates_excludes_non_fast_any_variants` (line 140) becomes
  `test_gather_candidates_excludes_variants_not_in_configured_set`, parameterized over an
  arbitrary configured set rather than hardcoding `FAST_ANY`.

`huts/src/tourSearch/approaches.test.ts` gets one new case: `getApproachLegs` passes `variant`
through on the returned `StartLeg`/`ApproachRecord`.

## Out of scope

- The road-avoidance signal itself (`docs/backlog/approach-urban-walk-unpenalized.md`) — this
  design only makes the selection matrix ready to carry a future street-avoidance variant, it does
  not compute one.
- Any change to `select_approach_pairs.py`'s upstream `selectK` pool or to exit-leg selection
  (`getExitLegs`/the E2 reverse index) — both already generic, neither touches the code this design
  changes.
