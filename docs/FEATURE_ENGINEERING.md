# Feature Engineering Reference

This document describes the feature computation helpers used by the NEO Detection Pipeline for detection, linking, classification, and scoring.

---

## Overview

Features are computed at multiple pipeline stages and collected into `CandidateFeatures`. All feature scores are bounded `[0, 1]` (`OptScore = float | None`). Missing features contribute `0.0` (neutral) to log-score models.

```
detect.py   → image/photometry features
link.py     → motion/arc features
classify.py → classification features
orbit.py    → orbital features
score.py    → composite scoring
```

---

## Detection Features

### Elongation Ratio (`compute_elongation_ratio`)

**Module**: `detect.py`

Axis ratio b/a from 2D image second moments:

```
mxx = Σ[(x - cx)² · I(x,y)] / Σ[I(x,y)]
myy = Σ[(y - cy)² · I(x,y)] / Σ[I(x,y)]
mxy = Σ[(x - cx)(y - cy) · I(x,y)] / Σ[I(x,y)]

eigenvalues λ₁ ≥ λ₂ from 2×2 moment matrix
ratio = λ₂ / λ₁
```

- `1.0` = circular PSF
- `< 1.0` = elongated / streak
- `None` if no cutout, zero flux, or degenerate moments

### Magnitude Residual (`compute_magnitude_residual`)

**Module**: `detect.py`

Signed difference between observed and predicted magnitude:

```
residual = obs_mag - predicted_mag
```

Returns `0.0` for sentinel magnitudes (≥ 90).

### Real/Bogus Histogram (`compute_real_bogus_histogram`)

**Module**: `classify.py`

Histogram of real/bogus scores across a tracklet's observations. Prefers `deep_real_bogus` over `real_bogus`.

---

## Linking Features

### Great-Circle Arc (`compute_great_circle_arc`)

**Module**: `link.py`

Total great-circle arc length in arcseconds:

```
arc = Σ arccos(sin δ₁ sin δ₂ + cos δ₁ cos δ₂ cos(α₂ - α₁)) × 3600
```

summed over consecutive observation pairs sorted by JD.

- Returns `0.0` for < 2 observations
- Complements `arc_days` (time-based) with a geometric measure

### Motion Scatter (`compute_tracklet_motion_scatter`)

**Module**: `link.py`

Standard deviation of pairwise apparent motion rates (arcsec/hr). Low scatter = consistent linear motion expected of a solar system object.

### Arc Completeness Score (`compute_arc_completeness_score`)

**Module**: `score.py`

Composite metric:

```
arc_completeness = 0.4 × arc_coverage_score
                 + 0.3 × nights_observed_score
                 + 0.3 × orbit_quality_score
```

| Score | Interpretation |
|-------|---------------|
| ≥ 0.8 | Excellent — suitable for MPC submission |
| 0.5–0.8 | Good — follow-up recommended |
| < 0.5 | Poor — orbit highly uncertain |

---

## Classification Features

### NEO Class Prior (`compute_neo_class_prior`)

**Module**: `classify.py`

Fractional prior for a NEO dynamical class based on survey-completeness-corrected population estimates:

| Class | Prior |
|-------|-------|
| Apollo | 0.50 |
| Amor | 0.35 |
| Aten | 0.12 |
| IEO (Atira) | 0.03 |

Used to initialize the log-score model before applying feature weights.

### Posterior Entropy (`posterior_entropy`)

**Module**: `classify.py`

Shannon entropy of `NEOPosterior` in bits. High entropy = uncertain classification; low entropy = confident.

### Real/Bogus Score

Threshold: `rb ≥ 0.65` for detection; `rb ≥ 0.90` required for MPC submission gate.

---

## Orbit-Derived Features

### Encounter Velocity (`compute_encounter_velocity`)

**Module**: `orbit.py`

Approximate Earth-encounter velocity in km/s via vis-viva equation at 1 AU:

```
v²_obj  = GM☉ × (2/r − 1/a)    [evaluated at r = 1 AU]
v²_enc  = max(0, v²_obj − v²_earth)
v_enc   = √v²_enc × (4.74047 km/s per AU/yr)
```

- Returns `None` for non-Earth-crossing orbits (q > 1 AU or Q < 1 AU) and hyperbolic orbits
- Typical NEO encounter velocities: 10–40 km/s

| v_enc (km/s) | Approximate impactor energy |
|---|---|
| < 15 | Low energy |
| 15–25 | Moderate |
| > 25 | High energy |

### Hill Sphere Radius (`compute_hill_sphere_radius`)

**Module**: `orbit.py`

Gravitational sphere of influence in AU:

```
r_H = q × (m_asteroid / (3 × M_sun))^(1/3)
```

Mass estimated from H magnitude with p_v = 0.14, ρ = 2000 kg/m³.

### Arc Quality Code

**Module**: `orbit.py`

| Code | Arc length | Reliability |
|------|-----------|-------------|
| 1 | < 1 day | Poor |
| 2 | Multi-night | Moderate |
| 3 | Multi-week | Good |
| 4 | Opposition | Excellent |

Only codes ≥ 2 are used in the MPC submission gate.

---

## Scoring Features

### Follow-up Window Score (`compute_followup_window_score`)

**Module**: `score.py`

Urgency combining observation gap and orbit quality:

```
gap_score        = min(1.0, days_since_last_obs / 7.0)
orbit_gap_score  = max(0.0, 1.0 - orbit_quality_score)
window_score     = 0.5 × gap_score + 0.5 × orbit_gap_score
```

- `1.0` = urgent (stale arc, poor orbit)
- `0.0` = low urgency

### Threat Score (`compute_threat_score`)

**Module**: `score.py`

Geometric mean of MOID proximity, H-magnitude size proxy, and orbit quality. Used for rapid triage of high-priority candidates.

---

## Log-Score Model Weights

From CLAUDE.md — weights for the `neo_candidate` hypothesis:

```
log_score_neo =
    log(0.05)                          # prior
    + 2.0 × real_bogus_score
    + 1.5 × arc_coverage_score
    + 1.5 × nights_observed_score
    + 1.2 × motion_consistency_score
    + 1.0 × orbit_quality_score
    − 2.5 × known_object_score
    − 2.0 × stellar_artifact_score
    − 1.5 × main_belt_consistency_score
```

All features in [0, 1]; missing features contribute 0 (neutral).

---

## Calibration Features

### Overconfidence Score (`compute_overconfidence_score`)

**Module**: `calibration.py`

```
overconfidence = mean(predicted_probs) - mean(labels)
```

- Positive = overconfident (model predicts too high)
- Negative = underconfident
- `0.0` = perfectly calibrated on average

### Calibration Slope (`compute_calibration_slope`)

**Module**: `calibration.py`

Regression slope of the reliability diagram: `1.0` = perfect, `< 1.0` = overconfident, `> 1.0` = underconfident.

---

## Related Modules

- `detect.py` — image-level features
- `link.py` — motion and arc features
- `classify.py` — ML classification and posterior
- `orbit.py` — orbital mechanics
- `score.py` — composite hazard and priority scoring
- `calibration.py` — probability calibration metrics
- `docs/QUALITY_METRICS.md` — full pipeline quality metric reference
- `docs/SCORING_MODEL.md` — Bayesian scoring model details
