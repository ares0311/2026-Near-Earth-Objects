# Photometry Guide

Technical reference for photometric processing in the NEO detection pipeline.

---

## Overview

Photometry in the pipeline operates on ZTF difference-image alerts and ATLAS forced-photometry outputs. Each observation carries an apparent magnitude, an uncertainty, and (for ZTF) a 63×63-pixel difference-image cutout used for flux and morphology extraction.

---

## Aperture Photometry

### `compute_source_flux(obs, aperture_radius_px=5.0)` — `detect.py`

Sums pixel values within a circular aperture centred on the brightest pixel of the difference-image cutout. The aperture radius is in pixels (ZTF plate scale ≈ 1.01 arcsec/px).

**When to use**: comparing relative brightnesses between candidates in the same field and epoch; not calibrated to an absolute flux scale.

**Returns**: `float | None` — `None` if no cutout is present or the cutout cannot be decoded.

---

## Gradient Magnitude

### `compute_gradient_magnitude(obs)` — `preprocess.py`

Computes the mean gradient magnitude over the difference-image cutout using NumPy's `np.gradient`. High values indicate sharp features (real point sources, cosmic rays); low values indicate diffuse or blank regions.

**Use case**: quick quality flag for difference-image artifacts. Combine with PSF FWHM and streak metric for artifact rejection.

---

## Magnitude Filtering

### `filter_by_magnitude(observations, min_mag, max_mag)` — `fetch.py`

Filters a list of observations to those with magnitude in `[min_mag, max_mag]`. Sentinel magnitudes (≥ 90) are always excluded regardless of the requested range.

---

## Zero-Point Calibration

### `estimate_zero_point(observations, catalog_mags)` — `preprocess.py`

Estimates a photometric zero-point offset as the median of `(observed_mag − catalog_mag)` pairs. Requires at least two valid pairs; excludes sentinel magnitudes (≥ 90).

### `normalize_photometry(observations, zero_point, reference_zero_point)` — `preprocess.py`

Applies a zero-point correction by shifting all magnitudes by `(reference_zero_point − zero_point)`. Observations with corrected magnitudes outside `[0, 35]` are dropped.

### `photometric_calibration.py` — `Skills/`

Per-field photometric zero-point fit against the Gaia DR3 catalog using a linear color term. Outputs a `PhotometricSolution` with zero-point, color coefficient, and RMS scatter.

---

## Color Index

### `compute_color_index(obs1, obs2)` — `preprocess.py`

Returns the magnitude difference between two observations in different filter bands (e.g., g − r). Both observations must be from the same source at comparable epochs. Returns `None` if either magnitude is a sentinel.

---

## Photometric Scatter

### `compute_photometric_scatter(observations)` — `preprocess.py`

Computes the RMS scatter of magnitudes across all valid observations for a source. Returns `None` for fewer than two valid observations. High scatter may indicate variability, contamination, or photometric errors.

---

## Survey Depth

### `estimate_survey_depth(fetch_result)` — `fetch.py`

Returns the 95th-percentile magnitude of all valid alerts in a `FetchResult` as a proxy for the limiting magnitude. Returns `None` if no valid magnitudes are found.

### `estimate_limiting_magnitude(fetch_result)` — `fetch.py`

Returns the median magnitude of the faintest 10% of sources as a conservative depth estimate.

---

## Brightness Score

The pipeline's `brightness_score` feature (in `CandidateFeatures`) is a proxy for estimated object size derived from apparent magnitude:

```
brightness_score = clip(1.0 - (mag - 15.0) / 10.0, 0.0, 1.0)
```

Bright objects (mag < 15) get a score near 1.0; objects fainter than mag 25 get 0.0.

---

## Absolute Magnitude

### `compute_absolute_magnitude(observed_mag, r_au, delta_au, phase_deg, g=0.15)` — `orbit.py`

Converts apparent magnitude to absolute magnitude H using the IAU HG phase function. Requires heliocentric distance `r_au`, geocentric distance `delta_au`, and phase angle `phase_deg`. Returns NaN for degenerate geometry.

---

## Apparent Magnitude Prediction

### `compute_apparent_magnitude(elements, target_jd, albedo=0.14)` — `orbit.py`

Predicts the V-band apparent magnitude at a future epoch from orbital elements and assumed geometric albedo. Uses the IAU HG phase function and the predicted ephemeris position.

---

## Guardrails

- Sentinel magnitudes (≥ 90) indicate missing or invalid photometry; always exclude these before analysis.
- Zero-point corrections should only be applied after at least two matched catalog stars; fewer matches produce unreliable offsets.
- Apparent magnitudes from short arcs (<24 hr) are less reliable due to unresolved light-curve rotation phase.
- Photometric outputs are **pipeline estimates** and must NOT be cited as authoritative measurements without cross-validation against a calibrated catalog.
