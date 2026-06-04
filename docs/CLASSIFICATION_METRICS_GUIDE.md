# Classification Metrics Guide

This document covers classification and calibration metric helpers
across `classify.py` and `calibration.py` (v0.83.0).

---

## Classification Metrics (classify.py)

### `posterior_entropy(posterior)` — classify.py
Shannon entropy of a `NEOPosterior` in bits; 0 = certainty, log2(5) ≈ 2.32 = maximum.

### `dominant_hypothesis(posterior)` — classify.py
Returns `(name, probability)` for the highest-probability class.

### `batch_dominant_hypothesis(neos)` — classify.py
List of `{object_id, hypothesis, probability}` dicts for each scored NEO.

### `count_by_dominant_hypothesis(neos)` — classify.py
Dict mapping each hypothesis name to the count of NEOs where it is dominant:

```python
from classify import count_by_dominant_hypothesis
counts = count_by_dominant_hypothesis(scored_neos)
# {'neo_candidate': 3, 'known_object': 12, 'stellar_artifact': 5, ...}
```

Use `Skills/count_by_hypothesis.py` for a CLI interface.

### `filter_by_neo_probability(neos, min_prob=0.5)` — classify.py
Filter `ScoredNEO` list by posterior `neo_candidate` probability.

### `compute_neo_class_distribution(neos)` — classify.py
Per-class count and fraction: `{'apollo': {'count': 5, 'fraction': 0.5}, ...}`.

### `summarize_classifications(neos)` — classify.py
Aggregate summary: total, dominant_hypothesis_counts, mean_entropy_bits,
mean_real_bogus_score, pha_candidate_count.

---

## Calibration Metrics (calibration.py)

### `compute_expected_calibration_error(probs, labels, n_bins=10)` — calibration.py
ECE: weighted average of bin-wise |mean_prob − fraction_positive|.

### `compute_max_calibration_error(probs, labels, n_bins=10)` — calibration.py
MCE: maximum over non-empty bins of |mean_prob − fraction_positive|.

### `compute_calibration_resolution(probs, labels, n_bins=10)` — calibration.py
Normalized resolution score [0, 1]; measures how well the model separates positives from negatives.

### `compute_fraction_calibrated(probs, labels, threshold=0.1, n_bins=10)` — calibration.py
Fraction of non-empty bins within `threshold` of perfect calibration:

```python
from calibration import compute_fraction_calibrated
frac = compute_fraction_calibrated(probs, labels, threshold=0.1)
# 0.8 → 80% of bins are within 0.1 of perfect calibration
```

### `compute_calibration_bias(probs, labels)` — calibration.py
Mean predicted probability minus fraction of positives (signed bias).

### `compute_overconfidence_fraction(probs, labels, threshold=0.7)` — calibration.py
Fraction of high-confidence predictions (prob ≥ threshold) that are wrong (label = 0).

### `calibration_report(probs, labels)` — calibration.py
Comprehensive dict: brier_score, ece, log_loss, n_samples, mean_prob, fraction_positive.

---

## Reliability Diagram

### `reliability_diagram(probs, labels, n_bins=10)` — calibration.py
Returns bin_centers, fraction_positive, bin_counts for plotting.

---

## Guardrails

All classification and calibration metrics are internal pipeline diagnostics.
They do NOT constitute confirmed NEO detections or hazard assessments.
Follow the alert protocol in `docs/ALERT_PROTOCOL.md` for external reporting.
