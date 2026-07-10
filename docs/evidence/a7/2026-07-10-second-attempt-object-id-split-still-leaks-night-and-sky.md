# A7 grouped-split closure attempt — 2026-07-10, second pass (multi-night fixed, deeper leakage found)

## What changed since the first attempt

`Skills/download_ztf_training_alerts.py` was fixed in commit `3914824e`
(per-night cap via `compute_per_night_target()`) to stop a single large
night's tarball from exhausting the entire `--limit` before later nights are
ever fetched. Re-running the full 3-step sequence:

```bash
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/download_ztf_training_alerts.py \
    --nights 3 --limit 40000 \
    --output data/ztf_labeled_alerts_v2.json
caffeinate -i uv run --python 3.14 python Skills/build_cutout_dataset.py \
    --input data/ztf_labeled_alerts_v2.json \
    --output-dir data/cutouts_v2/ \
    --csv data/cutouts_v2/index.csv
uv run --python 3.14 python Skills/train_tier2_cnn.py \
    --labels data/cutouts_v2/index.csv \
    --emit-split-csv data/cutouts_v2/grouped_split.csv
uv run --python 3.14 python Skills/validate_grouped_splits.py \
    data/cutouts_v2/grouped_split.csv > Logs/reports/tier2_cnn_grouped_split_report.json
```

## Result 1: multi-night acquisition now genuinely works

`data/ztf_labeled_alerts_v2.json` — 40,000 alerts, confirmed spanning three
distinct real archive nights:

| `archive_night` | count |
|---|---:|
| 20260707 | 13,332 |
| 20260708 | 13,334 |
| 20260709 | 13,334 |

36,038 distinct `object_id` values. The per-night-cap fix works as designed.

## Result 2: grouped split still FAILS — a deeper, structural gap

`Logs/reports/tier2_cnn_grouped_split_report.json`:
`"passed": false`, `n_records: 40000`, split counts
train:26000 / validation:8000 / test:6000.

- `hard_leakage.night_key`: **all three** night keys
  (`jdnight:2461229`, `jdnight:2461230`, `jdnight:2461231`) each appear in
  all three of train/validation/test.
- `hard_leakage.sky_cell`: **2,629** distinct sky cells span two or three
  splits.
- `context_overlap.source_key`: `ZTF:P48` in all three splits (expected,
  single-instrument acquisition — flagged as an untestable warning, not a
  hard failure).

## Root cause (structural, not a parameter or acquisition bug this time)

`Skills/train_tier2_cnn.py --emit-split-csv` groups **only by `object_id`**
when assigning records to train/validation/test (a random split over unique
objects). `Skills/validate_grouped_splits.py` independently checks THREE
`hard_groups` — `object_id`, `night_key`, `sky_cell` — and requires each one
to be wholly contained within a single split with zero cross-split overlap.

Grouping only by `object_id` guarantees `object_id` purity but does nothing
to prevent a given night's (or sky region's) alerts from being scattered
across all three splits, because `night_key`/`sky_cell` are independent axes
from `object_id` — thousands of different objects share a `night_key`, and
a random object-level split has no reason to keep them together.

With only **3** distinct nights present in this batch, achieving `night_key`
purity requires assigning **whole calendar nights** to whole splits (e.g.
night 1 -> train, night 2 -> validation, night 3 -> test) — a fundamentally
different (and much coarser) splitting strategy than object-random. This is
a real, structural mismatch between what the CNN training script's splitter
implements (`docs/PRODUCTION_READINESS.md`'s A4 note: "Initial grouped
leakage controls landed in v0.90.63") and what the validator it is piped
into actually enforces. Both scripts are real and each internally correct;
they were simply never run together end-to-end against real multi-night
data until this session, which is why this gap was not previously visible —
prior grouped-split evidence in this repo used synthetic or single-axis
fixtures, not a real ~3-night ZTF batch through the full emit+validate
pipeline.

## Why this is not a quick code fix

A whole-night assignment with only 3 total nights degenerates to exactly
one night per split — each split's class balance, field pointings, and
observing conditions would then be driven entirely by a single night, which
is a much weaker statistical design than the current 6,500/2,000/1,500
(now 26,000/8,000/6,000) object-random split, even though it satisfies the
validator's leakage check. Whether that tradeoff (leak-free but
single-night-per-split) is acceptable, or whether the real fix is acquiring
enough additional nights that whole-night assignment can put multiple
nights in each split, is a data-acquisition-scale and split-design decision,
not a bug fix — flagging for operator direction rather than guessing.

## Status

`grouped_split_report_missing` blocker: **still open**. Real progress: the
acquisition-side single-night bug (first attempt) is fixed and verified.
The remaining gap is in the split-assignment algorithm's grouping axes
versus the validator's requirements, given only 3 real nights of source
data. Do not cite this split report as A4 evidence; it is negative evidence
only, same as the first attempt.
