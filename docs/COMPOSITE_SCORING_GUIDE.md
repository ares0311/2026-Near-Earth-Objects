# Composite Scoring Guide

This document covers composite, weighted, and sharpness scoring helpers
across `classify.py`, `score.py`, and `calibration.py` (v0.85.0).

---

## Composite NEO Score

### `compute_composite_neo_score(features)` — classify.py

Weighted combination of four detection-quality signals into a single [0, 1] score:

| Feature | Weight |
|---|---|
| `real_bogus_score` | 0.35 |
| `arc_coverage_score` | 0.25 |
| `nights_observed_score` | 0.25 |
| `orbit_quality_score` | 0.15 |

Missing (`None`) features contribute 0. Result clamped to [0, 1].

```python
from classify import compute_composite_neo_score
from types import SimpleNamespace

features = SimpleNamespace(
    real_bogus_score=0.9,
    arc_coverage_score=0.8,
    nights_observed_score=0.6,
    orbit_quality_score=0.5,
)
score = compute_composite_neo_score(features)
# 0.9*0.35 + 0.8*0.25 + 0.6*0.25 + 0.5*0.15 = 0.74
```

Use `Skills/compute_composite_neo_scores.py` for a CLI interface.

---

## Arc Coverage Fraction

### `compute_arc_coverage_fraction(tracklet, survey_window_days)` — link.py

Fraction of the survey window covered by the tracklet arc:

    arc_coverage_fraction = min(1.0, arc_days / survey_window_days)

Returns 0.0 if the survey window is non-positive or `arc_days` is None.

```python
from link import compute_arc_coverage_fraction
from types import SimpleNamespace

tracklet = SimpleNamespace(arc_days=5.0)
frac = compute_arc_coverage_fraction(tracklet, survey_window_days=10.0)
# 0.5
```

---

## Weighted Hazard Index

### `compute_weighted_hazard_index(neo)` — score.py

Composite hazard index combining threat score, MOID proximity, and orbit quality:

| Component | Weight | Description |
|---|---|---|
| `compute_threat_score(neo)` | 0.4 | Geometric mean of MOID, size, quality |
| MOID proximity | 0.3 | `1 - moid_au / 0.05`, clamped [0,1]; 0.5 sentinel if unknown |
| Orbit quality fraction | 0.3 | `quality_code / 4`, clamped [0,1] |

Higher values indicate greater hazard concern.

```python
from score import compute_weighted_hazard_index
idx = compute_weighted_hazard_index(scored_neo)
# e.g. 0.73 for a close PHA candidate with good orbit
```

---

## Sharpness

### `compute_sharpness(probs)` — calibration.py

Mean squared deviation of predicted probabilities from 0.5:

    sharpness = mean((p - 0.5)² for p in probs)

- Result in [0, 0.25]
- A perfectly sharp model (all 0 or 1) scores 0.25
- Random guessing at 0.5 scores 0.0
- Sharpness measures decisiveness regardless of calibration accuracy

```python
from calibration import compute_sharpness
s = compute_sharpness([0.1, 0.9, 0.05, 0.95])
# high sharpness → confident predictions
```

---

## Specific Angular Momentum

### `compute_specific_angular_momentum(elements)` — orbit.py

Specific angular momentum h = sqrt(GM · a · (1 - e²)) in AU² yr⁻¹:

```python
from orbit import compute_specific_angular_momentum
from types import SimpleNamespace

elements = SimpleNamespace(a_au=1.5, e=0.3)
h = compute_specific_angular_momentum(elements)
# ~6.09 AU² yr⁻¹
```

Returns `None` for non-positive `a` or `e ≥ 1`.

---

## Guardrails

All composite scores are pipeline-internal diagnostics.
They do NOT constitute confirmed NEO detections or hazard assessments.
Follow the alert protocol in `docs/ALERT_PROTOCOL.md` for external reporting.
