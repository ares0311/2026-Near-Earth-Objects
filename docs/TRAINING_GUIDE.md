# ML Training Guide

Step-by-step instructions for training the three-tier classifier in the NEO
detection pipeline.  Complete each tier in order; later tiers depend on the
outputs of earlier ones.

---

## Prerequisites

```bash
pip install -e ".[dev]"          # installs torch, xgboost, lightgbm, etc.
python -m mypy src               # must pass with zero errors
PYTHONPATH=src python -m pytest  # all tests must pass (100% coverage gate)
```

Required environment variables (set in `.env` or export):

| Variable | Purpose |
|---|---|
| `ATLAS_TOKEN` | ATLAS forced-photometry API token |
| `ZTF_IRSA_USERNAME` / `ZTF_IRSA_PASSWORD` | Optional IRSA login for proprietary ZTF access; public ZTF access needs no credential |

---

## Step 1 — Collect Training Labels

```bash
python Skills/generate_training_labels.py \
    --out data/training_labels.csv \
    --n-neo 5000 \
    --n-mba 10000
```

This downloads MPC-numbered NEOs (positive labels) and a random MBA sample
(negative labels) via `astroquery.mpc`.  Output is a CSV with columns:

| Column | Description |
|---|---|
| `object_id` | MPC provisional or numbered designation |
| `label` | `neo`, `mba`, or `artifact` |
| `ra_deg`, `dec_deg` | Representative sky position |
| `mag` | Reported magnitude |
| `filter_band` | Photometric band |

**Label quality note**: Use only MPC-numbered objects as high-confidence
positives.  Provisional designations should be down-weighted (`sample_weight=0.5`).

---

## Step 2 — Fetch ZTF Alerts for Labeled Objects

```bash
python Skills/run_pipeline.py \
    --ra 180 --dec 0 --radius 10 \
    --start-jd 2460000 --end-jd 2460030 \
    --out data/pipeline_run.json
```

For each labeled object, the pipeline fetches difference-image alerts from ZTF
or ATLAS and saves scored NEO dicts to `data/pipeline_run.json`.

---

## Step 3 — Tier 1: XGBoost on Tabular Features

### 3a. Build the feature matrix

The feature matrix is assembled automatically by `classify.py` from
`CandidateFeatures` fields.  Features that are `None` are imputed as `0.0`
(neutral weight in the log-score model).

Key features used by Tier 1:

| Feature | Weight (neo_candidate) |
|---|---|
| `real_bogus_score` | +2.0 |
| `arc_coverage_score` | +1.5 |
| `nights_observed_score` | +1.5 |
| `motion_consistency_score` | +1.2 |
| `orbit_quality_score` | +1.0 |
| `known_object_score` | −2.5 |
| `stellar_artifact_score` | −2.0 |

### 3b. Train

```python
import sys; sys.path.insert(0, "src")
from classify import retrain_tier1

# labels: list of ("neo"|"mba"|"artifact", CandidateFeatures)
retrain_tier1(labeled_features)
```

Or from the CLI:

```bash
python Skills/batch_score.py data/training_labels.csv --train
```

### 3c. Evaluate

```bash
python Skills/evaluate_calibration.py --tier 1 --labels data/training_labels.csv
```

Expected output: Brier score < 0.10, ECE < 0.05 on held-out 20% split.

### 3d. Feature importances

```python
from classify import get_tier1_feature_importances
importances = get_tier1_feature_importances()
# Returns dict[str, float] — inspect to verify real_bogus and arc_coverage dominate
```

---

## Step 4 — Tier 2: CNN on Image Triplets

### 4a. Build the cutout dataset

```bash
python Skills/build_cutout_dataset.py \
    data/ztf_alerts.json \
    --out data/cutouts.npz \
    --index data/cutouts_index.csv
```

Each row in `cutouts_index.csv` contains `obs_id`, `label`, and `cutout_path`
pointing into the `.npz` archive.  Cutouts are 63×63 float32 arrays normalized
to [0, 1].

### 4b. Train

