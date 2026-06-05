# Batch Statistics Guide

This document covers batch aggregation and statistical helpers added in v0.87.0
across `schemas.py`, `fetch.py`, `preprocess.py`, `detect.py`, `link.py`,
`classify.py`, `orbit.py`, `score.py`, `alert.py`, and `calibration.py`.

---

## Survey Night Record

### `SurveyNightRecord` — schemas.py

Frozen model summarising one survey night at a high level.

| Field | Type | Description |
|---|---|---|
| `night_jd` | `float \| None` | Integer-floor Julian Date of the night |
| `survey` | `str` | Survey name (e.g. "ZTF") |
| `n_obs` | `int` | Total observations collected |
| `n_tracklets` | `int` | Tracklets formed from this night |
| `limiting_mag` | `float \| None` | Survey depth estimate |
| `area_sq_deg` | `float \| None` | Sky area covered in square degrees |

```python
from schemas import SurveyNightRecord
rec = SurveyNightRecord(night_jd=2460000.5, survey="ZTF", n_obs=342, n_tracklets=12)
```

---

## Observation Time Span

### `compute_observation_time_span(fetch_result)` — fetch.py

Total time span in days covered by valid observations (max JD − min JD).
Returns `None` if fewer than 2 valid (finite) JDs exist.

```python
from fetch import compute_observation_time_span
span = compute_observation_time_span(fetch_result)
# e.g. 3.5 days
```

Use `Skills/compute_observation_time_spans.py` for a CLI interface.

---

## Cutout Dynamic Range

### `compute_cutout_dynamic_range(obs)` — preprocess.py

Peak-to-trough pixel range of the float32 difference-image cutout:

    dynamic_range = max(pixels) − min(pixels)

Returns `None` if the cutout is absent, empty, or cannot be decoded.
A high dynamic range indicates a bright source relative to local background.

```python
from preprocess import compute_cutout_dynamic_range
dr = compute_cutout_dynamic_range(obs)
# e.g. 1250.3 (ADU)
```

---

## Detection Gap Days

### `compute_detection_gap_days(result)` — detect.py

Maximum JD gap between consecutive candidate detections (sorted by JD).
Returns `None` for fewer than 2 candidates or if no valid JDs exist.

A large gap may indicate a multi-night candidate list or missed observations.

```python
from detect import compute_detection_gap_days
gap = compute_detection_gap_days(detect_result)
# e.g. 2.1 days
```

---

## Inter-Night Motion

### `compute_inter_night_motion(tracklet)` — link.py

Mean angular displacement between consecutive distinct observing nights in
arcsec/night.  Night centroids are computed from mean RA/Dec of observations
on each integer-JD night; great-circle separation is used.

Returns `None` for fewer than 2 distinct nights.

```python
from link import compute_inter_night_motion
motion = compute_inter_night_motion(tracklet)
# e.g. 145.3 arcsec/night
```

---

## Classification Entropy Summary

### `compute_classification_entropy_summary(neos)` — classify.py

Aggregate statistics of Shannon entropy across all scored NEOs:

    result = {
        "mean_entropy": ...,
        "std_entropy": ...,
        "min_entropy": ...,
        "max_entropy": ...,
    }

Returns an empty dict if no NEOs have a valid posterior.
Low entropy indicates confident (peaked) posteriors; high entropy means
uncertain classification.

```python
from classify import compute_classification_entropy_summary
summary = compute_classification_entropy_summary(scored_neos)
print(summary["mean_entropy"])
```

---

## Mean Longitude

### `compute_mean_longitude(elements)` — orbit.py

Mean longitude of the orbit in degrees, normalised to [0, 360):

    λ = Ω + ω + M₀  (mod 360°)

where Ω is the longitude of ascending node, ω is the argument of perihelion,
and M₀ is the mean anomaly at epoch.  Returns `None` for missing attributes.

```python
from orbit import compute_mean_longitude
lam = compute_mean_longitude(orbital_elements)
# e.g. 217.4 degrees
```

---

## Batch Priority Statistics

### `compute_batch_priority_stats(neos)` — score.py

Aggregate statistics of `discovery_priority` across all scored NEOs:

    result = {"mean": ..., "std": ..., "min": ..., "max": ...}

Returns an empty dict if no NEOs have a valid priority.

```python
from score import compute_batch_priority_stats
stats = compute_batch_priority_stats(scored_neos)
print(f"Mean priority: {stats['mean']:.3f}, spread: {stats['std']:.3f}")
```

Use `Skills/compute_batch_priority_stats.py` for a CLI interface.

---

## Alert Pathway Summary

### `format_alert_pathway_summary(neos)` — alert.py

Multi-line text block showing pathway counts and percentages, sorted by
frequency descending.  Returns `"No candidates."` for empty input.

```python
from alert import format_alert_pathway_summary
print(format_alert_pathway_summary(scored_neos))
# Alert pathway summary (12 candidates):
#   internal_candidate              8  ( 66.7%)
#   mpc_submission                  3  ( 25.0%)
#   neocp_followup                  1  (  8.3%)
```

---

## Negative Predictive Value

### `compute_negative_predictive_value(probs, labels, threshold=0.5)` — calibration.py

NPV measures how well below-threshold predictions correspond to true negatives:

    NPV = TN / (TN + FN)

Returns 0.0 for empty input or no negative predictions below threshold.

```python
from calibration import compute_negative_predictive_value
npv = compute_negative_predictive_value(probs, labels, threshold=0.5)
# e.g. 0.92
```

---

## Guardrails

All batch statistics helpers are internal diagnostics.
They do NOT constitute confirmed NEO detections or hazard assessments.
Follow the alert protocol in `docs/ALERT_PROTOCOL.md` for external reporting.
