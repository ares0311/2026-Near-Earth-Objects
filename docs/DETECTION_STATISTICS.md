# Detection Statistics Reference

Technical reference for motion-detection statistics computed in `detect.py`, including angular velocity, sky background estimation, PSF metrics, source extent, and observation depth.

---

## Overview

The detection stage transforms preprocessed source catalogs into candidate moving objects. Statistical summaries help operators assess field quality, filter artifacts, and validate detector performance before downstream linking.

---

## Angular Velocity

**Function**: `compute_angular_velocity(obs1, obs2) -> dict | None`

Computes the apparent angular velocity (rate and position angle) between two observations.

### Formula

```
cos_dec = cos(mean_dec)
dRA_arcsec = (RA2 - RA1) * 3600 * cos_dec
dDec_arcsec = (Dec2 - Dec1) * 3600
rate = sqrt(dRA² + dDec²) / |dt_hours|
PA = atan2(dRA, dDec) mod 360°
```

### Output fields

| Field | Unit | Description |
|---|---|---|
| `rate_arcsec_hr` | arcsec/hr | Total sky-plane angular speed |
| `pa_deg` | degrees | Position angle (N through E) |
| `dt_hours` | hours | Time baseline between observations |

Returns `None` when both observations share the same JD (zero time baseline).

### Typical ranges

| Object type | Rate (arcsec/hr) |
|---|---|
| Distant NEO (> 1 AU) | 0.1 – 5 |
| Near-Earth approach | 5 – 60 |
| Fast-moving impactor | > 60 |
| MBA | 0.01 – 1 |

---

## Sky Background Estimation

**Function**: `estimate_sky_background(observations, percentile=50) -> float | None`

Estimates the per-field sky background level from difference-image cutouts.

### Method

Extracts the requested percentile of all pixel values across the 63×63 difference-image cutout arrays from the supplied observation list. Returns `None` when no valid cutouts are available.

### Interpretation

- **Low background** (near zero): clean sky with good image subtraction.
- **High background** (> 3σ of the photon noise floor): residual scattered light, poor subtraction, or cosmic-ray contamination.

---

## Source Extent

**Function**: `compute_source_extent(obs) -> float | None`

Estimates the source semi-major axis in arcsec from the 2D intensity-weighted covariance of the difference-image cutout.

### Method

1. Compute the intensity-weighted centroid of the 63×63 cutout.
2. Build the 2×2 second-moment matrix.
3. Return the square root of the largest eigenvalue, scaled to arcsec (1 pixel = 1 arcsec assumed).

Returns `None` for degenerate inputs (zero total flux or near-singular matrix).

### Interpretation

| Value | Morphology |
|---|---|
| < 1.5 arcsec | Point source (unresolved) |
| 1.5 – 5 arcsec | Marginally resolved or trailed |
| > 5 arcsec | Extended / heavily trailed |

---

## PSF FWHM

**Function**: `compute_psf_fwhm(obs) -> float | None`

Estimates the PSF full width at half maximum in arcsec from a 2D Gaussian moment fit to the difference-image cutout.

### Method

Uses intensity-weighted second moments:

```
sigma² = (Σ I*(r - r̄)²) / Σ I
FWHM = 2 * sqrt(2 * ln(2)) * sigma ≈ 2.355 * sigma
```

Returns `None` when no cutout is present or the total flux is zero.

### Typical values

| Condition | FWHM |
|---|---|
| Excellent seeing | < 1.5 arcsec |
| Median seeing | 1.5 – 2.5 arcsec |
| Poor seeing | > 2.5 arcsec |

---

## Streak Metric

**Function**: `compute_streak_metric(obs) -> float`

Returns a streak severity score in [0, 1] from the elongation of the second-moment ellipse.

### Formula

```
elongation = (lambda_max - lambda_min) / (lambda_max + lambda_min)
```

where `lambda_max` and `lambda_min` are the eigenvalues of the 2D second-moment matrix. A perfectly circular source gives 0; a fully elongated trail gives 1.

