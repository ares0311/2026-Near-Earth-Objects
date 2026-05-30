# ASTROMETRY_GUIDE — Astrometric Processing Reference

This document describes how astrometry is handled at each stage of the NEO detection pipeline,
from raw photometry through orbit fitting quality codes and candidate scoring.

---

## Gaia DR3 Cross-Matching

All astrometric calibration in the pipeline references **Gaia DR3**, which provides
sub-milliarcsecond positions for stars down to G ≈ 21.

- Access via `astroquery.gaia` (lazy-imported inside function bodies).
- Match ZTF/ATLAS sources to Gaia DR3 within a configurable radius (default 1 arcsec).
- Use matched star positions to compute a WCS correction (zero-point offsets in RA, Dec).
- Reject outliers using sigma clipping (3σ) before computing the correction.

Key function: `_apply_astrometric_correction` in `preprocess.py`.

---

## WCS Correction

The World Coordinate System (WCS) correction aligns pipeline source positions to the Gaia DR3
inertial reference frame.

**Steps:**

1. Extract source RA/Dec from the difference image (ZTF alert centroids or forced-photometry
   positions from ATLAS).
2. Cross-match with Gaia DR3 using a cone search.
3. Compute median offset in RA (corrected for cos Dec) and Dec separately.
4. Apply offset to all sources in the field.

The corrected positions feed directly into tracklet linking and orbit fitting.

---

## Astrometric Residual Computation

After linking, astrometric residuals measure how well each observation fits the fitted linear
(or quadratic) sky-plane motion model.

**Residual types:**

| Residual | Function | Description |
|---|---|---|
| Great-circle residual | `compute_great_circle_residual` | Angular separation between observed and predicted position |
| Linear-fit residual | `compute_astrometric_scatter` | RMS of RA/Dec residuals from a linear fit |
| Along-track error | `compute_along_track_error` | RMS projected along the motion position angle |

Residuals are reported in **arcseconds**.  Typical values for good tracklets are < 0.5 arcsec.

---

## FWHM Estimation from Cutouts

Point-spread function (PSF) width is estimated from the 63×63 float32 difference-image cutout
using a 1D Gaussian fit along the central row and column.

**Function:** `compute_fwhm_from_cutout` in `preprocess.py`.

**Steps:**
1. Decode the base64 cutout and reshape to (63, 63).
2. Extract the central row and central column as 1D profiles.
3. Fit a Gaussian to each profile using `scipy.optimize.curve_fit`.
4. FWHM = 2.355 × σ × pixel_scale (0.262 arcsec/pixel for ZTF).
5. Average the row and column FWHM estimates.

Returns `None` if the cutout is absent, the Gaussian fit diverges, or the cutout is degenerate.

---

## Astrometric Scatter Metrics

Two scatter metrics summarise position quality across a tracklet:

**`compute_astrometric_scatter(observations)`**
- Fits a linear model to RA(t) and Dec(t).
- Computes the RMS of the residuals in arcseconds.
- Returns `None` for fewer than 2 observations or zero time span.

**`compute_along_track_error(tracklet)`**
- Projects residuals onto the along-track direction (motion PA).
- Useful for distinguishing systematic bias (along-track) from noise (cross-track).
- Returns `0.0` for fewer than 3 observations.

---

## Astrometric Quality Flags

A tracklet's astrometric quality is encoded in the orbit quality code (1–4), which gates
external reporting and PHA flagging:

| Code | Meaning | Arc Length |
|---|---|---|
| 1 | Short-arc, low confidence | < 24 hours |
| 2 | Multi-night, reportable | ≥ 2 nights |
| 3 | Extended arc | ≥ 1 week |
| 4 | Opposition coverage | Multi-month |

Function: `arc_quality_report` in `orbit.py`.

Additional quality flags:
- `psf_quality_score` in `CandidateFeatures`: PSF elongation-based quality (0 = bad, 1 = stellar).
- `motion_consistency_score`: degree to which positions lie on a great-circle arc.

---

## Astrometry → Orbit Fitting Quality

Astrometric quality drives the orbit fitting pipeline in `orbit.py`:

1. **Gauss's method** (initial orbit) requires at least 3 well-separated positions with
   typical residuals ≤ 1 arcsec.
2. **Differential correction** (least-squares fit) iteratively reduces residuals.
   The fit converges when the RMS residual drops below 0.5 arcsec.
3. **Quality code** is assigned based on arc length (see table above).
4. **MOID** (Minimum Orbit Intersection Distance) is only reliable for quality code ≥ 2;
   short-arc MOIDs are flagged as unreliable.

Poor astrometric scatter (> 2 arcsec RMS) causes the differential correction to diverge.
The pipeline falls back to the Gauss solution and assigns quality code 1.

---

## Integration with Scoring

Astrometric quality propagates into the scoring model through:

- `orbit_quality_score` in `CandidateFeatures`: normalised quality code (1/4 … 4/4).
- `psf_quality_score`: PSF elongation penalty (reduces real/bogus score for trailed sources).
- PHA flagging requires `orbit_quality_score` corresponding to quality code ≥ 2.

The alert protocol gate also enforces `orbit_quality_code ≥ 2` before any MPC submission,
ensuring that poor astrometry cannot trigger false external alerts.
