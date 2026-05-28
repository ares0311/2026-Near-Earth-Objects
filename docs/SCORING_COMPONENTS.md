# Scoring Components Reference

Technical reference for the individual scoring components produced by `score.py`,
`calibration.py`, and supporting modules in v0.51.0.

---

## Overview

The NEO pipeline decomposes a candidate's overall hazard and detection quality
into a set of independently computable component scores.  Each component is
bounded to [0, 1] (or produces a physical quantity with defined units) and can
be combined, logged, or compared across pipeline runs.

---

## Detection Confidence (`compute_detection_confidence`)

**Location**: `score.py`

**Formula**:

```
confidence = 0.4 × real_bogus_score
           + 0.3 × orbit_quality_score
           + 0.3 × arc_coverage_score
```

**Range**: [0, 1]

**Interpretation**:

| Range      | Meaning                                          |
|------------|--------------------------------------------------|
| ≥ 0.8      | High confidence; candidate suitable for MPC report |
| 0.5 – 0.8  | Moderate; request additional observations         |
| < 0.5      | Low; internal candidate only                     |

Missing feature scores contribute **0.0** (conservative — uncertainty penalised).

---

## Priority Percentile (`compute_priority_percentile`)

**Location**: `score.py`

**Formula**:

```
percentile = count(neos where priority ≤ neo.priority) / total_neos
```

**Range**: [0, 1]

Returns the fraction of the candidate pool with equal or lower discovery
priority.  A value of 1.0 means this candidate has the highest priority.
Returns 0.0 for an empty pool.

---

## Perihelion Velocity (`compute_perihelion_velocity`)

**Location**: `orbit.py`

**Formula** (vis-viva at perihelion *r = q = a(1−e)*):

```
v_p = sqrt(GM_sun × (2/q − 1/a))    [AU/yr]
    × (1.496×10⁸ km/AU) / (365.25×86400 s/yr)
```

**Units**: km/s

**Typical values**:

| Object type | v_p (km/s) |
|-------------|------------|
| Apollo (e ≈ 0.5, a ≈ 1.5 AU) | ~35 |
| Aten (a ≈ 0.9 AU) | ~32 |
| Amor (q ≈ 1.1 AU) | ~28 |

Returns `None` for hyperbolic or degenerate orbits (*e* ≥ 1 or *a* ≤ 0).

---

## Tracklet Centroid (`compute_tracklet_centroid`)

**Location**: `link.py`

**Formula**:

```
(RA_centroid, Dec_centroid) = (mean(RA_i), mean(Dec_i))
```

Returns the arithmetic mean sky position as a `(ra_deg, dec_deg)` tuple.
Returns `None` if the tracklet has no observations.

**Note**: The arithmetic mean is appropriate for small fields (< a few degrees).
For wide-field clustering, a spherical centroid is preferable.

---

## Posterior KL Divergence (`compute_posterior_kl_divergence`)

**Location**: `classify.py`

**Formula**:

```
KL(p || q) = Σ_i p_i log(p_i / q_i)
```

Applied after additive smoothing (ε = 1e-10) and renormalisation over the five
NEOPosterior hypotheses.  Returns 0.0 for degenerate (all-zero) distributions.

**Interpretation**:

| KL value | Meaning |
|----------|---------|
| ≈ 0      | Distributions nearly identical |
| 0.1 – 0.5 | Moderate divergence; different dominant hypothesis likely |
| > 1      | Strong disagreement between calibration states |

Useful for measuring calibration gain and tracking posterior updates across
pipeline stages.

---

## Ensemble Agreement (`compute_ensemble_agreement`)

**Location**: `classify.py`

**Formula**:

```
agreement(p, q) = 1 − L1(p, q) / 2

mean_agreement = mean over all pairs (i, j), i < j
```

where L1 distance = Σ |p_k − q_k| over the five hypothesis keys.

**Range**: [0, 1]

Returns 0.0 for fewer than 2 posteriors.

---

## Brier Score Decomposition

The Brier score decomposes into three terms:

```
BS = Uncertainty − Resolution + Reliability
```

| Component | Function | Formula |
|-----------|----------|---------|
| Uncertainty | `compute_uncertainty_component` | o_bar × (1 − o_bar) |
| Resolution | `compute_resolution` | Σ (n_k/N)(o_k − o_bar)² |
| Reliability | via ECE | Σ (n_k/N)(p_k − o_k)² |

Where:
- *o_bar* = overall fraction of positive labels
- *o_k* = observed fraction in bin *k*
- *p_k* = mean predicted probability in bin *k*
- *n_k* = number of samples in bin *k*

A well-calibrated classifier maximises Resolution while minimising Reliability.
Uncertainty is a constant determined solely by the label distribution.

---

## MPC Submission Header (`format_mpc_submission_header`)

**Location**: `alert.py`

Generates the standard two-line COD/OBS header required at the top of every
MPC batch submission:

```
COD <obs_code>
OBS <observer_name>
```

- `obs_code`: 3-character MPC observatory code (upper-cased, truncated to 3 chars)
- `observer_name`: truncated to 60 characters

---

## Detection Confidence CLI

```bash
python Skills/compute_detection_confidence.py data/scored_neos.json
python Skills/compute_detection_confidence.py data/scored_neos.json --threshold 0.5
python Skills/compute_detection_confidence.py data/scored_neos.json --json
```

## Perihelion Velocity CLI

```bash
python Skills/compute_perihelion_velocities.py data/sample_tracklets.json
python Skills/compute_perihelion_velocities.py data/sample_tracklets.json --json
```

---

## Guardrail

This pipeline does **NOT** assert any probability of Earth impact.
All hazard scores are internal quality metrics.  Authoritative hazard assessment
must come from MPC/CNEOS.