```bash
python Skills/train_tier2_cnn.py \
    --index data/cutouts_index.csv \
    --epochs 20 \
    --batch-size 64 \
    --out models/tier2_cnn.pt
```

Architecture (Duev et al. 2019 adapted):
- Three parallel convolutional branches (science / reference / difference)
- Each branch: Conv2d(1,32,3) → ReLU → MaxPool → Conv2d(32,64,3) → ReLU → MaxPool → Flatten
- Merged at a dense layer: Linear(3×64×13×13, 256) → ReLU → Dropout(0.5) → Linear(256, 1) → Sigmoid

Recommended GPU: any CUDA device with ≥ 4 GB VRAM.  Training on CPU is
supported but slow (~1 hr per epoch on a 100k-alert dataset).

### 4c. Evaluate

After training, the script prints validation AUC and writes a calibration
curve.  Target: AUC > 0.95, Brier score < 0.08.

---

## Step 5 — Tier 3: Transformer on Tracklet Sequences

### 5a. Build the sequence dataset

```bash
python Skills/build_sequence_dataset.py \
    data/sample_tracklets.json \
    --out data/sequences.csv
```

Each row is a flat tokenized tracklet: `tok_0_ra`, `tok_0_dec`, `tok_0_mag`,
`tok_0_jd`, `tok_0_filter`, `tok_1_ra`, … up to `max_seq_len` observations.

### 5b. Train

```bash
python Skills/train_tier3_transformer.py \
    --sequences data/sequences.csv \
    --epochs 30 \
    --d-model 128 \
    --n-heads 4 \
    --n-layers 3 \
    --out models/tier3_transformer.pt
```

Architecture (BERT-style encoder-only):
- Linear embedding of (ra, dec, mag, jd, filter_id) per observation token
- Sinusoidal positional encoding keyed on observation JD (not sequence index)
- `n-layers` transformer encoder layers
- CLS token pooled → Linear(d_model, 5) → Softmax over 5 hypotheses

Target: macro-F1 > 0.80 on held-out 20% split.

### 5c. Evaluate

```bash
python Skills/evaluate_calibration.py --tier 3 --sequences data/sequences.csv
```

---

## Step 6 — Ensemble Calibration

After all three tiers are trained, calibrate the stacking meta-learner:

```python
from classify import retrain_stacker
# labeled_tracklets: list of (label, Tracklet) pairs with known ground truth
retrain_stacker(labeled_tracklets)
```

Then run calibration evaluation across all tiers:

```bash
python Skills/evaluate_calibration.py \
    --tier ensemble \
    --labels data/training_labels.csv \
    --platt     # or --isotonic for PAVA calibration
```

Expected final performance (injection-recovery baseline):
- Detection rate: 100%
- Link rate: 100%
- Score rate: 100% (see `data/injection_recovery_n200.json`)

---

## Step 7 — Injection-Recovery Validation

Run end-to-end injection-recovery to validate the full trained pipeline:

```bash
python Skills/injection_recovery.py \
    --n 200 --seed 42 \
    --json data/injection_recovery_trained.json

python Skills/compare_baselines.py \
    data/injection_recovery_n200.json \
    data/injection_recovery_trained.json
```

The comparison script exits non-zero if any metric regresses by > 5 pp.

---

## Updating Models

When retraining after new data arrives:

1. Re-run Steps 1–2 to refresh labels and fetch results.
2. Retrain only the tier that changed data affects (usually Tier 1 suffices for
   new catalog entries).
3. Re-run Steps 6–7 to validate end-to-end performance before deploying.

Model files are stored in `models/` and version-tagged via `ScoringMetadata.model_version`.

---

## Guardrails

- Never use a model trained on < 500 labeled examples in production.
- Always run `Skills/injection_recovery.py` before updating any deployed model.
- Never assert an impact probability from model output alone — defer to
  MPC/CNEOS.
- The alert protocol (CLAUDE.md §Alert Protocol) is mandatory and must not be
  bypassed regardless of model confidence.
