# Classification Guide

Technical reference for the three-tier classification pipeline in `classify.py`.

---

## Overview

The classification stage takes linked tracklets from `link.py` and produces a `NEOPosterior` over five hypotheses together with calibrated `CandidateFeatures`. Classification runs in three tiers that are trained independently and then combined by a stacking meta-learner.

```
Tracklet
  │
  ├── Tier 1: XGBoost on tabular features  →  real_bogus_score, neo_class_confidence
  ├── Tier 2: CNN on image triplets         →  calibrated real/bogus probability
  ├── Tier 3: Transformer on sequence       →  multi-class NEOPosterior
  │
  └── Stacking meta-learner (LogisticRegression)
        │
        └── Final NEOPosterior (calibrated via calibration.py)
```

---

## Hypotheses

| Symbol | Hypothesis | Prior |
|---|---|---|
| `neo_candidate` | Genuine new NEO | 0.05 |
| `known_object` | Matches MPC catalog | 0.30 |
| `main_belt_asteroid` | MBA on unusual orbit | 0.35 |
| `stellar_artifact` | Cosmic ray / satellite / artifact | 0.25 |
| `other_solar_system` | Comet, TNO, etc. | 0.05 |

Priors are deliberately pessimistic. At high ecliptic latitudes, MBA contamination is lower and the `main_belt_asteroid` prior may be reduced.

---

## Tier 1: XGBoost on Tabular Features

### Input Features

| Feature | Source | Notes |
|---|---|---|
| `real_bogus_score` | ZTF `rb` / `drb` field | Pre-computed by ZTF |
| `motion_rate_arcsec_hr` | `link.py` | Rate of sky-plane motion |
| `arc_days` | `link.py` | Arc length in days |
| `nights_observed` | `link.py` | Number of distinct nights |
| `brightness` (mag) | `preprocess.py` | Aperture magnitude |
| `color_index` (g-r) | `preprocess.py` | Colour from multi-band obs |
| `streak_score` | `detect.py` | Image-moment elongation |
| `psf_elongation` | `preprocess.py` | PSF axis ratio |
| `mpc_match_distance_arcsec` | `detect.py` | Cross-match residual |

### Training Data

- Positive (NEO): MPC confirmed NEOs with numbered designations from `astroquery.mpc`.
- Negative (artifact): ZTF real/bogus labels (Duev et al. 2019) with `rb < 0.3`.
- Negative (MBA): MPC MBA sample restricted to `2.0 < a < 3.5 AU`.

Minimum recommended training set: 500 examples per class.

### Output

`real_bogus_score` and `neo_class_confidence` as `OptScore` (float | None in [0, 1]).

---

## Tier 2: CNN on Image Triplets

Architecture follows Duev et al. (2019):

- Three parallel convolutional branches for science / reference / difference cutouts (63×63 px).
- Each branch: Conv→ReLU→MaxPool×2 then flatten.
- Concatenated branch features → dense layer → sigmoid output.

Input cutouts are normalized to [0, 1] by `preprocess.py`.

Pre-trained weights (ZTF real/bogus) are available in `models/tier2_cnn.pt` after running `Skills/train_tier2_cnn.py`.

### Fine-Tuning

```bash
python Skills/train_tier2_cnn.py \
    --cutout-csv data/cutouts/index.csv \
    --epochs 20 \
    --lr 1e-4 \
    --output models/tier2_cnn.pt
```

---

## Tier 3: Transformer on Tracklet Sequences

Architecture:

- Observation token: (RA, Dec, magnitude, time_offset, filter_id) → linear projection.
- Standard encoder-only transformer (BERT-style) with sinusoidal positional encoding based on observation Julian Date.
- CLS token output → 5-class logits; inference softmax → `NEOPosterior`.

Training data: MPC observation history exported via `Skills/build_sequence_dataset.py`.

```bash
caffeinate -i .venv/bin/python Skills/train_tier3_transformer.py \
    --train data/sequences/production/train.csv \
    --validation data/sequences/production/calibration.csv \
    --test data/sequences/production/test.csv \
    --epochs 30 \
    --out models/tier3_transformer.pt \
    --report data/sequences/production/tier3_training_report.json
```

