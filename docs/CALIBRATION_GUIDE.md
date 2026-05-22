# Calibration Guide

Technical reference for `src/calibration.py` — probability calibration, metric
computation, and evaluation tools for the NEO detection pipeline.

---

## Overview

Raw ML classifier scores are not automatically calibrated probabilities.
A score of 0.8 from an XGBoost model does not guarantee that 80% of such
candidates are genuine NEOs.  Calibration maps raw scores to reliable
posterior probabilities so that downstream scoring, hazard assessment, and
alert decisions are well-founded.

The `calibration.py` module provides:

- Two calibrators: **Platt scaling** (parametric) and **isotonic regression** (non-parametric)
- Calibration metrics: Brier score, ECE, log loss, ROC AUC, average precision, F1
- Reliability diagrams for visual calibration assessment
- Bootstrap confidence intervals and K-fold cross-validation
- Comparison utilities for multiple calibrators

---

## Platt Scaling

Platt scaling fits a sigmoid function to the raw classifier scores:

```
P(y=1 | f) = 1 / (1 + exp(A·f + B))
```

where `A` and `B` are learned by minimising the binary cross-entropy on a
held-out calibration set.  The implementation uses the modified target labels
from Platt (1999) to prevent overfitting to hard 0/1 targets:

```
t+ = (N+ + 1) / (N+ + 2)
t- = 1 / (N- + 2)
```

**When to use Platt scaling:**
- Small calibration sets (< 1,000 examples)
- The raw score distribution is roughly sigmoidal
- Speed matters (only 2 parameters to fit)
- Tier 1 XGBoost output (well-separated bimodal distribution)

**Usage:**

```python
from calibration import PlattCalibrator

cal = PlattCalibrator()
cal.fit(scores_train, labels_train)
calibrated_probs = cal.predict(scores_test)
cal.save("tier1_rb")  # saves to models/calibration/tier1_rb_platt.npz
```

---

## Isotonic Regression (PAVA)

Isotonic regression finds the best-fit non-decreasing step function mapping
raw scores to probabilities, using the **Pool Adjacent Violators Algorithm
(PAVA)**.  It is non-parametric and can fit arbitrary monotone shapes.

**When to use isotonic regression:**
- Large calibration sets (> 1,000 examples)
- The raw score distribution has a non-sigmoid shape
- The classifier produces plateau or multi-modal output
- Tier 2 CNN or Tier 3 Transformer output (complex output distributions)

**Usage:**

```python
from calibration import IsotonicCalibrator

cal = IsotonicCalibrator()
cal.fit(scores_train, labels_train)
calibrated_probs = cal.predict(scores_test)
cal.save("tier2_cnn")  # saves to models/calibration/tier2_cnn_isotonic.npz
```

**Caution:** Isotonic regression can overfit on small sets; use cross-validation
to verify generalisation before deployment.

---

## Reliability Diagram (Calibration Curve)

A reliability diagram plots mean predicted probability against fraction of
true positives within equal-width probability bins.  A perfectly calibrated
classifier lies on the diagonal `y = x`.

```python
from calibration import reliability_diagram

diagram = reliability_diagram(probs, labels, n_bins=10)
# Returns: {"bin_centers": [...], "fraction_positive": [...], "bin_counts": [...]}
```

Use `Skills/plot_calibration.py` to generate a PNG:

```bash
python Skills/plot_calibration.py data/scored_neos.json --out calibration.png
```

---

## Expected Calibration Error (ECE)

ECE measures the weighted average absolute difference between predicted
probability and actual fraction of positives across M equal-width bins:

```
ECE = Σ_m (|B_m| / n) × |acc(B_m) - conf(B_m)|
```

where `|B_m|` is the number of samples in bin m, `n` is total samples,
`acc(B_m)` is the fraction of true positives, and `conf(B_m)` is the mean
predicted probability.

**Interpretation:**
- ECE = 0.0: Perfect calibration
- ECE < 0.05: Well calibrated (acceptable for pipeline use)
- ECE > 0.10: Poorly calibrated; recalibration required before alert decisions

```python
from calibration import expected_calibration_error

ece = expected_calibration_error(probs, labels, n_bins=10)
```

---

## ROC AUC

The Area Under the Receiver Operating Characteristic curve measures a
classifier's ability to separate positive from negative classes regardless
of threshold.  Computed via the trapezoidal rule.

```
AUC = ∫ TPR d(FPR)
```

**Interpretation:**
- AUC = 1.0: Perfect discrimination
- AUC = 0.5: Random classifier (no discrimination)
- AUC < 0.7: Unacceptable for pipeline gating

```python
from calibration import compute_roc_auc

auc = compute_roc_auc(probs, labels)
```

NumPy compatibility: uses `np.trapezoid` (NumPy ≥ 2.0) with fallback to
`np.trapz` (NumPy 1.x).

