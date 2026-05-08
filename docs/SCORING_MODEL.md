# Scoring Model

Bayesian log-score model for ranking NEO candidates produced by the pipeline.

---

## Hypotheses

The scoring model maintains a posterior over five mutually exclusive hypotheses for each candidate:

| Symbol | Hypothesis | Prior | Description |
|---|---|---|---|
| H_neo | `neo_candidate` | 0.05 | Genuine new NEO, not in MPC catalog |
| H_ko | `known_object` | 0.30 | Matches MPC catalog within astrometric tolerance |
| H_mba | `main_belt_asteroid` | 0.35 | Main-belt asteroid on ordinary orbit |
| H_art | `stellar_artifact` | 0.25 | Cosmic ray, satellite trail, or optical artifact |
| H_other | `other_solar_system` | 0.05 | Comet, TNO, or other unusual body |

Priors are deliberately pessimistic about new NEOs: the vast majority of moving transients detected by ZTF are known MBAs or artifacts. Priors may be adjusted for high-ecliptic-latitude fields where MBA contamination is lower.

---

## Log-Score Formulation

For each hypothesis H_i:

```
ℓ_i = log P(H_i) + Σ_k w_ik · φ_k(D)
```

where:
- `φ_k ∈ [0, 1]` are bounded feature scores
- `w_ik` are signed feature weights (positive = evidence for H_i)
- Missing features contribute 0 (neutral, no evidence for or against)

Posterior probabilities via softmax:

```
p_i = exp(ℓ_i − ℓ_max) / Σ_j exp(ℓ_j − ℓ_max)
```

---

## Feature Weights for `neo_candidate`

```
log_score_neo =
    log(0.05)                        # prior
    + 2.0 × real_bogus_score         # high rb → genuine detection
    + 1.5 × arc_coverage_score       # longer arc → better constrained
    + 1.5 × nights_observed_score    # multi-night → not satellite/artifact
    + 1.2 × motion_consistency_score # linear motion → solar system body
    + 1.0 × orbit_quality_score      # quality code ≥ 2 → credible orbit
    − 2.5 × known_object_score       # MPC match → not new
    − 2.0 × stellar_artifact_score   # artifact evidence → penalize
    − 1.5 × main_belt_consistency    # MBA-like orbit → penalize
```

---

## Feature Definitions

### Detection Quality

| Feature | Range | Description |
|---|---|---|
| `real_bogus_score` | [0, 1] | Mean rb/drb score from ZTF; 1 = real source |
| `streak_score` | [0, 1] | Image elongation; 1 = clear streak (fast NEO) |
| `psf_quality_score` | [0, 1] | Peak SNR proxy; 1 = high-quality detection |

### Motion

| Feature | Range | Description |
|---|---|---|
| `motion_consistency_score` | [0, 1] | Linearity of sky motion; 1 = perfect linear track |
| `arc_coverage_score` | [0, 1] | Arc length / 30 days, clamped to [0, 1] |
| `nights_observed_score` | [0, 1] | Sigmoid of nights observed |

### Photometry

| Feature | Range | Description |
|---|---|---|
| `brightness_score` | [0, 1] | Proxy for size; 1 = bright (large, detectable) |
| `color_score` | [0, 1] | g−r index; near 0.5 = typical S/C asteroid |
| `lightcurve_variability_score` | [0, 1] | Magnitude std; 1 = high variability (rotating body) |

### Orbit (populated after orbit.py)

| Feature | Range | Description |
|---|---|---|
| `orbit_quality_score` | [0, 1] | Quality code / 4, normalized |
| `moid_score` | [0, 1] | 1 if MOID ≤ 0.05 AU (PHA regime) |
| `neo_class_confidence` | [0, 1] | Confidence of NEO classification |
| `pha_flag_confidence` | [0, 1] | Confidence of PHA flag |

### Catalog

| Feature | Range | Description |
|---|---|---|
| `known_object_score` | [0, 1] | 1 = confirmed MPC match; 0 = genuinely new |

---

## Hazard Assessment

After scoring, each candidate receives a `HazardAssessment`:

```python
hazard_flag: Literal["pha_candidate", "close_approach", "nominal", "unknown"]
moid_au: float | None
estimated_diameter_m: float | None
absolute_magnitude_h: float | None
neo_class: NEOClass
alert_pathway: AlertPathway
```

**PHA flag logic**:
- `pha_candidate`: MOID ≤ 0.05 AU **and** H ≤ 22 (D ≳ 140 m) and quality_code ≥ 2
- `close_approach`: MOID ≤ 0.05 AU but H > 22 (smaller body)
- `nominal`: NEO with MOID > 0.05 AU
- `unknown`: orbit not yet constrained (quality_code = 1 or MOID = None)

**Diameter estimate** from absolute magnitude H:
```
D = (1329 km / √p_v) × 10^(−H/5)
```
using geometric albedo p_v = 0.14 (S-type assumption; conservative).

---

## Discovery Priority Score

Composite score for follow-up prioritization:

```
discovery_priority = 0.5 × neo_candidate_prob
                   + 0.3 × orbit_quality_score
                   + 0.2 × (1 if pha_candidate else 0)
```

Ranges [0, 1]; higher = more urgent follow-up needed.

---

## Calibration

Final probabilities are calibrated via `calibration.py`:
- **Platt scaling**: logistic regression on validation set posteriors
- **Isotonic regression (PAVA)**: non-parametric; preferred for larger validation sets

Both calibrators are evaluated via Brier score and Expected Calibration Error (ECE) using `Skills/evaluate_calibration.py`.

---

## Guardrails

- The pipeline **never** outputs a confirmed NEO or an impact probability
- All scoring is advisory; human review is required before any alert action
- Unknown features contribute 0 to the log-score (conservative)
- PHA flag requires orbit quality code ≥ 2 (multi-night arc)
- Alert pathway `nasa_pdco_notify` additionally requires MPC submission and independent confirmation

---

## References

- Jedicke et al. (2002) — observational selection effects in asteroid surveys
- Duev et al. (2019) — ZTF real/bogus deep learning classifier
- Moeyens et al. (2021) — THOR tracklet linking algorithm
- Lin et al. (2022) — transformer for asteroid light-curve classification
