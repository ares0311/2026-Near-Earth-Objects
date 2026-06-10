# Quality Metrics Reference

This document describes every quantitative quality metric produced by the NEO detection
pipeline, its definition, range, and how to interpret it.

---

## 1. Detection Quality

### 1.1 Real/Bogus Score (`real_bogus_score`)

**Source**: Tier 1 XGBoost + Tier 2 CNN ensemble  
**Range**: [0, 1]  
**Interpretation**: Probability that a source detection is a genuine astrophysical signal
rather than an instrumental artifact, cosmic ray, satellite trail, or noise spike.

| Value | Meaning |
|---|---|
| ≥ 0.90 | Very high confidence genuine detection |
| 0.65–0.90 | Passes detection gate; monitor closely |
| < 0.65 | Rejected; not linked or scored |

**Pipeline gate**: `detect.py` applies `rb ≥ 0.65` (configurable via `PipelineConfig.real_bogus_threshold`).

---

### 1.2 Streak Score (`streak_score`)

**Source**: `compute_streak_metric(obs)` in `detect.py`  
**Range**: [0, 1]  
**Interpretation**: Severity of PSF elongation in the difference image.  
Value of 1.0 indicates a fully trailed source (fast-moving NEO or satellite).

Streak fraction across a tracklet: `batch_morphology(tracklet)["streak_fraction"]`.

---

### 1.3 PSF Quality Score (`psf_quality_score`)

**Source**: `preprocess.py` PSF fitting  
**Range**: [0, 1] (0 = poor, 1 = stellar PSF)  
**Interpretation**: Ratio of observed PSF FWHM to expected seeing FWHM.  
Values near 1.0 indicate clean, well-sampled point sources.

**Related function**: `compute_psf_fwhm(obs)` returns FWHM in arcseconds (ZTF pixel scale: 1.01 arcsec/px).

---

## 2. Astrometric Quality

### 2.1 Motion Consistency Score (`motion_consistency_score`)

**Source**: `link.py` linear fit residuals  
**Range**: [0, 1]  
**Interpretation**: How closely observed positions follow a uniform linear motion model.

Derived from `assess_link_confidence(tracklet)`:

```
conf = max(0, 1 - rms / 10.0)
```

where `rms` is the RMS residual of a linear RA/Dec fit in arcseconds.

---

### 2.2 Astrometric Scatter (`compute_astrometric_scatter`)

**Source**: `preprocess.py`  
**Units**: arcseconds  
**Interpretation**: RMS residual of a linear RA(t)/Dec(t) fit across all observations.
Values below 0.5 arcsec indicate GPS-quality astrometry relative to Gaia DR3.
Returns `None` if fewer than 2 observations or degenerate time coverage.

---

### 2.3 Arc Coverage Score (`arc_coverage_score`)

**Source**: Derived from tracklet arc length  
**Range**: [0, 1]  
**Interpretation**: Normalized arc duration.  
- 0 = single epoch  
- 1 = ≥ 30 days arc (multi-opposition candidate)

---

### 2.4 Nights Observed Score (`nights_observed_score`)

**Source**: Derived from unique Julian date nights  
**Range**: [0, 1]  
**Interpretation**: Fraction of ideal multi-night coverage achieved.  
- 0 = single night  
- 1 = ≥ 5 separate nights

---

## 3. Tracklet Grade

### 3.1 Grade (`compute_tracklet_grade`)

**Source**: `link.py`  
**Values**: A, B, C, D  
**Interpretation**: Combined quality assessment of arc length, nights observed, and astrometric RMS.

| Grade | Arc | Nights | RMS |
|---|---|---|---|
| A | ≥ 7 days | ≥ 3 | ≤ 0.5 arcsec |
| B | ≥ 2 days | ≥ 2 | ≤ 2.0 arcsec |
| C | ≥ 0.5 days | ≥ 2 | ≤ 5.0 arcsec |
| D | Below all thresholds | — | — |

