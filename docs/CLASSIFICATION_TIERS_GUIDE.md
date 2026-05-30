# Classification Tiers Guide

Technical reference for the three-tier ML classification pipeline, ensemble
stacking, calibration, and conservative classification policy.

---

## Overview

The classifier assigns each linked tracklet a posterior probability over five
hypotheses: `neo_candidate`, `known_object`, `main_belt_asteroid`,
`stellar_artifact`, and `other_solar_system`.  Three independent models run
in sequence; their outputs are fused by a meta-learner.

---

## Tier 1 — XGBoost on Tabular Features

**Architecture**: Gradient-boosted decision trees (XGBoost or LightGBM).

**Input features**:
- `real_bogus_score`, `streak_score`, `psf_quality_score`
- `motion_rate_arcsec_per_hour`, `arc_days`, `nights_observed_score`
- `brightness_score`, `color_score`, `lightcurve_variability_score`
- MPC match distance (known-object proximity)

**Training data**: ZTF real/bogus labeled alerts (Duev et al. 2019,
~100,000 examples) plus MPC confirmed NEO catalog (~35,000 objects) as
positive class.

**Outputs**: `real_bogus_score` and `neo_class_confidence` as `OptScore`
(float in [0, 1] or None).

**Advantages**: Fast inference, interpretable feature importances, works
with small labeled sets (~500 examples minimum).

---

## Tier 2 — CNN on Image Triplets

**Architecture**: Three parallel convolutional branches (science, reference,
difference cutouts) merged at a dense layer.  Adapted from Duev et al.
(2019).

**Input**: 63×63 pixel float32 cutout triplets normalized to [0, 1].

**Training data**: ZTF real/bogus training set (public weights available as
starting point).  Fine-tuned on confirmed NEO vs. artifact subsets.

**Calibration**: Platt scaling applied after training to map raw logits to
calibrated probabilities.

**Output**: Calibrated real/bogus probability per alert.

**Build order**: Construct only after Tier 1 is calibrated.

---

## Tier 3 — Transformer on Tracklet Sequences

**Architecture**: Standard encoder-only transformer (BERT-style) with
positional encoding based on observation time.  Reference: Lin et al. (2022).

**Input**: Sequence of `(RA, Dec, magnitude, time, filter)` tokens per
tracklet, one token per observation.

**Task**: Multi-class classification over all five hypotheses.

**Training data**: MPC observation history for confirmed NEOs, MBA sample,
and ZTF artifact labels.

**Build order**: Construct only after Tier 2 is calibrated.

---

## Ensemble Stacking

A logistic regression meta-learner combines the outputs of all three tiers:

```
stacker_input = [tier1_neo_prob, tier1_rb, tier2_rb, tier3_neo_prob, ...]
final_posterior = softmax(stacker.predict_proba(stacker_input))
```

The stacker is trained on held-out validation data with cross-validated
predictions from each tier to avoid leakage.

---

## Calibration Pipeline

All tier outputs and the stacked posterior are calibrated via
`calibration.py`:

- **Platt scaling** (`PlattCalibrator`): logistic regression fit on
  validation predicted probabilities vs. labels; works well for small
  validation sets.
- **Isotonic regression** (`IsotonicCalibrator`, PAVA): non-parametric
  monotone fit; better for larger validation sets.

Calibration quality is evaluated with Brier score, Expected Calibration
Error (ECE), and log-loss.  Use `Skills/evaluate_calibration.py` and
`Skills/plot_calibration.py` to inspect reliability diagrams.

---

## Conservative Classification Policy

- `None` feature scores contribute 0 to log-score computations (neutral,
  not penalised).
- Unknown objects default to `"candidate"` not `"confirmed NEO"`.  The
  pipeline never outputs `"confirmed NEO"` for internally detected objects.
- PHAs require orbit quality code ≥ 2 before the `pha_candidate` flag is
  set.
- The dominant hypothesis and entropy are always reported alongside any
  classification decision to expose uncertainty.
- When in doubt, flag for human review rather than suppress.

---

## Key References

- Duev, D.A. et al. (2019). *MNRAS* 489, 3582–3590.
- Lin, H.-W. et al. (2022). *AJ* 163, 154.
