# Observation Quality Reference

This document describes the observation quality metrics computed by the NEO Detection Pipeline.

---

## Overview

Observation quality determines whether a detection is suitable for MPC reporting, orbit fitting, and hazard assessment. The pipeline evaluates quality at multiple stages:

1. **Image quality** — cutout sharpness, PSF FWHM, background level
2. **Astrometric quality** — positional residuals, scatter, great-circle fit
3. **Photometric quality** — SNR, zero-point stability, saturation flags
4. **Tracklet quality** — arc completeness, motion scatter, grade

---

## Cutout Sharpness (`compute_cutout_sharpness`)

**Module**: `preprocess.py`

Measures the sharpness of a difference-image cutout using the variance of the Laplacian:

```
sharpness = Var(Laplacian(cutout))
```

The 3×3 Laplacian kernel used is:
```
 0  1  0
 1 -4  1
 0  1  0
```

- **High value**: sharp PSF, well-subtracted background
- **Low value**: blurry image, poor subtraction, or cosmic ray
- Returns `None` if no cutout or base64 decode fails

---

## Magnitude Residual (`compute_magnitude_residual`)

**Module**: `detect.py`

The signed difference between observed and predicted magnitude:

```
residual = obs_mag - predicted_mag
```

- Returns `0.0` if either magnitude is a sentinel value (≥ 90)
- Useful for identifying photometric outliers or variable sources
- Large residuals indicate photometric problems or real variability

---

## Tracklet Motion Scatter (`compute_tracklet_motion_scatter`)

**Module**: `link.py`

The standard deviation of pairwise apparent motion rates (arcsec/hr) across consecutive observation pairs in a tracklet:

```
scatter = std(rate_i for each consecutive pair)
```

- Cosine-Dec corrected in RA
- Low scatter indicates consistent linear motion (solar system object)
- High scatter may indicate a spurious link or non-linear trajectory
- Returns `None` for fewer than 3 observations

---

## Arc Completeness Score (`compute_arc_completeness_score`)

**Module**: `score.py`

A composite metric combining arc coverage, nights observed, and orbit quality:

```
arc_completeness = 0.4 × arc_coverage_score
                 + 0.3 × nights_observed_score
                 + 0.3 × orbit_quality_score
```

- Bounded `[0, 1]`
- `1.0` = long arc over many nights with well-constrained orbit
- `0.0` = single-night detection with no orbit solution
- Missing components contribute 0.0

### Interpretation

| Score | Meaning |
|-------|---------|
| ≥ 0.8 | Excellent arc; suitable for MPC submission |
| 0.5–0.8 | Good arc; follow-up recommended before submission |
| 0.2–0.5 | Marginal arc; orbit highly uncertain |
| < 0.2 | Poor arc; candidate only |

---

## Real/Bogus Histogram (`compute_real_bogus_histogram`)

**Module**: `classify.py`

Histogram of real/bogus scores across a batch of observations. Prefers `deep_real_bogus` over `real_bogus` when available.

```python
{"bins": [0.0, 0.1, ..., 1.0], "counts": [...], "mean": float | None}
```

- 10 equal-width bins over [0, 1]
- Mean is computed from valid (non-None) scores
- An empty histogram is returned if no scores are available

A bimodal distribution (peaks near 0 and 1) is typical of well-separated real/bogus scores. A flat distribution may indicate calibration issues.

---

## Field Observation Summary (`FieldObservationSummary`)

**Module**: `schemas.py`

A frozen Pydantic model summarizing observations from a single pipeline epoch:

```python
class FieldObservationSummary(BaseModel):
    field_id: str
    epoch_jd: float
    survey: Mission
    n_sources: int       # total sources extracted
    n_moving: int        # sources with detectable motion
    n_known: int         # matched to MPC catalog
    n_new: int           # candidate new objects
    limiting_mag: float | None
```

Used by `Skills/assess_survey_coverage.py` and `Skills/export_survey_summary.py`.

---

## Hill Sphere Radius (`compute_hill_sphere_radius`)

**Module**: `orbit.py`

The approximate gravitational sphere of influence of the NEO:

```
r_H = q × (m / (3 × M_☉))^(1/3)
```

where mass `m` is estimated from the absolute magnitude H using:

```
diameter = 1329 / sqrt(p_v) × 10^(-H/5)   [km]
mass = (4/3) × π × (diameter/2)³ × ρ       [kg]
```

with default albedo `p_v = 0.14` and density `ρ = 2000 kg/m³`.

- Returns `None` for hyperbolic/parabolic orbits (`e ≥ 1`) or non-positive semi-major axis
- Very small Hill spheres (< 1 km) indicate tiny objects unlikely to retain satellites
- Primarily a scientific curiosity metric; not used in hazard assessment

---

## Calibration Slope (`compute_calibration_slope`)

**Module**: `calibration.py`

Measures the slope of the reliability diagram:

```
slope = Σ[(p̄_b - p̄)(f_b - f̄)] / Σ[(p̄_b - p̄)²]
```

where `p̄_b` is the mean predicted probability in bin `b` and `f_b` is the observed fraction of positives.

- `slope ≈ 1.0`: well-calibrated classifier
- `slope > 1.0`: underconfident (probabilities too compressed toward 0.5)
- `slope < 1.0`: overconfident (probabilities too extreme)
- Returns `1.0` if fewer than 2 non-empty bins

---

## Quality Gates for MPC Submission

Before submitting observations to the MPC, all of the following must pass:

| Gate | Threshold | Metric |
|------|-----------|--------|
| Real/bogus | ≥ 0.90 | `real_bogus_score` or `deep_real_bogus` |
| Orbit quality | ≥ 2 | `quality_code` in `OrbitalElements` |
| MOID | ≤ 0.05 AU | `moid_au` in `HazardAssessment` |
| Not known object | `known_object_score` < 0.5 | or no MPC match |
| Arc completeness | ≥ 0.5 | `compute_arc_completeness_score` |

See `docs/ALERT_PROTOCOL.md` for the full mandatory alert decision tree.

---

## Related Modules

- `preprocess.py`: image-level quality metrics
- `detect.py`: motion and photometry residuals
- `link.py`: tracklet geometry and consistency
- `orbit.py`: orbit quality codes and uncertainty propagation
- `score.py`: composite hazard and discovery scoring
- `calibration.py`: classifier probability calibration metrics
