# Hard-Negative Training Augmentation Implemented (tier2_cnn_v4 prep)

Date: 2026-07-12
Follows: `docs/evidence/a7/2026-07-12-model-rejected-retune-required.md`
("Reject - Retune" decision on `tier2_cnn_v3`).

## What changed

`Skills/train_tier2_cnn.py` gained an opt-in `--n-hard-negatives` flag that
mixes N synthetic `stellar_artifact`-labeled cutout triplets into the
TRAINING split only (never validation/test, so val_loss/val_acc stay
comparable to prior model versions and reflect real data only).

Implementation:

- `Skills/evaluate_cnn_false_discovery.py` (the module that produced the
  disqualifying adversarial-test evidence) was refactored to expose
  `_synthesize_artifact_cutout_arrays(rng, mag, background_level, sigma_px=...)`
  — the same artifact math, extracted so it returns raw numpy arrays instead
  of only a base64-encoded `Observation`-ready triplet, and with `sigma_px`
  now a parameter instead of hardcoded to the one extreme adversarial-test
  value (`0.15px`). `_synthesize_artifact_cutout_triplet` is now a thin
  wrapper around it; behavior for existing callers is unchanged (verified by
  a new regression test comparing default-arg output to explicit-arg output
  byte-for-byte, plus the full existing test suite passing unmodified).
- `Skills/train_tier2_cnn.py` adds `SyntheticArtifactDataset`, a module-level
  (picklable) torch Dataset that generates one hard-negative triplet per
  index on the fly (no npz files written to disk), drawing sigma from a
  configurable range (`--hard-negative-sigma-min/-max`, default
  `0.05-0.35px` — bracketing the adversarial test's `0.15px` case, and kept
  below the real seeing-limited PSF lower bound of ~0.4px so a hard negative
  can never resemble a genuine point source) rather than one fixed value, so
  training exposes a continuum of spike widths instead of memorizing one
  parameter. `_compute_class_weights` gained an `extra_label_counts`
  parameter so the balanced class weights reflect the true combined
  training composition (real + synthetic), not just the real-data split.
- Off by default (`--n-hard-negatives 0`) — explicit opt-in, no change to
  any existing invocation's behavior.

## Verification

- 32 new/updated unit tests (`tests/test_train_tier2_cnn_policy.py`,
  `tests/test_evaluate_cnn_false_discovery.py`), all offline/synthetic, no
  network or real model weights required except a tiny in-memory CNN
  fixture. `ruff check .` and `mypy src Skills/train_tier2_cnn.py
  Skills/evaluate_cnn_false_discovery.py` both clean. Full offline suite:
  1892 passed, 2 deselected.
- Real, bounded, CPU-only, in-sandbox smoke test (not committed —
  disposable scratch, deleted after use): built a 40-row synthetic labels
  CSV (30 `neo_candidate` + 10 `stellar_artifact`), ran
  `train_tier2_cnn.train(..., n_hard_negatives=20, ...)` for 1 epoch.
  Console output confirmed the augmentation is genuinely wired end-to-end,
  not a no-op:
  ```
  Grouped split: 26 train / 8 validation / 6 test (held out, unused here)
  Hard-negative augmentation: +20 synthetic stellar_artifact triplets
    (sigma range 0.05-0.35 px, seed=1)
  Training on 46 samples, validating on 8 samples
    Train label counts: {'neo_candidate': 21, 'stellar_artifact': 25}
  ```
  46 = 26 real train rows + 20 synthetic; `stellar_artifact` count (25) =
  5 real + 20 synthetic — both class-weight computation and the
  DataLoader's actual batch composition reflect the augmentation
  correctly. Validation stayed at 8 (real-data-only), confirming hard
  negatives never leak into the held-out split.

## Not yet done — next step is a real GPU retrain

This is code-only. Producing `tier2_cnn_v4` still requires an actual
retrain on real MPS hardware (this session's sandbox cannot do GPU
training, per the established pattern for every prior retrain in this
project). Recommended `--n-hard-negatives` for the real run: **3000** —
`tier2_cnn_v3`'s real training data has 18,871 real `stellar_artifact`
(bogus) examples out of 90,000 total (`data/cutouts_v3/index.csv`,
confirmed by direct count); 3000 synthetic hard negatives is a meaningful
~16% addition to that class without overwhelming real bogus diversity.
This number is a starting recommendation, not a tuned hyperparameter — the
acceptance test (below) is what actually validates it, not this count in
isolation.

Command (not yet run):

```bash
git pull origin main
export PYTHONPATH=src

caffeinate -i uv run --python 3.14 python Skills/train_tier2_cnn.py \
    --labels data/cutouts_v3/index.csv \
    --epochs 20 \
    --num-workers 8 \
    --n-hard-negatives 3000 \
    --out models/tier2_cnn_v4.pt \
    --grouped-split-report Logs/reports/tier2_cnn_v3_grouped_split_report.json \
    --production-candidate

# Acceptance test for the retune itself -- the retune is only "done" when
# this specific measured gap closes, not when training completes:
caffeinate -i uv run --python 3.14 python Skills/evaluate_cnn_false_discovery.py \
    --cnn-model models/tier2_cnn_v4.pt --n-artifacts 200 --seed 42 \
    --json Logs/reports/cnn_false_discovery_tier2_cnn_v4.json

# Then recalibrate (T1-D KPIs must be repeated for any new candidate):
caffeinate -i uv run --python 3.14 python Skills/evaluate_calibration.py \
    --alerts data/ztf_labeled_alerts_v3.json \
    --cutouts-csv data/cutouts_v3/index.csv \
    --cnn-model models/tier2_cnn_v4.pt \
    --report-out Logs/reports/calibration_report_v4.json
```

Reuses the existing real, passing `tier2_cnn_v3_grouped_split_report.json`
(the grouped split by real `object_id` is unaffected by hard-negative
augmentation, since those are added only inside `train()`'s in-memory
training set, never touching the split CSV or its report).