Grade A tracklets support preliminary orbit determination. Grade D tracklets should be
re-observed before any external reporting.

**Batch grading**: `Skills/grade_tracklets.py`

---

## 4. Photometric Quality

### 4.1 Brightness Score (`brightness_score`)

**Range**: [0, 1]  
**Interpretation**: Proxy for object size.  
Derived from H magnitude: higher score = brighter (larger) object.

### 4.2 Color Score (`color_score`)

**Range**: [0, 1]  
**Interpretation**: Normalized g−r color index.  
Values near 0.5 correspond to C-type asteroid colors; values near 1.0 indicate reddish S-type.

---

## 5. Orbit Quality

### 5.1 Orbit Quality Code

**Source**: `orbit.py` → `arc_quality_report(tracklet)`  
**Values**: 1 (arc < 1 day), 2 (multi-night), 3 (multi-week), 4 (multi-opposition)  
**Interpretation**: Reliability of the fitted orbit.

| Code | Description | MOID reliability |
|---|---|---|
| 1 | Single-night arc | Unreliable — flag |
| 2 | Multi-night arc | Moderate |
| 3 | Multi-week arc | Good |
| 4 | Opposition-linked | Excellent |

**Alert protocol gate**: MOID ≤ 0.05 AU AND quality code ≥ 2 required before MPC submission.

### 5.2 MOID Score (`moid_score`)

**Source**: `orbit.py` MOID calculation  
**Range**: [0, 1]  
**Interpretation**: Probability-like proximity indicator.  
`moid_score = 1.0` if MOID ≤ 0.05 AU (PHA threshold).

### 5.3 Phase Angle (`compute_phase_angle`)

**Source**: `orbit.py`  
**Units**: degrees [0, 180]  
**Interpretation**: Sun–target–observer angle.  
Low phase angles (< 10°) occur near opposition; high phase angles (> 90°) can indicate
unusual orbits or quadrature geometry.  Returns NaN on degenerate geometry.

---

## 6. Classifier Calibration Metrics

### 6.1 Brier Score

**Formula**: `mean((p_i - y_i)²)`  
**Range**: [0, 1] (lower is better; 0 = perfect)  
**Source**: `calibration.py` → `evaluate_calibration`  
**Interpretation**: Mean squared error between predicted probabilities and binary outcomes.
A random classifier scores 0.25; a perfect classifier scores 0.

### 6.2 Expected Calibration Error (ECE)

**Formula**: Binned average `|mean(p) - mean(y)|` weighted by bin size  
**Range**: [0, 1] (lower is better)  
**Source**: `calibration.py` → `evaluate_calibration`  
**Interpretation**: Average mismatch between predicted probability and observed frequency.
Well-calibrated classifiers have ECE < 0.05.

### 6.3 Log-Loss

**Formula**: `-mean(y log(p) + (1-y) log(1-p))`  
**Source**: `calibration.py` → `compute_log_loss`  
**Range**: [0, ∞) (lower is better)  
**Interpretation**: Cross-entropy between predictions and labels. Penalizes confident wrong
predictions more harshly than Brier score. A classifier outputting 0.5 always scores ln(2) ≈ 0.693.

### 6.4 Cross-Validation (K-fold)

**Source**: `calibration.py` → `cross_validate_calibration(probs, labels, n_folds, metric)`  
**Returns**: `(mean_score, std_score)`  
**Interpretation**: Estimate of calibration generalization.  
A large std relative to mean indicates overfitting to the training split.

### 6.5 Bootstrap Confidence Interval

**Source**: `calibration.py` → `bootstrap_confidence_interval`  
**Returns**: `(lower_95_ci, upper_95_ci)` tuple  
**Interpretation**: 95% bootstrap confidence interval for the chosen metric.
Use to decide whether two calibrators are statistically different.

### 6.6 Production Calibration Promotion Gate

