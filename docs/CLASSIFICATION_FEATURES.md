# Classification Features Reference

Technical reference for all tabular features used in the Tier-1 classifier
and their relationship to the `CandidateFeatures` schema.

---

## Overview

The Tier-1 classifier operates on 14 scalar features extracted from each
tracklet.  All features are `OptScore` values — `float | None`, bounded
`[0, 1]`.  A `None` value means the feature could not be computed (missing
data, insufficient arc, etc.).  Missing features contribute 0 to the
log-score model (neutral).

---

## Feature Definitions

### Detection Quality

| Feature | Schema Field | Description |
|---|---|---|
| Real/bogus score | `real_bogus_score` | Mean deep real/bogus score across observations; 1 = real source |
| Streak score | `streak_score` | Elongation index from image moments; 1 = strong streak |
| PSF quality | `psf_quality_score` | Peak-to-background SNR proxy; 1 = high-SNR point source |

**Computation**: `real_bogus_score` is the mean of `obs.deep_real_bogus` (preferred)
or `obs.real_bogus` across all tracklet observations.  ZTF threshold: `rb ≥ 0.65`
for initial detection; `rb ≥ 0.90` for MPC submission gate.

### Motion

| Feature | Schema Field | Description |
|---|---|---|
| Motion consistency | `motion_consistency_score` | Linear-fit RMS residual inverse; 1 = perfectly linear motion |
| Arc coverage | `arc_coverage_score` | `min(arc_days / 30, 1)`; longer arc → higher score |
| Nights observed | `nights_observed_score` | `min((n_nights − 1) / 6, 1)`; ≥7 nights → 1.0 |

**Note**: Motion consistency uses a 2D linear fit to (RA cos δ, Dec) vs JD.
30 arcsec RMS scatter gives score 0; < 1 arcsec gives score > 0.97.

### Photometry

| Feature | Schema Field | Description |
|---|---|---|
| Brightness score | `brightness_score` | `clip((25 − H) / 10, 0, 1)`; brighter → higher priority |
| Color score | `color_score` | Normalised g−r color index; typical NEO g−r ≈ 0.4–0.7 |
| Lightcurve variability | `lightcurve_variability_score` | Magnitude std dev normalised to 0.5 mag |

**Color score formula**: `clip((g−r + 0.5) / 2, 0, 1)`.
Requires observations in both g and r filters; returns `None` otherwise.

### Orbital (populated after orbit.py)

| Feature | Schema Field | Description |
|---|---|---|
| Orbit quality | `orbit_quality_score` | Quality code / 4; code 1 = short arc, code 4 = multi-opposition |
| MOID score | `moid_score` | 1 if MOID ≤ 0.05 AU; scaled otherwise |
| NEO class confidence | `neo_class_confidence` | Classifier confidence in the assigned NEO dynamical class |
| PHA flag confidence | `pha_flag_confidence` | Confidence in PHA assessment (requires MOID + H) |

**Orbit quality codes**:

| Code | Condition |
|---|---|
| 1 | Arc < 1 day |
| 2 | Multi-night (2+ nights) |
| 3 | Multi-week (1+ month) |
| 4 | Multi-opposition |

### Catalog

| Feature | Schema Field | Description |
|---|---|---|
| Known object score | `known_object_score` | 0 = no MPC match (new object); 1 = confirmed known match |

A known-object match within 5 arcsec of the MPC ephemeris gives
`known_object_score = 1.0`.  Large separation → lower score.

---

## Tier-1 Confidence

The `compute_tier1_confidence(features)` function returns the fraction of
the 14 feature fields that are not `None`.  Use this to assess data quality
before classification:

```python
from classify import compute_tier1_confidence, extract_features

features = extract_features(tracklet)
confidence = compute_tier1_confidence(features)
# 1.0 → all 14 features populated; 0.0 → no features
```

---

## Log-Score Model

The Tier-1 classifier uses a log-score model over 5 hypotheses:

```
ℓ_neo = log(0.05)
      + 2.0 × real_bogus_score
      + 1.5 × arc_coverage_score
      + 1.5 × nights_observed_score
      + 1.2 × motion_consistency_score
      + 1.0 × orbit_quality_score
      − 2.5 × known_object_score
      − 2.0 × stellar_artifact_score
      − 1.5 × main_belt_consistency_score
```

Posterior probabilities are computed via softmax over all 5 log-scores.
Missing features (None) contribute 0 — no penalty, no bonus.

### Priors

| Hypothesis | Prior |
|---|---|
| neo_candidate | 0.05 |
| known_object | 0.30 |
| main_belt_asteroid | 0.35 |
| stellar_artifact | 0.25 |
| other_solar_system | 0.05 |

Priors are deliberately pessimistic about new NEOs.  For high-ecliptic-
latitude fields (|b| > 30°), MBA contamination is lower and the prior
may be relaxed.

---

## Feature Extraction

```python
from classify import extract_features
from link import link

link_result = link(raw_candidates)
for tracklet in link_result.tracklets:
    features = extract_features(tracklet)
    print(features.real_bogus_score, features.arc_coverage_score)
```

Features requiring orbital elements (`orbit_quality_score`, `moid_score`,
`neo_class_confidence`, `pha_flag_confidence`, `known_object_score`) are
populated by `score.py` after `orbit.py` runs.

---

## Tier-2 CNN Features

The Tier-2 CNN does not use `CandidateFeatures` directly.  It operates on
63×63 pixel image triplets (science / reference / difference) normalized to
[0, 1].  The CNN output is a calibrated real/bogus probability that updates
`real_bogus_score` before the ensemble stacker runs.

---

## Tier-3 Transformer Features

The Tier-3 Transformer tokenizes each observation as a 5-tuple:

```
(RA_deg, Dec_deg, magnitude, JD, filter_band_index)
```

Positional encoding is based on observation time (JD).  The transformer
produces a 5-class posterior directly comparable to `NEOPosterior`.

---

## Ensemble

The final posterior is produced by a logistic regression meta-learner
stacking Tier-1, Tier-2, and Tier-3 outputs.  Calibrate with
`calibration.py` (Platt or isotonic) on held-out labeled data.

---

## References

- Duev et al. (2019): ZTF real/bogus CNN architecture
- Lin et al. (2022): Transformer for asteroid light-curve classification
- CLAUDE.md §Scoring Model: full feature weight table
