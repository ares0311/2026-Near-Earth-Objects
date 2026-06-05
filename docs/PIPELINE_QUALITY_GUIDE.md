# Pipeline Quality Guide

This document covers pipeline quality helpers across
`preprocess.py`, `detect.py`, `link.py`, `score.py`, and `calibration.py` (v0.86.0).

---

## Photometric Noise Level

### `compute_photometric_noise_level(observations)` — preprocess.py

Median absolute deviation (MAD) of valid observation magnitudes.
Provides a robust estimate of photometric noise that is insensitive to outliers.
Sentinel magnitudes (≥ 90) are excluded.  Returns `None` for fewer than 2 valid mags.

```python
from preprocess import compute_photometric_noise_level
from types import SimpleNamespace

obs = [SimpleNamespace(mag=20.0), SimpleNamespace(mag=20.3), SimpleNamespace(mag=19.8)]
mad = compute_photometric_noise_level(obs)
# e.g. 0.2
```

---

## Candidate Sky Density

### `compute_candidate_sky_density(result, field_radius_deg)` — detect.py

Candidates per square degree for a circular survey field.
Uses the solid-angle formula: area = 2π(1 − cos r) sr, converted to square degrees.
Returns 0.0 for empty candidate lists or non-positive radius.

```python
from detect import compute_candidate_sky_density
density = compute_candidate_sky_density(detect_result, field_radius_deg=1.5)
# e.g. 3.7 candidates/sq-deg
```

---

## Maximum Observation Gap

### `compute_max_observation_gap(tracklet)` — link.py

Maximum gap in days between consecutive observations, sorted by JD.
Returns `None` for fewer than 2 observations.

A large gap may indicate a poor-quality tracklet or multi-night linking challenge.

```python
from link import compute_max_observation_gap
gap = compute_max_observation_gap(tracklet)
# e.g. 2.5 days
```

---

## Candidate Priority Spread

### `compute_candidate_priority_spread(neos)` — score.py

Standard deviation of discovery_priority values across all scored NEOs.
Returns 0.0 if fewer than 2 candidates have valid priority values.

A high spread indicates a well-differentiated candidate list;
a low spread suggests candidates are similarly ranked.

```python
from score import compute_candidate_priority_spread
spread = compute_candidate_priority_spread(scored_neos)
# e.g. 0.23
```

Use `Skills/compute_candidate_priority_spreads.py` for a CLI interface.

---

## Positive Predictive Value

### `compute_positive_predictive_value(probs, labels, threshold=0.5)` — calibration.py

Precision (PPV) at a given probability threshold:

    PPV = TP / (TP + FP)

Returns 0.0 for empty input or no positive predictions above threshold.

```python
from calibration import compute_positive_predictive_value
ppv = compute_positive_predictive_value(probs, labels, threshold=0.7)
# e.g. 0.85
```

---

## Orbit Complexity

### `compute_orbit_complexity(elements)` — orbit.py

Scalar complexity index in [0, 1] combining eccentricity and inclination:

    complexity = 0.5 × min(e, 1) + 0.5 × min(|i|, 90) / 90

- 0.0 = circular, equatorial orbit
- 1.0 = parabolic/hyperbolic, polar orbit
- Returns 0.0 for missing attributes

---

## Guardrails

All pipeline quality metrics are internal diagnostics.
They do NOT constitute confirmed NEO detections or hazard assessments.
Follow the alert protocol in `docs/ALERT_PROTOCOL.md` for external reporting.
