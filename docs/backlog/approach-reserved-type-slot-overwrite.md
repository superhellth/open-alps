# Approach table drops a reserved source-type slot when two types are missing

**Priority:** High

`select_approaches` (`pipeline/phases/postprocessing/build_approach_table.py:82-101`) takes the
`k`-best candidates per hut by DIN duration, then reserves a slot for each source type
(parking/station/partner_betrieb) that the top-k missed — that reservation is the whole reason the
client's car/transit split has anything to work with.

The reservation writes into the *same* slot every time:

```python
for source_type in _SOURCE_TYPE_NAME:
    if source_type in present_types:
        continue
    best_other = next((c for c in candidates if c["source_type"] == source_type), None)
    if best_other is None:
        continue
    if selected:
        selected[-1] = best_other   # <- always the last slot
```

So when **two** types are missing from the top-k, the second iteration overwrites the first one's
insertion and that type is lost. With `_SOURCE_TYPE_NAME` iterating parking → station →
partner_betrieb, a hut whose top-3 is all parking and which has both a station and a partner
business ends up with the partner business and **no station at all**.

**Measured on the current run** (`data/osm/start_edges/records.npy`, FAST_ANY, k=3): two or more
source types are missing from the top-3 for **102 of 610 huts (17%)**, so each of those loses one
reserved slot. Shipped `approaches.bin` confirms the effect on output shape: 609 of 610 huts have
exactly 3 rows — the reservation only ever replaces, never extends, so a hut that legitimately
needs three type slots plus its best-by-duration entries cannot express that in `k=3`.

**Two separable decisions for whoever fixes this:**

1. The overwrite itself is unambiguously a bug — reserving a second type must not clobber the
   first (replace successive tail slots, or track which slots are already reserved).
2. Whether reservation should *replace* or *extend* past `k` is a design call, not a bug. Replacing
   means a hut with three source types has no room for a second-best approach of the dominant type;
   extending means the row count per hut becomes `k + reserved`. `approach.k` in
   `pipeline.config.json` is the knob either way.

Found while reviewing `docs/superpowers/specs/2026-09-02-hub-edge-scaling-design.md`, which
preserves this code path verbatim (its §B7 re-ranks over a shorter candidate list but keeps the
selection logic) — so the scaling work neither causes nor fixes it, and it is filed here rather
than folded into that spec.
