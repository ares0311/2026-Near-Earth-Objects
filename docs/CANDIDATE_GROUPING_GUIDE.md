# Candidate Grouping Guide

## Overview

The `CandidateGrouping` schema and related helpers allow the pipeline to organise scored NEO candidates into named groups by field and night. This is useful for per-field statistics, follow-up scheduling, and reporting.

## Schema: `CandidateGrouping`

```python
class CandidateGrouping(BaseModel):
    model_config = ConfigDict(frozen=True)
    group_id: str
    field_id: str | None = None
    night_jd: float | None = None
    candidate_ids: tuple[str, ...] = ()
    n_candidates: int = 0
    dominant_hazard_flag: str = "unknown"
```

| Field | Type | Description |
|---|---|---|
| `group_id` | `str` | Unique identifier for this grouping |
| `field_id` | `str \| None` | Survey field identifier (e.g. ZTF field number) |
| `night_jd` | `float \| None` | JD of the observing night |
| `candidate_ids` | `tuple[str, ...]` | Object IDs of members |
| `n_candidates` | `int` | Count of members |
| `dominant_hazard_flag` | `str` | Most common hazard flag in the group |

## Related Helper Functions

### `compute_magnitude_range(observations)` — detect.py

Returns the range (max − min) of valid magnitudes across a list of observations. Excludes sentinel magnitudes (≥ 90) and `None` values. Returns `None` if fewer than 2 valid magnitudes are found.

```python
from detect import compute_magnitude_range
mag_range = compute_magnitude_range(obs_list)  # float | None
```

### `compute_arc_endpoint_separation(tracklet)` — link.py

Computes the great-circle angular separation in arcseconds between the first and last observation of a tracklet. Returns `None` if the tracklet has fewer than 2 observations.

```python
from link import compute_arc_endpoint_separation
sep_arcsec = compute_arc_endpoint_separation(tracklet)  # float | None
```

### `compute_real_bogus_summary(neos)` — classify.py

Aggregates real/bogus score statistics across a list of scored NEOs. Returns a dict with `mean`, `min`, `max`, and `n` keys. Stats are `None` if no valid scores are found.

```python
from classify import compute_real_bogus_summary
summary = compute_real_bogus_summary(neo_list)
# {'mean': 0.85, 'min': 0.72, 'max': 0.94, 'n': 12}
```

### `compute_orbital_speed_at_perihelion(elements)` — orbit.py

Estimates orbital speed at perihelion using the vis-viva equation. Returns speed in km/s, or `None` if orbital elements are unavailable or the result would be non-physical.

```python
from orbit import compute_orbital_speed_at_perihelion
speed = compute_orbital_speed_at_perihelion(elements)  # float | None (km/s)
```

### `compute_moid_hazard_score(neo)` — score.py

Returns a [0, 1] hazard score derived from MOID: `1 − clip(moid_au / 0.5, 0, 1)`. Returns 0.5 if MOID is unknown.

```python
from score import compute_moid_hazard_score
hazard_score = compute_moid_hazard_score(neo)  # float in [0, 1]
```

### `compute_survey_overlap(result1, result2)` — fetch.py

Returns the Jaccard overlap fraction between two `FetchResult` observation sets, based on `obs_id`. Returns 0.0 if either result has no observations.

```python
from fetch import compute_survey_overlap
overlap = compute_survey_overlap(result_a, result_b)  # float in [0, 1]
```

### `compute_cutout_entropy_normalized(obs)` — preprocess.py

Returns the normalised Shannon entropy of a difference-image cutout pixel distribution, in [0, 1]. Returns `None` if no cutout is available.

```python
from preprocess import compute_cutout_entropy_normalized
entropy = compute_cutout_entropy_normalized(obs)  # float | None
```

### `format_observation_count_summary(neos)` — alert.py

Counts total observations and breaks them down by mission (survey) across all scored NEO candidates. Includes a mandatory guardrail statement.

```python
from alert import format_observation_count_summary
summary = format_observation_count_summary(neo_list)
# {'total_observations': 42, 'by_mission': {'ZTF': 30, 'ATLAS': 12}, ...}
```

### `compute_calibration_gap(probs, labels, n_bins)` — calibration.py

Returns the mean absolute calibration gap: the average of |predicted probability − observed frequency| across reliability diagram bins. Returns 0.0 for empty inputs.

```python
from calibration import compute_calibration_gap
gap = compute_calibration_gap(probs, labels, n_bins=10)  # float ≥ 0
```

## Skills

| Script | Purpose |
|---|---|
| `Skills/compute_magnitude_ranges.py` | Batch magnitude range per tracklet from JSON; `--json` flag |
| `Skills/compute_orbital_speeds.py` | Batch perihelion speed per tracklet from JSON; `--json` flag |

## Guardrails

- `CandidateGrouping` objects reflect pipeline groupings only. Members are **NOT** confirmed NEOs.
- `format_observation_count_summary` always includes a guardrail statement with "NOT".
- Never use internal groupings to assert impact probabilities. Defer to MPC/CNEOS.
