# Survey Statistics Guide

This document covers all survey-statistics helpers across the pipeline
modules (v0.82.0).

---

## Temporal Coverage

### `compute_temporal_coverage(fetch_result)` — fetch.py

Returns a dict with `n_observations`, `min_jd`, `max_jd`, `span_days`, and
`n_nights` for a `FetchResult`.  `None` for empty inputs.

---

## Observation Rate

### `compute_observation_rate(fetch_result)` — fetch.py

Mean observations per night over the time window spanned by the fetch result.
Returns `None` if fewer than 2 distinct nights are present.

---

## Magnitude Distribution

### `compute_magnitude_distribution(fetch_result, n_bins=10)` — fetch.py

Equal-width histogram of alert magnitudes:

```python
from fetch import compute_magnitude_distribution
hist = compute_magnitude_distribution(fetch_result, n_bins=10)
# {'bin_edges': [14.0, 15.4, ...], 'counts': [3, 12, ...], 'n_total': 85}
```

Sentinel magnitudes ≥ 90 are excluded.

Use `Skills/compute_magnitude_distributions.py` for a CLI interface.

---

## Group Observations by Night

### `group_observations_by_night(fetch_result)` — fetch.py

Groups all observations in a `FetchResult` by integer night (floor of JD).
Returns a `dict[int, list[Observation]]`.  Observations with non-finite JDs
are silently skipped.

```python
from fetch import group_observations_by_night
groups = group_observations_by_night(fetch_result)
# {2460000: [obs1, obs2, ...], 2460001: [...], ...}
```

Use `Skills/group_observations_by_night.py` for a CLI per-night summary.

---

## Observation Cadence

### `estimate_observation_cadence(tracklet)` — link.py

Mean time between consecutive observations in hours.  Returns `None` for
fewer than 2 observations.

```python
from link import estimate_observation_cadence
cadence_hr = estimate_observation_cadence(tracklet)
```

---

## Field Tracklet Density

### `compute_field_tracklet_density(tracklets, field_radius_deg)` — link.py

Tracklets per square degree for a circular field, using the solid-angle
formula Ω = 2π(1 − cos r).  Returns `None` for non-positive radius.

---

## Survey Depth

### `estimate_survey_depth(fetch_result)` — fetch.py

95th-percentile magnitude from valid alerts; `None` if no valid magnitudes.

---

## Guardrails

All survey-statistics outputs are internal pipeline diagnostics only.
No output implies a confirmed NEO detection or Earth-impact probability.
Follow the alert protocol in `docs/ALERT_PROTOCOL.md` for external reporting.