### Thresholds

| Score | Interpretation |
|---|---|
| 0.0 – 0.3 | Point source |
| 0.3 – 0.6 | Marginally trailed |
| > 0.6 | Definite streak / trail |

---

## Trail Length

**Function**: `compute_trail_length(obs) -> float | None`

Returns the trail length in arcsec from the larger second-moment axis. Useful for estimating apparent velocity when the exposure time is known.

---

## Observation Depth Estimation

**Function**: `estimate_observation_depth(observations, percentile=95) -> float | None`

Estimates the field limiting magnitude from the bright-end percentile of valid observation magnitudes.

### Method

Selects magnitudes where `mag < 90` (excluding the sentinel value used for non-detections), then returns the requested percentile. The 95th percentile approximates the faint-end detection limit.

Returns `None` when fewer than 2 valid magnitudes are available.

### Typical limits

| Survey | Limiting mag (30 s) |
|---|---|
| ZTF (r-band) | ~20.5 |
| ATLAS (o-band) | ~19.5 |
| Pan-STARRS (r-band) | ~22.0 |

---

## Detection Efficiency

**Function**: `compute_detection_efficiency(observations, limiting_mag) -> float`

Returns the fraction of observations brighter than `limiting_mag`. Observations with `mag ≥ 90` (sentinels) count as missed.

---

## Detection Counts by Filter

**Function**: `count_detections_by_filter(observations) -> dict[str, int]`

Returns a dict mapping filter band (e.g., `"g"`, `"r"`, `"i"`, `"o"`, `"c"`) to observation count. Observations with `filter_band=None` are counted under `"unknown"`.

---

## Image Quality Metrics

**Function**: `compute_image_quality_metrics(observations) -> dict`

Aggregates per-observation PSF and background statistics across a set of observations.

### Output fields

| Key | Description |
|---|---|
| `n_sources` | Number of observations |
| `mean_fwhm_arcsec` | Mean PSF FWHM across observations |
| `median_fwhm_arcsec` | Median PSF FWHM |
| `mean_snr` | Mean difference-image SNR |
| `background_rms` | RMS of per-observation background estimates |

---

## Image Gradient

**Function**: `compute_image_gradient(obs) -> float | None`

Computes the RMS Sobel gradient magnitude of the difference-image cutout. High gradient values indicate sharp edges from real sources or cosmic rays; low values indicate smooth noise.

### Method

Applies 3×3 Sobel kernels (horizontal and vertical) via `scipy.signal.convolve2d` and returns:

```
gradient_rms = sqrt(mean(gx² + gy²))
```

Returns `None` when no cutout is available or the cutout cannot be decoded.

---

## Usage Example

```python
from detect import (
    compute_angular_velocity,
    estimate_sky_background,
    compute_source_extent,
    compute_psf_fwhm,
    compute_streak_metric,
    estimate_observation_depth,
    compute_detection_efficiency,
    count_detections_by_filter,
)

# Angular velocity between two observations
vel = compute_angular_velocity(obs1, obs2)
# {'rate_arcsec_hr': 12.3, 'pa_deg': 45.0, 'dt_hours': 1.0}

# Sky background from a list of observations
bg = estimate_sky_background(observations, percentile=50)

# Observation depth
depth = estimate_observation_depth(observations)

# Detection efficiency
eff = compute_detection_efficiency(observations, limiting_mag=20.5)

# Filter breakdown
counts = count_detections_by_filter(observations)
# {'r': 42, 'g': 31, 'unknown': 2}
```

---

## Related Modules

- `preprocess.py` → `compute_image_gradient`, `compute_cutout_entropy`, `compute_difference_image_snr`
- `link.py` → `compute_tracklet_velocity_dispersion`, `compute_great_circle_residual`
- `orbit.py` → `compute_motion_vector`, `compute_apparent_magnitude`
- `docs/LINKING_GUIDE.md` → tracklet formation and arc statistics
- `docs/PREPROCESS_GUIDE.md` → difference image quality and photometry
