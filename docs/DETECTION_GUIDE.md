# Detection Guide

Technical reference for the `detect.py` module: moving-object detection from difference-image alerts, streak/trail identification, spatial clustering, known-object cross-matching, and detection efficiency.

---

## Overview

The detection stage takes preprocessed source catalogs and produces a `DetectResult` containing:

- `candidates` — raw moving-object candidates not matched to MPC known objects
- `known_matches` — candidates that correspond to catalogued solar system objects

Detection is **conservative by design** (DECISION-005): when in doubt, retain the candidate for downstream linking and scoring rather than suppressing it.

---

## Real/Bogus Filtering

The first gate is the ZTF real/bogus score (`rb`), a machine-learning classifier trained to distinguish genuine astrophysical sources from instrumental artefacts.

| Threshold | Behaviour |
|---|---|
| `rb_threshold = 0.65` (default) | Pass sources with `rb ≥ 0.65`; reject lower |
| `rb_threshold = 0.90` | Stricter; fewer artefacts but higher completeness loss |
| None | No RB gate; all sources pass (use for Tier 2/3 retraining only) |

The threshold is configurable in `PipelineConfig.real_bogus_threshold`.  Sources without an `rb` score (e.g. ATLAS observations) pass through by default.

```python
from detect import filter_by_real_bogus
filtered = filter_by_real_bogus(detect_result, threshold=0.80)
```

---

## Moving-Object Detection

After RB filtering, sources are compared across epochs to identify motion:

1. **Apparent motion rate** — computed from successive position differences; `0.01–60 arcsec/hr` is the allowed range for solar system objects.
2. **Motion consistency** — direction (position angle) is checked for consistency across ≥3 epochs.
3. **Streak detection** — very fast-moving NEOs (rate > ~15 arcsec/30 s exposure) will trail; the streak metric (`compute_streak_metric`) captures elongation from difference-image second moments.

```python
from detect import streak_candidates
streaks = streak_candidates(detect_result)  # filter DetectResult to streaks only
```

---

## PSF and Trail Metrics

Two diagnostic functions measure source morphology:

| Function | Returns | Notes |
|---|---|---|
| `compute_psf_fwhm(obs)` | FWHM in arcsec (float or None) | 2D Gaussian moment fit; None if no cutout |
| `compute_streak_metric(obs)` | Streak severity [0, 1] | 0 = point source, 1 = fully trailed |
| `compute_trail_length(obs)` | Trail length in arcsec (float or None) | From image second moments |

---

## Spatial Clustering

`cluster_detections` groups nearby detections into spatial clusters (greedy radius-based):

```python
from detect import cluster_detections
clusters = cluster_detections(observations, radius_arcsec=5.0)
```

Clustering is useful for:
- Grouping multiple detections of the same moving object within a single night
- Identifying crowded-field artefact clumps

---

## Sky Background Estimation

```python
from detect import estimate_sky_background
bg = estimate_sky_background(observations, percentile=25.0)
```

Returns the 25th-percentile pixel value across all difference-image cutouts — a lower-quartile background estimate.  Returns `None` if no valid cutouts are present.

---

## Detection Efficiency

`compute_detection_efficiency` provides a simple per-field efficiency proxy:

```python
from detect import compute_detection_efficiency
eff = compute_detection_efficiency(observations, limiting_mag=20.5)
# Returns fraction of observations with mag < limiting_mag
```

| Efficiency | Interpretation |
|---|---|
| > 0.90 | Good field conditions; most sources near or above the detection floor |
| 0.50–0.90 | Mixed conditions; check PSF quality and background |
| < 0.50 | Poor conditions; consider excluding from pipeline run |

---

## Known-Object Cross-Matching

After moving-object candidates are identified, they are cross-matched against MPC ephemerides via `fetch_mpc_known` (fetch.py):

- Match radius: 10 arcsec (configurable)
- Time window: ±5 minutes of observation epoch
- Output: `KnownMatch` objects stored in `DetectResult.known_matches`

Objects within the match radius are removed from the new-candidate list and stored separately for provenance.

---

## DetectionSummary Schema

The `DetectionSummary` schema (schemas.py) summarises a single detection run:

```python
from schemas import DetectionSummary

summary = DetectionSummary(
    field_id="ZTF_F001",
    epoch_jd=2460000.5,
    survey="ZTF",
    n_candidates=142,
    n_known_matches=137,
    n_new=5,
    limiting_mag=20.8,
)
```

| Field | Type | Description |
|---|---|---|
| `field_id` | `str` | Survey field identifier |
| `epoch_jd` | `float` | Julian Date of observation |
| `survey` | `Mission` | Survey that produced this run |
| `n_candidates` | `int` | Total raw candidates |
| `n_known_matches` | `int` | Matched to MPC catalog |
| `n_new` | `int` | Unmatched (new candidates) |
| `limiting_mag` | `float \| None` | 5σ limiting magnitude |

---

## Batch Detection

For multi-field pipeline runs:

```python
from detect import detect_batch
results = detect_batch(preprocess_results_list)
```

Each `PreprocessResult` in the list is processed independently, returning a list of `DetectResult` objects.

---

## Tuning Guidelines

1. **High artefact rate** → raise `rb_threshold` (0.75–0.85); accept higher false-negative rate
2. **Missing fast movers** → enable streak detection (`streak_score` gate); check `compute_psf_fwhm` for trail elongation
3. **Many known-object duplicates** → reduce cross-match radius; check ephemeris accuracy
4. **Low detection efficiency** → check limiting magnitude calibration via `Skills/photometric_calibration.py`

---

## References

- Duev, D.A., et al. "Real-bogus Classification for the Zwicky Transient Facility Using Deep Learning." *MNRAS*, 489, 2019.
- Bellm, E.C., et al. "The Zwicky Transient Facility: System Overview." *PASP*, 131, 2019.
- Masci, F.J., et al. "The Zwicky Transient Facility: Data Processing, Products, and Archive." *PASP*, 131, 2019.
