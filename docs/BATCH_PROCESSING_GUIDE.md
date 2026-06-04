# Batch Processing Guide

This document describes the `BatchProcessingResult` schema and batch-oriented
helper functions added in v0.79.0.

---

## BatchProcessingResult Schema

`BatchProcessingResult` (in `schemas.py`) is an immutable Pydantic model that
summarises the outcome of a single batch run through the NEO pipeline.

```python
from schemas import BatchProcessingResult

result = BatchProcessingResult(
    batch_id="2026-06-04T00:00:00Z",
    n_input=500,
    n_detected=420,
    n_linked=310,
    n_scored=295,
    n_pha_candidates=3,
    elapsed_seconds=47.2,
    pipeline_version="0.79.0",
)
```

| Field | Type | Description |
|---|---|---|
| `batch_id` | `str` | Unique identifier for the batch run (e.g. ISO timestamp) |
| `n_input` | `int` | Raw alert / observation count entering the batch |
| `n_detected` | `int` | Candidates surviving the detection gate |
| `n_linked` | `int` | Tracklets formed after linking |
| `n_scored` | `int` | Scored NEO candidates produced |
| `n_pha_candidates` | `int` | Candidates flagged `pha_candidate` |
| `elapsed_seconds` | `float` | Wall-clock time for the full batch |
| `pipeline_version` | `str` | Version of the pipeline that produced the result |

---

## New Batch Helper Functions (v0.79.0)

### `compute_temporal_coverage(fetch_result)` — fetch.py

Returns a dict summarising the JD span covered by a FetchResult:

```python
from fetch import compute_temporal_coverage
summary = compute_temporal_coverage(fetch_result)
# {'n_observations': 42, 'min_jd': 2460000.5, 'max_jd': 2460003.5,
#  'span_days': 3.0, 'n_nights': 4}
```

Useful for checking whether a batch covers the expected time window before
running the full pipeline.

### `compute_pixel_saturation_fraction(obs, saturation_threshold=0.98)` — preprocess.py

Returns the fraction of science-cutout pixels at or above the saturation
threshold (normalised to [0, 1]).  Values near 1.0 indicate a saturated source
that should be flagged for review.

### `count_streak_detections(detect_result)` — detect.py

Returns the integer count of streak/trail candidates in a `DetectResult`.
High streak counts indicate either a fast-moving NEO population or satellite
trail contamination.

### `compute_sky_coverage_area(tracklets)` — link.py

Returns the approximate bounding-box sky area in square degrees covered by
a list of tracklets, corrected for the spherical projection via cos(mean Dec).
Useful for estimating the effective survey area of a batch.

### `compute_neo_class_distribution(neos)` — classify.py

Returns a per-class dict of `{"count": int, "fraction": float}` values across
all scored candidates.  Diagnose class imbalance before retraining.

### `compute_geocentric_velocity(elements)` — orbit.py

Returns the inclination-corrected encounter velocity in km/s:

```
v_enc = sqrt(v_obj² + v_Earth² − 2·v_obj·v_Earth·cos(i))
```

where `v_obj` is the vis-viva speed at perihelion and `v_Earth = 29.78 km/s`.
This is the rigorous vector-subtraction formula — see `docs/ORBIT_FITTING.md`
for derivation notes.

### `compute_priority_histogram(neos, n_bins=5)` — score.py

Returns a histogram dict `{"bin_edges", "counts", "n_total"}` of
`discovery_priority` values.  Use with `Skills/compute_priority_histograms.py`
for a quick ranked-candidate distribution plot.

### `format_mpc_observation_block(neo, obs_code=...)` — alert.py

Returns a paste-ready multi-line string of MPC 80-column observation records,
one line per observation.  The first observation is marked as the discovery
observation (asterisk in column 6).

**Guardrail**: This function formats observations only.  It does NOT submit
data and does NOT assert that the candidate is a confirmed NEO.

### `compute_calibration_bias(probs, labels)` — calibration.py

Returns `mean(predicted_probability) − fraction_positive`.  Positive values
indicate over-confidence; negative values indicate under-confidence.

---

## Skills Scripts

| Script | Description |
|---|---|
| `Skills/compute_temporal_coverages.py` | Print or JSON-export temporal coverage from tracklet JSON |
| `Skills/compute_priority_histograms.py` | Print or JSON-export discovery-priority histogram; `--bins N` flag |

---

## Guardrails

All batch results are internal pipeline outputs only.  No batch result implies
a confirmed NEO detection or Earth-impact probability.  Follow the alert
protocol in `docs/ALERT_PROTOCOL.md` before any external reporting.