Production promotion is automatic and fail-closed; it does not require a human
calibration review. The evaluation set must contain at least 1,000 held-out real
labeled examples, including at least 200 positive and 200 negative examples.
Every KPI must pass:

| KPI | Production threshold |
|---|---|
| Brier score | < 0.10 |
| ECE, 10 equal-width bins | < 0.05 |
| Log loss | < 0.50 |
| ROC AUC | > 0.95 |
| Five-fold mean ECE | < 0.05 |
| Five-fold ECE standard deviation | ≤ 0.02 |
| Bootstrap 95% Brier upper bound | < 0.12 |
| Bootstrap 95% ECE upper bound | < 0.07 |

Missing metrics count as failures. A machine-readable report must record dataset
provenance, model hashes, calibrator method, metric values, thresholds, and
`promotion_gate_passed`. Reliability diagrams are retained for audit evidence
but do not determine approval.

---

## 7. Classification Quality

### 7.1 Posterior Entropy

**Formula**: `-sum(p_i log2(p_i))` over all hypotheses  
**Source**: `classify.py` → `posterior_entropy(posterior)`  
**Range**: [0, log2(5)] ≈ [0, 2.32] bits  
**Interpretation**: Uncertainty in the classification.  
- 0 bits = completely certain  
- 2.32 bits = uniform over all 5 hypotheses  

Flag candidates with entropy > 1.5 bits for human review.

### 7.2 NEO Novelty Score (`compute_novelty_score`)

**Source**: `score.py`  
**Range**: [0, 1]  
**Interpretation**: Orbital distance from nearest known NEO in the (a, e, i) space.
Score of 1.0 = completely novel orbit.  Score near 0 = very similar to a known object.

**Distance metric**:

```
d = sqrt((Δa / 3)² + (Δe)² + (Δi / 180)²)
```

---

## 8. Hazard Scoring

### 8.1 Discovery Priority

**Source**: `score.py` → `ScoringMetadata.discovery_priority`  
**Range**: [0, 1]  
**Interpretation**: Combined novelty, orbit quality, and PHA flag.  
High values drive follow-up scheduling (see `Skills/generate_obs_schedule.py`).

### 8.2 Followup Value

**Source**: `score.py` → `ScoringMetadata.followup_value`  
**Range**: [0, 1]  
**Interpretation**: Scientific return on follow-up observations.  
Weighs brightness (accessible from small telescopes), arc improvement, and orbit uncertainty reduction.

### 8.3 Scientific Interest

**Source**: `score.py` → `ScoringMetadata.scientific_interest`  
**Range**: [0, 1]  
**Interpretation**: Unusual orbital properties (extreme eccentricity, very small perihelion, high inclination, near-Earth resonances).

---

## 9. Impact Energy

### 9.1 `compute_impact_energy(diameter_m, velocity_km_s, density_kg_m3)`

**Source**: `score.py`  
**Units**: Megatons TNT  
**Formula**:

```
KE = 0.5 * m * v²  (Joules)
E_MT = KE / 4.184e15
```

where `m = density * (4/3) * π * (d/2)³`.

**Important**: This is an **order-of-magnitude estimate** for scientific context only.
Do NOT use as an impact probability or risk assessment.
All hazard determinations must defer to CNEOS Scout/Sentry.

---

## 10. Survey Coverage

### 10.1 `assess_survey_coverage` (Skills)

**Source**: `Skills/assess_survey_coverage.py`  
**Key outputs**: area_sq_deg, mean_limiting_mag, total_sources, fields_per_night  
**Interpretation**: Field-level metadata for completeness assessment.
Compare against nominal ZTF depth (r ≈ 20.5 mag) and NEO detection limits.

---

## References

- Duev et al. (2019) — Real-bogus classification deep learning
- Jedicke et al. (2002) — Observational selection effects in asteroid surveys
- Mainzer et al. (2014) — NEOWISE performance and detection statistics
- IAU Working Group on Near-Earth Objects — orbit quality code definitions
