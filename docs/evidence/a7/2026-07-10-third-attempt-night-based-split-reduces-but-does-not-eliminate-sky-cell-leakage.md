# A7 grouped-split closure attempt — 2026-07-10, third pass (night-aware split implemented and tested)

## What was built

Added `assign_night_based_split()` and a `--split-strategy {object,night}`
flag to `Skills/train_tier2_cnn.py` (commit pending). It assigns whole
calendar nights (using the exact same `night_key` derivation as
`src/grouped_splits.py`, imported not duplicated) to whole splits
chronologically (test nights first, then validation, then train), tracking
record counts against `--val-fraction`/`--test-fraction`. It then resolves
any `object_id` conflicts a whole-night assignment creates (an object
observed on two nights that landed in different splits) by moving all of
that object's rows into the split of its first-seen row, and reports the
count of rows moved. 3 new regression tests, all pass; ruff clean.

## Real result on the existing 3-night, 40,000-alert batch

```
uv run --python 3.14 python Skills/train_tier2_cnn.py \
    --labels data/cutouts_v2/index.csv \
    --emit-split-csv data/cutouts_v2/grouped_split_night.csv \
    --split-strategy night
```

```
counts: {'train': 15347, 'validation': 12768, 'test': 11885}
nights: 3
  jdnight:2461229: test (13332 records)
  jdnight:2461230: validation (13334 records)
  jdnight:2461231: train (13334 records)
object_id conflict resolution: 2653 rows moved to their object's first-seen split
```

`Skills/validate_grouped_splits.py` on the resulting CSV:

```json
"passed": false,
"n_records": 40000,
"hard_leakage issue counts": {"night_key": 2, "sky_cell": 1407}
```

Compare to the second attempt's object_id-only split on the same data:
`{"night_key": 3, "sky_cell": 2629}`.

## What this proves

1. **Night-aware splitting works as designed, with an expected residual.**
   `night_key` leakage dropped from 3/3 nights leaking to 2/3, and the
   remaining 2 are a direct, understood, and counted consequence of the
   2,653-row object-conflict resolution (moving an object's later-night rows
   into its earlier-night split necessarily mixes a small amount of that
   later night's data into a different split). This is not a bug -- it is
   the real cost of preferring object_id purity when a real object is
   detected across nights assigned to different splits. Perfect purity on
   both axes simultaneously is only possible if zero objects repeat across
   split-assigned nights, which real ZTF data mostly does not guarantee.
2. **Sky-cell leakage is substantially reduced but not eliminated (2629 ->
   1407, a 46% reduction), and this is likely a real-survey-physics limit,
   not a splitter bug.** `sky_cell` is a 1-degree RA/Dec grid cell
   (`src/grouped_splits.py:_sky_cell`, `cell_degrees=1.0`). ZTF's northern
   all-sky survey revisits the same field footprint on a roughly 2-3 day
   public-survey cadence by design -- that is the entire point of a
   time-domain survey. Even with each of the 3 nights cleanly assigned to a
   different split, the *same* sky positions get reobserved night to night,
   so a meaningful fraction of `sky_cell` values necessarily appear in more
   than one split no matter how the nights are partitioned. This is not
   something a smarter split algorithm can fix within a short (3-night, or
   even a much longer) real single-instrument survey window -- it would
   require deliberately holding out entire *sky regions* (not just time
   windows) from one or more splits, which trades one kind of leakage risk
   for a different one (season/airmass/systematics correlated with sky
   region rather than with time).

## Implication for the "acquire more nights" plan

Acquiring more nights (the previously chosen direction) will very likely
**still** leave nonzero `sky_cell` leakage, because more nights means more
opportunities for ZTF to revisit the same fields across split boundaries --
the underlying survey-cadence physics does not go away with a larger time
window; if anything a longer window guarantees more field revisits, not
fewer. It should still further reduce/dilute `night_key` leakage's relative
weight (more train-side nights available for the object-conflict-resolution
step to "absorb" without visibly mixing into val/test), and will materially
improve statistical diversity within each split (the original stated goal),
but it is very unlikely to reach `passed: true` on `sky_cell` purity by
itself. Flagging this refined understanding back to the operator before
committing to a large new download, since the honest expectation has
changed from "more nights should close this" to "more nights improves but
likely does not fully close this without also addressing sky_cell
specifically (e.g. redefining sky_cell context as a reported/monitored
metric rather than a hard gate for single-survey time-domain data, or a
combined time+space holdout design)."

## Status

`grouped_split_report_missing` blocker: **still open**. Real, tested code
improvement landed (`--split-strategy night`); real diagnostic evidence
gathered on genuine data. Next step needs operator direction given the
refined understanding above, not another guess.
