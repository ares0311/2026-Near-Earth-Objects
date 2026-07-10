# A7 grouped-split closure attempt — 2026-07-10, first pass (single-night leakage found)

## Command run (per v0.90.74 handoff in CLAUDE.md)

```bash
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/download_ztf_training_alerts.py \
    --nights 3 --limit 10000 \
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

## Results

1. **Download: succeeded.** `data/ztf_labeled_alerts_v2.json` — 10,000 real ZTF
   alerts, valid JSON, each record carries the new provenance fields
   (`object_id`, `candid`, `jd`, `ra`, `dec`, `fid`, `field`, `archive_night`)
   added in v0.90.74.
2. **Cutout build: succeeded.** `data/cutouts_v2/index.csv` — 10,000 rows, each
   with `object_id`, `jd`, `ra_deg`, `dec_deg`, `source_key`. 10,000 `.npz`
   cutout files written.
3. **Grouped split emitted: succeeded** (by `train_tier2_cnn.py
   --emit-split-csv`, which groups by `object_id` only) — counts
   train:6500 / validation:2000 / test:1500.
4. **Grouped split validation: FAILED (real result, not a script error).**
   `Skills/validate_grouped_splits.py` report
   (`Logs/reports/tier2_cnn_grouped_split_report.json`):
   `"passed": false`, `n_records: 10000`. Failure is on the `hard_groups`
   checks the object_id-only splitter does not cover:
   - `night_key`: only **one** distinct night key
     (`jdnight:2461231`) appears across all 10,000 records, and that single
     night appears in all three of train/validation/test — by definition,
     with only one night present, night-level holdout is impossible.
   - `sky_cell`: dozens of `sky_cell` values appear across two or three of
     the three splits (object-id-only splitting does not group by sky
     region, so adjacent-field alerts land in different splits).
   - `context_overlap.source_key`: `ZTF:P48` (the only source) appears in
     all three splits — expected/unavoidable with a single-instrument
     acquisition, flagged as context not hard leakage.

## Root cause (read from source, not guessed)

`Skills/download_ztf_training_alerts.py:371`:
```python
if len(results) >= args.limit:
    break
```
The per-night loop stops as soon as the **global** `--limit` is reached. The
script's own docstring states each night yields roughly 5,000-20,000 alerts.
With `--limit 10000`, night 1 alone satisfies the cap, so nights 2 and 3 are
never fetched — the acquisition is structurally single-night no matter how
many `--nights` are requested, unless `--limit` comfortably exceeds one
night's maximum yield. This matches the exact caveat already written into the
v0.90.74 handoff comment ("`--nights 3` typically satisfies `--limit` from the
first night's tarball") — but that caveat was recorded as a storage/sharding
note, not connected to the fact that it would also break the A4 grouped
night-level split requirement. This is the actual root cause of
`grouped_split_report_missing` failing to close on the first real attempt.

## Fix attempted (no code change, minimal first try)

Re-running the same download with `--limit 40000` (raised from 10000) to
force the loop past night 1's maximum plausible yield (~20,000) and into
nights 2-3, using the existing script unmodified. Result recorded in a
follow-up evidence file once that run completes.

## Status

`grouped_split_report_missing` blocker: **still open**. This file documents
a real, non-passing attempt — not a fabricated success. Do not cite this
split report as A4 evidence; it is negative evidence only.
