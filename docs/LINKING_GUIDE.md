# LINKING_GUIDE.md — Tracklet Formation and Quality Reference

Technical reference for `link.py`: how single-night detections become linked multi-night tracklets, the statistical tests applied, and the quality metrics used to grade and filter results.

---

## Overview

The link stage receives a list of `RawCandidate` objects from `detect.py` and attempts to connect observations that belong to the same moving solar-system body across multiple nights.  The output is a list of `Tracklet` objects, each containing ≥3 observations spanning ≥2 nights.

```
RawCandidate (single night) → link() → Tracklet (multi-night)
```

The algorithm is inspired by THOR (Moeyens et al. 2021) but implemented as a pure Python/NumPy solution without external orbit-determination dependencies.

---

## Linking Algorithm

### Step 1 — Pair formation

All pairs of detections from different nights within a configurable time window are tested for kinematic consistency:

- **Motion rate**: must satisfy `0.01 ≤ rate ≤ 60 arcsec/hr` (solar-system object window)
- **Position angle consistency**: pair PA must be within `±30°` of the initial pair PA
- **Position tolerance**: predicted position vs observed position must be within `position_tolerance_arcsec` (default `5.0`)

### Step 2 — Triplet extension

Pairs that pass the kinematic cut are extended to triplets and longer arcs using a χ² orbit-consistency test.  The predicted position at each additional epoch is computed by `_predict_from_arc`:

- **≥3 observations**: quadratic polynomial fit in RA and Dec vs time
- **2 observations**: linear extrapolation

The χ² residual uses the astrometric uncertainty proxy `max(mag_err, 0.5)` arcsec.  A candidate extension is accepted if χ²/dof ≤ `chi2_threshold` (default `5.0`).

### Step 3 — Satellite trail rejection

Pairs moving at ≥30 arcsec/hr purely in the E-W or N-S direction (within ±5°) are rejected as likely satellite or debris trails via `_is_satellite_trail`.

---

## Arc Quality

### Quality Code

The quality code (1–4) assigned by `arc_quality_report` governs downstream orbit reliability:

| Code | Description | MOID reliability |
|------|-------------|-----------------|
| 1 | Arc < 1 day | Poor |
| 2 | Multi-night (≥2 nights) | Marginal |
| 3 | Multi-week (≥7 days) | Good |
| 4 | Opposition coverage (≥30 days) | Excellent |

### Tracklet Grade

`compute_tracklet_grade` assigns an A/B/C/D grade:

| Grade | Arc (days) | Nights | Astrometric RMS |
|-------|-----------|--------|----------------|
| A | ≥7 | ≥3 | ≤1 arcsec |
| B | ≥1 | ≥2 | ≤3 arcsec |
| C | ≥0.5 | ≥2 | ≤5 arcsec |
| D | Otherwise | — | — |

---

## Arc Statistics

`compute_arc_statistics(tracklet)` returns a summary dict for a single tracklet:

| Key | Description |
|-----|-------------|
| `n_observations` | Total observation count |
| `n_nights` | Distinct integer-JD nights |
| `arc_days` | Total arc length in days |
| `mean_motion_arcsec_hr` | Mean apparent motion rate |
| `motion_pa_std_deg` | Std of position-angle across the arc |

`summarize_arc_statistics(tracklets)` aggregates over a list:

| Key | Description |
|-----|-------------|
| `n_tracklets` | Total count |
| `mean_arc_days` | Mean arc length |
| `max_arc_days` | Longest arc |
| `fraction_multi_night` | Fraction spanning >1 night |

---

## Filtering Functions

| Function | Description |
|----------|-------------|
| `filter_high_motion(tracklets, min_rate)` | Keep tracklets above a motion threshold |
| `filter_by_arc_length(tracklets, min_arc_days)` | Keep tracklets with arc ≥ threshold |
| `filter_by_nights_observed(tracklets, min_nights)` | Keep tracklets spanning ≥ min distinct nights |
| `deduplicate_tracklets(tracklets)` | Remove tracklets with ≥50% overlapping obs_ids |
| `split_tracklet(tracklet, split_jd)` | Split at a JD boundary into two sub-tracklets |

---

## Deduplication

`deduplicate_tracklets` removes redundant tracklets using a greedy longest-arc-first strategy:

1. Sort tracklets by `arc_days` descending
2. For each tracklet, compute Jaccard overlap with all already-kept tracklets
3. Discard if overlap ≥ 0.50; keep otherwise

This ensures the longest arc is preserved when the same physical object appears in multiple tracklets (e.g. from overlapping survey fields).

---

## Link Confidence

`assess_link_confidence(tracklet)` returns a [0, 1] confidence score based on the linear-fit RMS residual:

```
confidence = max(0, 1 - rms_arcsec / 10.0)
```

A reference scale of 10 arcsec represents a poor link; sub-arcsecond residuals give confidence ≈ 1.

---

## Motion Uncertainty

`estimate_motion_uncertainty(tracklet)` returns `(rate_err_arcsec_hr, pa_err_deg)` from the residuals of a linear fit to RA and Dec vs time.  Used to propagate ephemeris uncertainty for follow-up scheduling.

---

## Multi-Night Requirement

For MPC submission, the alert protocol requires ≥3 detections on ≥2 nights.  Use `filter_by_nights_observed(tracklets, min_nights=2)` as the final gate before orbit fitting.  Tracklets with a single night are only useful for intra-night candidate lists and should not be reported externally.

---

## Tuning

The linker has two primary knobs:

| Parameter | Default | Effect |
|-----------|---------|--------|
| `position_tolerance_arcsec` | 5.0 | Looser = more links, more false positives |
| `chi2_threshold` | 5.0 | Looser = more extensions, higher false-pair rate |

Use `Skills/tune_linker.py` to sweep these parameters against an injection-recovery test set and choose the point that maximises link rate while keeping false-pair fraction below your target (typically <5%).

---

## Reference

- Moeyens, J., et al. "THOR: An Algorithm for Cadence-independent Asteroid Discovery." *AJ*, 162, 143 (2021).
- Bernstein, G. & Khushalani, B. "Orbit Fitting and Uncertainties for Kuiper Belt Objects." *AJ*, 120, 3323 (2000).