---

## Morphology Classification

`classify_morphology(obs)` classifies a single observation as one of three source types using the second-moment ellipse of the difference-image cutout:

| Label | Condition |
|---|---|
| `"streak"` | Elongation ratio λ₁/λ₂ ≥ 5.0 |
| `"extended"` | Elongation ratio ≥ 1.5 |
| `"point_source"` | Elongation ratio < 1.5 |

`batch_morphology(tracklet)` aggregates morphology across all observations in a tracklet and returns the modal class, per-class counts, and the streak fraction.

---

## Stacking Ensemble

After all three tiers produce outputs, a `LogisticRegression` meta-learner is trained on held-out predictions. The stacker takes concatenated Tier 1 + Tier 2 + Tier 3 outputs as input features and produces the final `NEOPosterior`.

```python
from classify import ensemble_predict, _build_ensemble

# Build stacker from held-out predictions
stacker = _build_ensemble(tier1_preds, tier2_preds, tier3_preds, labels)

# Predict on new tracklets
posterior = ensemble_predict(tracklet, tier1_model, tier2_model, tier3_model, stacker)
```

Retrain the Tier 1 XGBoost or stacker without restarting the pipeline:

```python
from classify import retrain_tier1, retrain_stacker

retrain_tier1(new_features, new_labels)
retrain_stacker(new_tier_preds, new_labels)
```

---

## Calibration

All tier outputs should be calibrated before use in scoring. `calibration.py` provides:

- **Platt scaling** (`PlattCalibrator`): sigmoid fit; fast; works on any size dataset.
- **Isotonic regression** (`IsotonicCalibrator`): non-parametric PAVA; requires ≥ 1000 examples.

Evaluate calibration quality:

```python
from calibration import brier_score, expected_calibration_error, cross_validate_calibration

mean, std = cross_validate_calibration(probs, labels, n_folds=5, metric="brier")
print(f"Brier score: {mean:.4f} ± {std:.4f}")
```

---

## Posterior Entropy and Dominant Hypothesis

```python
from classify import posterior_entropy, dominant_hypothesis

bits = posterior_entropy(posterior)         # Shannon entropy; high = uncertain
name, prob = dominant_hypothesis(posterior) # Most probable class
```

Use entropy as a flag for human review: candidates with entropy > 1.5 bits should be inspected manually before external reporting.

---

## Conservative Classification Policy

Per DECISION-005, the pipeline defaults to conservatism:

- `None` feature scores are treated as neutral (contribute 0 to log-score).
- Unknown objects default to `"internal_candidate"` alert pathway, not `"mpc_submission"`.
- PHA flagging requires orbit quality code ≥ 2 (`multi_night` arc).
- `"confirmed NEO"` is never emitted; only `"neo_candidate"` with a posterior probability.

---

## Key Functions

| Function | Description |
|---|---|
| `extract_features(tracklet)` | Build `CandidateFeatures` from a linked tracklet |
| `classify(tracklet)` | Full three-tier classification → `NEOPosterior` |
| `classify_batch(tracklets)` | Batch classification |
| `classify_morphology(obs)` | Source morphology from image moments |
| `batch_morphology(tracklet)` | Modal morphology across all observations |
| `explain_classification(tracklet)` | Structured breakdown with Tier 1 importances |
| `batch_explain(tracklets)` | Batch version of `explain_classification` |
| `dominant_hypothesis(posterior)` | (name, probability) of top class |
| `posterior_entropy(posterior)` | Shannon entropy of `NEOPosterior` in bits |
| `ensemble_predict(...)` | Stacking meta-learner prediction |
| `retrain_tier1(features, labels)` | Incremental XGBoost retraining |
| `retrain_stacker(preds, labels)` | Incremental stacker retraining |

---

## References

- Duev, D. A., et al. "Real-bogus Classification for the Zwicky Transient Facility Using Deep Learning." *MNRAS*, 489(3), 2019.
- Lin, H.-W., et al. "Astronomical Image Time Series Classification Using CONVolutional Neural nETworks." *AJ*, 163, 2022.
