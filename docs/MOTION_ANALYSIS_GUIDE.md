# Motion Analysis Guide

Technical reference for sky-plane motion rate computation, velocity analysis, and brightness trend fitting in the NEO detection pipeline.

---

## Overview

Apparent angular motion is the primary observable that distinguishes solar system objects from background stars. The pipeline measures, filters, and uses motion in every stage from detect through link.

---

## Sky-Plane Velocity

### `compute_apparent_motion_rate(observations)` — `detect.py`

Returns the mean apparent motion rate in arcsec/hr across consecutive observation pairs in a list. Uses cosine-Dec-corrected RA differences for each pair. Returns `None` for fewer than 2 observations or when all pairs have identical JDs.

**Typical NEO rates** (arcsec/hr):

| Object class | Rate range |
|---|---|
| Main-belt asteroid | 0.01 – 2 |
| Near-Earth Object | 1 – 30 |
| Fast NEO (close approach) | 30 – 60+ |
| Low-Earth orbit satellite | > 60 (rejected by linker) |

### `compute_motion_vector(obs1, obs2)` — `detect.py`

Returns a dict with `dra_arcsec_hr`, `ddec_arcsec_hr`, `rate_arcsec_hr`, `pa_deg`. Cosine-Dec-corrected. Returns zero vector for identical JDs.

### `compute_sky_plane_velocity(obs1, obs2)` — `detect.py`

Returns a dict with velocity components and the great-circle separation rate in arcsec/hr.

---

## Motion Filtering

### `filter_alerts_by_motion(alerts, min_rate, max_rate)` — `fetch.py`

Filter observations by motion proxy (based on `ssdistnr` field). Observations without this field pass through.

### `filter_high_motion(tracklets, min_rate_arcsec_hr)` — `link.py`

Keep only tracklets whose `motion_rate_arcsec_per_hour` exceeds the threshold (default 10 arcsec/hr).

### `filter_by_motion_rate(tracklets, min_rate, max_rate)` — `link.py`

Filter tracklets to those with motion rate in `[min_rate, max_rate]` arcsec/hr.

---

## Position Angle and Consistency

### `compute_position_angle_consistency(tracklet)` — `link.py`

Measures how consistently the motion direction is maintained across observations. Returns a [0, 1] score; 1 = perfectly linear motion; 0 = random walk.

### `compute_arc_curvature(tracklet)` — `link.py`

Detects curvature in the sky-plane track due to parallax or actual orbital curvature. Useful for distinguishing NEOs from very distant objects.

### `compute_along_track_error(tracklet)` — `link.py`

RMS residual of observations along the dominant motion axis in arcsec. Low values confirm that the tracklet is consistent with a single moving object.

---

## Brightness Trends

### `compute_tracklet_brightness_trend(tracklet)` — `link.py`

Returns the linear slope of magnitude vs Julian Date in mag/day via `np.polyfit`. A positive slope means the object is fading; negative means brightening. Returns `None` for fewer than 2 valid (non-sentinel) magnitudes.

**Interpretation**:
- Fading (positive slope): object receding from Earth; post-opposition
- Brightening (negative slope): object approaching; pre-opposition
- Steep slopes (|slope| > 0.5 mag/day) may indicate rapid close approach

### `compute_brightness_trend(observations)` — `detect.py`

Similar fit on a raw observation list; returns slope in mag/day.

---

## Streak and Trail Detection

### `compute_streak_metric(obs)` — `detect.py`

Streak severity [0, 1] from difference-image second moments. High values indicate fast-moving objects that trail during a 30 s ZTF exposure. Objects with streak scores > 0.7 are flagged as potential high-velocity NEOs.

### `compute_trail_length(obs)` — `detect.py`

Trail length in arcsec from image second moments. For a 30 s ZTF exposure: trail_length ≈ rate × (30/3600) arcsec. Invert to estimate motion rate.

### `flag_moving_sources(observations, min_rate_arcsec_hr)` — `detect.py`

Returns observations with pairwise motion rate ≥ threshold. Uses `compute_motion_vector` pairwise with cosine-Dec correction.

---

## Motion Scatter and Residuals

### `compute_tracklet_motion_scatter(tracklet)` — `link.py`

Standard deviation of consecutive motion rates across the tracklet. Low scatter confirms consistent linear motion; high scatter may indicate mislinked detections.

### `compute_great_circle_residual(tracklet)` — `link.py`

RMS of great-circle fit residuals in arcsec for the full tracklet arc.

---

## Satellite Trail Rejection

The linker automatically rejects pairs moving at > 30 arcsec/hr in a nearly pure E-W or N-S direction (axis fraction > 0.98). These are characteristic of low-Earth-orbit satellites and debris. The flag is checked in `_is_satellite_trail()` within `link.py`.

---

## Guardrails

- Motion rate alone does not confirm a NEO — a full tracklet with multi-night arc is required.
- Streak-flagged sources should be followed up promptly; a 24-hr follow-up window is typical for fast NEOs.
- Satellite trail rejection is heuristic — very slow LEO objects near 30 arcsec/hr may pass through; use `compute_streak_metric` and `compute_trail_length` for additional discrimination.
- Brightness trends from arcs shorter than 3 hours are unreliable due to rotation-phase aliasing.
