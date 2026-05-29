# Pipeline Internals Reference

Technical reference for v0.63.0 internal helper APIs added across detection,
preprocessing, linking, classification, orbit fitting, scoring, alerting, and
calibration modules.

---

## Detection: compute_detection_significance

**Module**: `detect.py`

Computes a `[0, 1]` detection significance score using:

```
score = clip((limiting_mag - mag) / 5.0, 0, 1)
```

Returns `None` if either magnitude is absent or a sentinel value (≥ 90).

---

## Preprocessing: compute_elongation_angle

**Module**: `preprocess.py`

Computes the orientation angle of an elongated source from 63×63
difference-image second moments. Returns the major-axis angle in degrees
`[0, 180)` using `0.5 * arctan2(2*mxy, mxx - myy)`. Returns `None` for
circular sources (degenerate moments), missing cutouts, or decode failures.

---

## Linking: compute_arc_curvature

**Module**: `link.py`

Computes the RMS of linear-fit residuals in arcsec across a tracklet arc.
A value near zero indicates straight-line (inertial) apparent motion; a
larger value indicates curvature consistent with parallax or non-linear
motion. Returns `0.0` for fewer than 3 observations.

---

## Classification: compute_main_belt_probability

**Module**: `classify.py`

Log-score probability for the main-belt asteroid hypothesis using the
prior of 0.35 (from CLAUDE.md). Features rewarding MBA evidence include
`main_belt_consistency_score` and `known_object_score`; NEO-like motion
(`motion_consistency_score`, `arc_coverage_score`) suppresses the score.
Result is normalised against the `neo_candidate` hypothesis and clamped to
`[0, 1]`.

---

## Orbit: compute_heliocentric_velocity

**Module**: `orbit.py`

Computes the heliocentric speed at perihelion in km/s using the vis-viva
equation evaluated at `r = q`:

```
v = sqrt(GM_sun * (2/q - 1/a))
```

where `GM_sun = 4π² AU³/yr²` and `1 AU/yr ≈ 4.74047 km/s`. Returns `None`
for non-positive perihelion distance, zero semi-major axis, or non-physical
(negative) values under the radical.

---

## Scoring: compute_astrometric_priority

**Module**: `score.py`

Computes the astrometric follow-up priority for a NEO candidate:

```
score = 0.4 × (1 − arc_coverage_score)
      + 0.3 × brightness_score
      + 0.3 × orbit_quality_score
```

Missing feature scores contribute 0.5 (neutral). Result is clamped to
`[0, 1]`. High values indicate objects where additional astrometry would
be most valuable.

---

## Alerting: compute_alert_priority_score

**Module**: `alert.py`

Composite alert priority score combining discovery priority, novelty, and
orbit quality:

```
score = 0.4 × discovery_priority
      + 0.3 × (1 − known_object_score)
      + 0.3 × orbit_quality_score
```

Missing values contribute 0.5 (neutral). Result is clamped to `[0, 1]`.

**Guardrail**: This score does NOT assert any impact probability and must
NOT be used to trigger the NASA/MPC alert pathway autonomously.

---

## Calibration: compute_calibration_summary

**Module**: `calibration.py`

Returns a comprehensive calibration summary dict in a single call:

```python
{
    "brier_score": float,
    "ece": float,
    "log_loss": float,
    "roc_auc": float,
    "overconfidence": float,
    "n_samples": int,
}
```

Returns sentinel values (`0.0` for error scores, `0.5` for `roc_auc`,
`0` for `n_samples`) for empty inputs.

---

## Skills

| Script | Purpose |
|---|---|
| `Skills/compute_arc_curvatures.py` | Batch arc curvature from tracklet JSON |
| `Skills/compute_detection_significance.py` | Batch detection significance from observation JSON |