---

## PR Curve and Average Precision

The Precision-Recall curve is more informative than ROC for imbalanced
datasets (e.g., NEO candidates are rare).  Average Precision (AP) is the
area under the PR curve, anchored at (recall=0, precision=1):

```python
from calibration import compute_precision_recall_curve

result = compute_precision_recall_curve(probs, labels)
# result["average_precision"]: AP in [0, 1]
# result["precisions"], result["recalls"], result["thresholds"]: curve arrays
```

**Interpretation:**
- AP = 1.0: Perfect ranking
- AP ≈ base_rate: No useful ranking above chance
- Aim for AP > 0.8 at Tier 1 before progressing to Tier 2 training

---

## F1 Score at Threshold

F1 is the harmonic mean of precision and recall at a fixed decision threshold.
Use it to characterise the operating point actually used in the pipeline.

```
precision = TP / (TP + FP)
recall    = TP / (TP + FN)
F1        = 2 × precision × recall / (precision + recall)
```

```python
from calibration import compute_f1_score

metrics = compute_f1_score(probs, labels, threshold=0.65)
# {"precision": 0.82, "recall": 0.76, "f1": 0.79, "threshold": 0.65, "n_samples": 500}
```

The default threshold of 0.5 rarely matches the operational threshold.
Always evaluate F1 at the actual detection gate (e.g., `rb ≥ 0.65`).

---

## Log Loss (Binary Cross-Entropy)

Log loss penalises confident wrong predictions more than uncertain ones:

```
L = -(1/n) Σ [y·log(p) + (1-y)·log(1-p)]
```

```python
from calibration import compute_log_loss

ll = compute_log_loss(probs, labels)
```

**Interpretation:**
- Perfect calibration gives log loss ≈ binary entropy of the base rate
- Log loss > 0.5 with a base rate of 5% NEOs indicates poor calibration

---

## Bootstrap Confidence Intervals

Estimate uncertainty in any metric via non-parametric bootstrapping (1,000
resamples by default):

```python
from calibration import bootstrap_confidence_interval

lo, hi = bootstrap_confidence_interval(probs, labels, n_bootstrap=1000, metric="brier")
print(f"Brier 95% CI: [{lo:.4f}, {hi:.4f}]")
```

Supported metrics: `"brier"`, `"ece"`.

---

## K-Fold Cross-Validation of Calibration

Evaluate calibration stability across data splits before deployment:

```python
from calibration import cross_validate_calibration

mean_ece, std_ece = cross_validate_calibration(probs, labels, n_folds=5, metric="ece")
print(f"ECE: {mean_ece:.4f} ± {std_ece:.4f}")
```

---

## When to Use Platt vs Isotonic

| Condition | Recommendation |
|---|---|
| Calibration set < 500 samples | Platt scaling |
| Calibration set > 1,000 samples | Isotonic regression |
| Score distribution is sigmoid-shaped | Platt scaling |
| Score distribution is irregular / plateau | Isotonic regression |
| Tier 1 (XGBoost/LightGBM) | Platt scaling |
| Tier 2 (CNN) | Isotonic regression |
| Tier 3 (Transformer) | Isotonic regression |
| Speed-critical production path | Platt scaling |

When unsure, compare both with `compare_calibrators()`:

```python
from calibration import compare_calibrators

report = compare_calibrators(
    [platt_probs, isotonic_probs],
    labels,
    names=["platt", "isotonic"],
)
print(report["platt"]["brier_score"], report["isotonic"]["brier_score"])
```

---

## CLI Usage Examples

### Evaluate calibration on scored NEO output

```bash
python Skills/evaluate_calibration.py data/scored_neos.json
```

### Plot reliability diagram

```bash
python Skills/plot_calibration.py data/scored_neos.json --out calibration.png
```

The plot shows the reliability curve, bin counts, Brier score, ECE, and log loss.

### JSON output from evaluate_calibration

```bash
python Skills/evaluate_calibration.py data/scored_neos.json --json
```

Returns a JSON object with keys `brier_score`, `ece`, `log_loss`, `n_samples`,
`mean_prob`, `fraction_positive`.

---

## Calibration in the Pipeline

Calibration runs after each classifier tier via `calibrate()`:

```python
from calibration import calibrate, PlattCalibrator

cal = PlattCalibrator()
cal.fit(train_scores, train_labels)
calibrated = calibrate(raw_scores, cal)
```

The ensemble stacker (logistic regression over Tier 1 + Tier 2 + Tier 3
outputs) is also calibrated before generating the final `NEOPosterior`.

Calibrators are versioned and saved to `models/calibration/` with names
following the pattern `{tier}_{target}.npz`.  Always re-evaluate ECE after
retraining any tier.
