# Calibration Metrics Reference

This document describes the calibration quality metrics available in
`calibration.py`, including their formulas, interpretation, and typical usage.

---

## Overview

A well-calibrated classifier assigns probability *p* to an event that occurs
with empirical frequency *p*.  All metrics in this module operate on a list of
predicted probabilities `probs` (floats in [0, 1]) and true binary labels
`labels` (0 or 1).

---

## Metrics

### Brier Score (`brier_score`)

$$\text{BS} = \frac{1}{N}\sum_{i=1}^{N}(p_i - y_i)^2$$

- Range: [0, 1].  Lower is better.
- Perfect model: BS = 0.0.
- Random (50%) model: BS = 0.25.

### Expected Calibration Error (`expected_calibration_error`)

Bins predictions into *B* equal-width buckets; computes the weighted average of
|mean confidence − fraction positive| per bucket.

$$\text{ECE} = \sum_{b=1}^{B} \frac{|B_b|}{N} \left|\bar{p}_b - \bar{y}_b\right|$$

- Range: [0, 1].  Lower is better.  ECE < 0.05 is typically considered good.

### Log Loss (`compute_log_loss`)

Binary cross-entropy with probability clipping to avoid log(0):

$$\text{LogLoss} = -\frac{1}{N}\sum_{i}[y_i \log p_i + (1-y_i)\log(1-p_i)]$$

- Range: [0, ∞).  Lower is better.

### ROC AUC (`compute_roc_auc`)

Area under the Receiver Operating Characteristic curve; computed via the
trapezoidal rule.

- Range: [0, 1].  AUC = 0.5 is random; AUC = 1.0 is perfect.

### Average Precision (`compute_average_precision`)

Area under the Precision–Recall curve; more informative than AUC for
imbalanced datasets (as is typical for NEO detection).

### F1 Score (`compute_f1_score`)

$$F_1 = \frac{2 \cdot \text{precision} \cdot \text{recall}}{\text{precision} + \text{recall}}$$

Computed at a user-supplied decision threshold (default 0.5).

### Brier Skill Score (`compute_brier_skill_score`)

$$\text{BSS} = 1 - \frac{\text{BS}_\text{model}}{\text{BS}_\text{climatology}}$$

where BS_climatology = base_rate × (1 − base_rate).

- BSS = 1.0: perfect skill.
- BSS = 0.0: no improvement over climatology.
- BSS < 0.0: worse than always predicting the base rate.
- Returns 0.0 for all-same-label datasets (BS_climatology = 0).

### Calibration Sharpness (`compute_calibration_sharpness`)

Mean of max(p, 1 − p) across all predictions.  Sharp models push predictions
away from 0.5; uncertain models cluster near 0.5.

- Range: [0.5, 1.0].  Higher = sharper (but not necessarily better calibrated).

---

## Reliability Diagram

`reliability_diagram(probs, labels, n_bins=10)` partitions predictions into
equal-width bins and reports the observed fraction positive per bin.  Ideal
calibration lies on the diagonal (mean confidence = fraction positive).

---

## Bootstrap Confidence Intervals

`bootstrap_confidence_interval(probs, labels, n_bootstrap=1000, metric="brier")`
returns a 95% CI (lower, upper) for the chosen metric by resampling with
replacement.

---

## Cross-Validation

`cross_validate_calibration(probs, labels, n_folds=5, metric="brier")` returns
(mean, std) of the chosen metric across K stratified folds.

---

## Usage Example

```python
from calibration import (
    brier_score,
    compute_brier_skill_score,
    expected_calibration_error,
    compute_roc_auc,
    calibration_report,
)
import numpy as np

probs = np.array([0.9, 0.8, 0.3, 0.1])
labels = np.array([1, 1, 0, 0])

bs = brier_score(probs, labels)          # Brier score
bss = compute_brier_skill_score(probs, labels)  # Skill score
ece = expected_calibration_error(probs, labels)
auc = compute_roc_auc(probs, labels)
report = calibration_report(probs, labels)
```

---

## See Also

- `Skills/plot_calibration.py` — reliability diagram plot + metric summary
- `Skills/evaluate_calibration.py` — Brier/ECE evaluation for Platt / isotonic
- `docs/CLASSIFICATION_GUIDE.md` — three-tier ML calibration integration
