# Filtering and Distribution Guide

This document covers all filter helpers and histogram/distribution functions
across the pipeline modules (v0.16–v0.81).

---

## Filter Functions

### Detection-Level Filters

#### `filter_by_real_bogus(result, threshold=0.65)` — detect.py
Keeps candidates where max real/bogus score ≥ threshold. Candidates without
scores are kept (conservative default).

#### `filter_by_magnitude(result, max_mag)` — detect.py
Keeps candidates with at least one observation brighter than *max_mag*.

#### `filter_by_streak_score(result, min_streak_score=0.5)` — detect.py
Keeps candidates where max `compute_streak_metric` across observations ≥
threshold. Use to isolate fast-moving or trailed sources.

```python
from detect import filter_by_streak_score
streaky = filter_by_streak_score(detect_result, min_streak_score=0.6)
```

### Link-Level Filters

#### `filter_by_arc_length(tracklets, min_arc_days=1.0)` — link.py
Keeps tracklets with arc_days ≥ threshold.

#### `filter_by_nights_observed(tracklets, min_nights=2)` — link.py
Keeps tracklets spanning ≥ min distinct integer-JD nights.

#### `filter_high_motion(tracklets, min_rate_arcsec_hr=10)` — link.py
Keeps tracklets above a motion rate threshold.

### Score-Level Filters

#### `pha_candidates(neos)` — score.py
Returns only `ScoredNEO` candidates flagged `pha_candidate`.

#### `close_approach_candidates(neos, max_moid_au=0.05)` — score.py
Returns candidates with MOID ≤ threshold (None MOID excluded).

#### `filter_by_alert_pathway(neos, pathway)` — score.py
Exact match on `alert_pathway` field.

#### `filter_by_discovery_priority(neos, min_priority=0.5)` — score.py
Keeps candidates with `metadata.discovery_priority ≥ min_priority`.

```python
from score import filter_by_discovery_priority
high_pri = filter_by_discovery_priority(neos, min_priority=0.7)
```

Use `Skills/filter_priority_candidates.py` for a CLI interface.

### Fetch-Level Filters

#### `filter_by_survey(fetch_result, surveys)` — fetch.py
Keeps observations from the specified mission list.

#### `filter_alerts_by_motion(alerts, min_rate, max_rate)` — fetch.py
Filters by motion proxy based on `ssdistnr`.

---

## Distribution and Histogram Functions

### `compute_magnitude_distribution(fetch_result, n_bins=10)` — fetch.py

Equal-width histogram of alert magnitudes:

```python
from fetch import compute_magnitude_distribution
hist = compute_magnitude_distribution(fetch_result, n_bins=10)
# {'bin_edges': [14.0, 15.4, ...], 'counts': [3, 12, ...], 'n_total': 85}
```

Use `Skills/compute_magnitude_distributions.py` for a CLI interface.

### `compute_priority_histogram(neos, n_bins=5)` — score.py

Equal-width histogram of `discovery_priority` values across scored NEOs.

### `compute_tier1_score_distribution(neos)` — classify.py

Summary of Tier 1 score distributions (mean, std, percentiles).

### `compute_neo_class_distribution(neos)` — classify.py

Per-class count and fraction across scored candidates:

```python
from classify import compute_neo_class_distribution
dist = compute_neo_class_distribution(neos)
# {'apollo': {'count': 5, 'fraction': 0.5}, 'amor': {'count': 3, 'fraction': 0.3}, ...}
```

### `batch_dominant_hypothesis(neos)` — classify.py

List of `{object_id, hypothesis, probability}` dicts — quick hypothesis audit:

```python
from classify import batch_dominant_hypothesis
rows = batch_dominant_hypothesis(neos)
# [{'object_id': 'T001', 'hypothesis': 'neo_candidate', 'probability': 0.75}, ...]
```

---

## Density Functions

### `compute_detection_density(candidates, field_radius_deg)` — detect.py
Raw candidate density (candidates per sq-deg).

### `compute_field_tracklet_density(tracklets, field_radius_deg)` — link.py
Linked tracklet density (tracklets per sq-deg) for a complete survey field.

### `compute_sky_coverage_area(tracklets)` — link.py
Bounding-box area in sq-deg covered by a tracklet list.

---

## Calibration Error Metrics

### `compute_expected_calibration_error(probs, labels, n_bins=10)` — calibration.py
Equal-width ECE: weighted average bin-wise |prob − fraction_positive|.

### `compute_max_calibration_error(probs, labels, n_bins=10)` — calibration.py
MCE: maximum over non-empty bins of |mean_prob − fraction_positive|.

```python
from calibration import compute_max_calibration_error
mce = compute_max_calibration_error(probs, labels, n_bins=10)
```

---

## Guardrails

All filtered and histogrammed outputs are internal pipeline results only.
No filter result implies a confirmed NEO detection or Earth-impact probability.
Follow the alert protocol in `docs/ALERT_PROTOCOL.md` for external reporting.
