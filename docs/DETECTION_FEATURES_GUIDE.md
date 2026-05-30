# Detection Features Guide

Technical reference for all detection-stage features computed in `detect.py` and
used as inputs to the three-tier ML classifier.

---

## Overview

Detection features characterise the morphological, photometric, and kinematic
properties of each candidate source.  They are computed from difference-image
cutouts (ZTF 63×63 float32 arrays) and from the positional and brightness
time-series of each detection.

All features are expressed as `OptScore` values in [0, 1] or as raw physical
quantities that are later normalised before classification.

---

## Feature Reference

### Real/Bogus Score (`real_bogus_score`)

**Source**: ZTF alert field `rb` or `drb`; or Tier 1 XGBoost output.

**Range**: [0, 1] — 1 = genuine astrophysical source; 0 = artefact.

**Threshold**: Default cut at `rb ≥ 0.65` (configurable).  Candidates below
threshold are rejected before linking.

**Classifier use**: Primary Tier 1 feature with weight `+2.0` in the NEO
log-score model.  Tier 2 CNN re-derives an independent real/bogus probability
from the image triplet.

---

### Streak Metric (`streak_score`)

**Function**: `compute_streak_metric(obs)`

**Method**: Computes the ratio of the larger to smaller eigenvalue of the
second-moment matrix of the difference-image cutout.  Values near 1 indicate
a round PSF; values near 1 (after the minor/major inversion) indicate an
elongated trail.

**Range**: [0, 1] — 1 = maximally elongated (fast-moving trail).

**Classifier use**: Positive indicator for fast-moving NEOs and streak
candidates; filtered separately via `streak_candidates()`.

---

### Elongation Ratio (`elongation_ratio`)

**Function**: `compute_elongation_ratio(obs)`

**Method**: Ratio of second-moment eigenvalues (minor/major axis) from the
difference-image cutout, analogous to a PSF ellipticity measure.

**Range**: [0, 1] — values below 0.7 indicate significant elongation.

**Classifier use**: Complements `streak_score`; used in Tier 1 tabular
features to identify non-stellar morphologies.

---

### Source Compactness (`compactness`)

**Function**: `compute_source_compactness(obs)`

**Method**: Ratio of the peak pixel value to the total flux (sum of all pixels)
in the 63×63 difference-image cutout.

**Range**: [0, 1] — values near 1 indicate a point-like source concentrated in
a single pixel; lower values indicate extended or diffuse emission.

**Returns**: `None` if no cutout is present, decoding fails, or total flux ≤ 0.

**Classifier use**: Point-source NEO candidates are expected to have high
compactness; extended sources or artefacts tend to have lower values.

---

### FWHM Estimation (`fwhm_arcsec`)

**Function**: `compute_fwhm_from_cutout(obs)` (preprocess.py)

**Method**: Sums the 63×63 cutout along axis 0 to form a 1D marginal profile,
then fits a Gaussian model
`A * exp(-0.5 * ((x - mu) / sigma)^2) + B` using `scipy.optimize.curve_fit`.
FWHM = 2.355 × |sigma| × 1.01 arcsec/pixel (ZTF plate scale).

**Returns**: FWHM in arcsec (float), or `None` on fit failure.

**Classifier use**: Consistent FWHM near the expected PSF width confirms a
stellar-morphology detection; FWHM outliers indicate artefacts or extended
sources.

---

### PSF Quality Score (`psf_quality_score`)

**Function**: Derived from `compute_psf_fwhm(obs)` and image quality metrics.

**Method**: Compares measured FWHM against a reference PSF model for the
survey field.  High scores reflect detections well-matched to the expected PSF.

**Range**: [0, 1].

**Classifier use**: Used in Tier 1 as a sanity check that the detection
morphology is consistent with a point source at the survey resolution.

---

### Trail Length (`trail_length_arcsec`)

**Function**: `compute_trail_length(obs)`

**Method**: Computes the elongated extent of the source from second-moment
eigenvalues of the difference-image cutout, expressed in arcsec using the
ZTF plate scale.

**Returns**: Trail length in arcsec, or `None` on failure.

**Classifier use**: Trail length > 5 arcsec flags a fast-moving object whose
sky-plane velocity is high enough to trail in a 30 s ZTF exposure.

---

### Sky Background Estimation (`sky_background`)

**Function**: `estimate_sky_background(observations, percentile)`

**Method**: Takes the requested percentile (default 25th) of pixel values
across the difference-image cutouts of a set of observations.  Low percentile
values approximate the local sky background.

**Returns**: Background estimate (float) in raw pixel units, or `None` if no
valid cutouts are available.

**Classifier use**: Anomalously high background values indicate crowded fields
or residual host-galaxy light, which increases the false-positive rate for
faint detections.

---

## Feeding Into Classifier Tiers

| Feature | Tier 1 (XGBoost) | Tier 2 (CNN) | Tier 3 (Transformer) |
|---|---|---|---|
| `real_bogus_score` | ✓ (weight +2.0) | Derived from image triplet | — |
| `streak_score` | ✓ | Implicit in convolution | — |
| `elongation_ratio` | ✓ | Implicit in convolution | — |
| `compactness` | ✓ | Implicit in convolution | — |
| `fwhm_arcsec` | ✓ | Implicit in convolution | — |
| `psf_quality_score` | ✓ | — | — |
| `trail_length_arcsec` | ✓ | — | — |
| `sky_background` | ✓ (field-level) | — | — |

Tier 2 CNN receives the raw image triplet (science, reference, difference) and
implicitly learns morphological features including all of the above.  Tier 3
Transformer receives tokenised observation sequences and focuses on kinematic
and photometric time-series patterns rather than image morphology.

---

## Conservative Classification Policy

Per DECISION-005, any `None` feature value contributes a neutral score of 0.0
in the log-score model — it does not fail the candidate outright.  Unknown
objects default to `"candidate"` status, not `"confirmed NEO"`.  High-quality
PHA candidates require orbit quality code ≥ 2 before the PHA flag is set.
