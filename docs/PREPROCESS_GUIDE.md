# PREPROCESS_GUIDE.md — Preprocessing Stage Reference

Technical reference for `preprocess.py`: difference image handling, source extraction, photometric and astrometric calibration, quality metrics, and batch preprocessing.

---

## Overview

The preprocess stage converts raw alert observations into a validated, calibrated source catalog ready for detection and linking.

```
FetchResult → preprocess() → PreprocessResult(sources, provenance)
```

Key responsibilities:
- Reject observations with invalid coordinates or out-of-range magnitudes
- Normalize image cutouts to [0, 1] for CNN input
- Optionally apply Gaia DR3 astrometric correction
- Compute photometric and PSF quality metrics

---

## Entry Points

### Single-batch preprocessing

```python
from preprocess import preprocess
result = preprocess(observations, apply_astrometry=True)
```

**Inputs**: `tuple[Observation, ...]` from the fetch stage  
**Output**: `PreprocessResult(sources, provenance: PreprocessProvenance)`

Quality cuts applied:
- RA in [0, 360], Dec in [−90, 90]
- Magnitude in (0, 35]
- No NaN coordinates or JD

### Batch preprocessing

```python
from preprocess import preprocess_batch
results = preprocess_batch([fetch_result1, fetch_result2])
```

Accepts a list of `FetchResult` objects and returns a list of `PreprocessResult` objects in the same order.

---

## Image Cutout Normalization

ZTF alerts include three 63×63 pixel cutouts in base64-encoded float32 format:
- `cutout_science`: science image
- `cutout_reference`: reference template
- `cutout_difference`: difference image (most important for detection)

All three are normalized to [0, 1] using the 1st–99th percentile range:

```python
lo, hi = np.percentile(arr, 1), np.percentile(arr, 99)
normed = np.clip((arr - lo) / (hi - lo), 0, 1)
```

---

## Astrometric Correction

When `apply_astrometry=True` (the default), a Gaia DR3 cone search is performed near each observation to compute an astrometric offset.  The correction is a simple median RA/Dec shift from cross-matched reference stars.

```python
from preprocess import preprocess
result = preprocess(observations, apply_astrometry=False)  # disable for speed
```

---

## Photometric Functions

### Zero-point estimation

```python
from preprocess import estimate_zero_point
zp = estimate_zero_point(observations, catalog_mags)
# Returns median(obs.mag - catalog_mag); None if <2 valid pairs
```

Sentinel magnitudes ≥ 90 are excluded.  At least 2 valid pairs are required.

### Photometric normalization

```python
from preprocess import normalize_photometry
corrected = normalize_photometry(observations, zero_point=0.3, reference_zero_point=0.0)
```

Applies `mag_corrected = mag - zero_point + reference_zero_point`.  Drops any observation whose corrected magnitude falls outside [0, 35].

### Photometric scatter

```python
from preprocess import compute_photometric_scatter
rms = compute_photometric_scatter(observations)  # RMS mag scatter; None for <2 valid obs
```

### Color index

```python
from preprocess import compute_color_index
g_r = compute_color_index(obs_g, obs_r)  # None if bands are identical
```

---

## PSF and Image Quality

### PSF FWHM

Available from `detect.py`:
```python
from detect import compute_psf_fwhm
fwhm = compute_psf_fwhm(obs)  # arcsec; None if no cutout or degenerate
```

### Source SNR (science cutout)

```python
from preprocess import compute_source_snr
snr = compute_source_snr(obs)  # peak / background-RMS from science cutout
```

### Difference-image SNR

```python
from preprocess import compute_difference_image_snr
snr = compute_difference_image_snr(obs)
# Peak-to-background SNR from the 63×63 difference cutout
# Background estimated from outer annulus (pixels outside central 15×15 box)
# Returns None if no cutout or degenerate background
```

### Image quality metrics (field-level)

```python
from preprocess import compute_image_quality_metrics
metrics = compute_image_quality_metrics(observations)
# Returns: n_sources, mean_fwhm_arcsec, median_fwhm_arcsec, mean_snr, background_rms
```

### Field quality summary

```python
from preprocess import quality_summary
summary = quality_summary(result)
# Returns: n_sources, mean_fwhm_arcsec, background_rms, mean_elongation
```

---

## Astrometric Quality

### Astrometric scatter

```python
from preprocess import compute_astrometric_scatter
rms_arcsec = compute_astrometric_scatter(observations)
# RMS of linear RA/Dec fit residuals in arcsec; None for <2 obs
```

### Source density

```python
from preprocess import estimate_source_density
density = estimate_source_density(observations, field_radius_deg=0.5)
# Sources per square degree
```

---

## Bad Pixel Detection

```python
from preprocess import detect_bad_pixels
bad = detect_bad_pixels(obs, sigma_threshold=5.0)
# Returns list of (row, col) tuples for pixels > sigma_threshold × MAD
```

---

## Saturation Flagging

```python
from preprocess import flag_saturated_sources
saturated_ids = flag_saturated_sources(result, saturation_mag=12.0)
# Returns list of obs_id strings for likely saturated sources
```

---

## Data Quality Notes

- ZTF difference cutouts are the primary input for CNN-based real/bogus scoring.
- ATLAS forced photometry does not include image cutouts; only photometric features are available.
- Magnitude sentinels ≥ 90 are non-detections (upper limits); they are excluded from scatter and zero-point calculations.
- Astrometric scatter > 1 arcsec per observation suggests a poor astrometric solution; flag for human review.
- PSF elongation > 3.0 suggests a streak or satellite trail; see `detect.py` for streak filtering.
