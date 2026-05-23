# Hazard Scoring Reference

Technical reference for the NEO hazard scoring subsystem: threat score, weighted hazard score, close-approach score, arc quality bonus, impact energy, size estimate, and Brier skill score calibration metric.

---

## Overview

The scoring stage (`score.py`) produces a layered hazard assessment for each `ScoredNEO` candidate. Several scalar scores are available at different levels of granularity:

| Score | Range | Description |
|---|---|---|
| `compute_threat_score` | [0, 1] | Geometric mean of MOID proximity, H-magnitude proxy, and orbit quality |
| `compute_close_approach_score` | [0, 1] | MOID proximity + 0.2 PHA bonus |
| `compute_arc_quality_bonus` | [0, 1] | Quality code × arc length modifier |
| `compute_weighted_hazard_score` | [0, 1] | 0.4×threat + 0.4×close_approach + 0.2×arc_quality |
| `compute_size_estimate` | (min_m, max_m) | Diameter range in metres from H magnitude |
| `compute_impact_energy` | megatons TNT | Kinetic impact energy from diameter and velocity |

---

## Threat Score

**Function**: `compute_threat_score(neo) -> float`

The threat score is the geometric mean of three components, each bounded [0, 1]:

```
threat = (moid_component * size_component * orbit_component)^(1/3)
```

| Component | Formula | Sentinel |
|---|---|---|
| MOID proximity | `max(0, 1 − moid_au / 0.05)` | 0.5 if unknown |
| Size proxy | `max(0, 1 − (H − 18) / 8)` if H ≤ 26 | 0.5 if unknown |
| Orbit quality | `quality_code / 4` | 0.25 if unknown |

A score of 1.0 would require MOID = 0 AU, H = 18 (diameter ~1 km), and quality_code = 4 (opposition-linked orbit). In practice, scores above 0.5 represent high-priority candidates.

---

## Close-Approach Score

**Function**: `compute_close_approach_score(neo) -> float`

Focuses specifically on MOID proximity and PHA status:

```
score = max(0, 1 − moid_au / 0.05) + 0.2 * is_pha
score = min(1.0, score)
```

Returns 0.5 when MOID is unknown. The 0.2 PHA bonus is applied when `hazard_flag == "pha_candidate"`.

---

## Arc Quality Bonus

**Function**: `compute_arc_quality_bonus(neo) -> float`

Rewards candidates with longer observational arcs and higher orbit quality codes:

```
quality_base = min(quality_code, 4) / 4
arc_modifier = log10(arc_days + 1) / log10(366)   [clamped to [0, 1]]
bonus = 0.6 * quality_base + 0.4 * arc_modifier
```

| Quality Code | Meaning |
|---|---|
| 1 | Arc < 1 day |
| 2 | Multi-night arc |
| 3 | Multi-week arc |
| 4 | Opposition-linked |

---

## Weighted Hazard Score

**Function**: `compute_weighted_hazard_score(neo) -> float`

Combines all three component scores:

```
weighted_hazard = 0.4 × threat + 0.4 × close_approach + 0.2 × arc_quality_bonus
```

This single scalar is the primary ranking metric for prioritising follow-up observations and alert processing. Candidates with `weighted_hazard_score ≥ 0.5` should be flagged for immediate review.

### Interpretation

| Score | Priority |
|---|---|
| ≥ 0.7 | **URGENT** — submit to MPC immediately |
| 0.5 – 0.7 | **HIGH** — schedule within 24 hours |
| 0.3 – 0.5 | **MEDIUM** — observe within 48 hours |
| < 0.3 | **ROUTINE** — standard queue |

---

## Size Estimate

**Function**: `compute_size_estimate(neo) -> tuple[float, float] | None`

Returns a `(min_m, max_m)` diameter range in metres from the absolute magnitude H, assuming geometric albedo in [0.05, 0.30]:

```
diameter_km = (1329 / sqrt(albedo)) * 10^(-H/5)
```

- Low albedo (0.05) → larger diameter (upper bound)
- High albedo (0.30) → smaller diameter (lower bound)

Returns `None` when H is unknown.

### PHA diameter threshold

PHAs are defined as having H ≤ 22, which corresponds to diameters roughly ≥ 140 m for typical albedos. The pipeline flags objects with H ≤ 22 AND MOID ≤ 0.05 AU as `pha_candidate`.

---

## Impact Energy

**Function**: `compute_impact_energy(diameter_m, velocity_km_s, density_kg_m3) -> float`

Returns the kinetic impact energy in megatons TNT equivalent:

```
E = 0.5 * m * v²
m = density * (4π/3) * (d/2)³
1 megaton TNT = 4.184 × 10¹⁵ J
```

Default parameters: `velocity_km_s = 20.0`, `density_kg_m3 = 2500` (silicate rock).

### Reference energies

| Diameter | Energy (MT TNT) | Event class |
|---|---|---|
| 25 m | ~0.5 | Tunguska-class airburst |
| 140 m | ~300 | Regional devastation |
| 1 km | ~100,000 | Global effects |
| 10 km | ~10⁸ | Mass extinction |

---

## Brier Skill Score

**Function**: `compute_brier_skill_score(probs, labels) -> float`

The Brier skill score (BSS) measures calibration improvement over a climatological baseline:

```
BSS = 1 − BS / BS_ref
BS_ref = ȳ * (1 − ȳ)    # climatological Brier score
```

where `ȳ` is the mean label (base rate of positives).

| BSS | Interpretation |
|---|---|
| 1.0 | Perfect predictions |
| 0.0 | No improvement over climatology |
| < 0.0 | Worse than climatology |

Returns 0.0 for empty inputs or single-class label sets.

---

## Resolution Score

**Function**: `compute_resolution_score(probs, labels, n_bins=10) -> float`

The resolution component of the Brier score decomposition measures how much the predicted per-bin outcome rates deviate from the overall base rate:

```
resolution = (1 / n) * Σ_k  n_k * (ȳ_k − ȳ)²
```

Higher resolution indicates better discrimination: the model concentrates probability mass on actually-positive and actually-negative sub-populations.

---

## Pipeline Integration

```python
from score import (
    compute_threat_score,
    compute_close_approach_score,
    compute_arc_quality_bonus,
    compute_weighted_hazard_score,
    compute_size_estimate,
    compute_impact_energy,
)
from calibration import compute_brier_skill_score, compute_resolution_score

# Score a single candidate
threat = compute_threat_score(neo)
close = compute_close_approach_score(neo)
arc = compute_arc_quality_bonus(neo)
hazard = compute_weighted_hazard_score(neo)  # primary ranking metric

# Size and energy
size_range = compute_size_estimate(neo)  # (min_m, max_m) or None
if size_range:
    energy_mt = compute_impact_energy(size_range[1], velocity_km_s=20.0)

# Calibration quality
bss = compute_brier_skill_score(probs, labels)
resolution = compute_resolution_score(probs, labels)
```

---

## CLI

```bash
# Batch weighted hazard scores from JSON
python Skills/compute_weighted_hazard_scores.py data/sample_tracklets.json --threshold 0.3
python Skills/compute_weighted_hazard_scores.py data/sample_tracklets.json --json

# Threat scores
python Skills/compute_threat_scores.py data/sample_tracklets.json --threshold 0.2
```

---

## Related Modules

- `score.py` — all scoring functions
- `calibration.py` — BSS, resolution score, Brier score, ECE
- `alert.py` — `compute_alert_age_days`, `ready_for_submission`, `format_candidate_dossier`
- `docs/THREAT_ASSESSMENT.md` — threat score formula, component breakdowns, interpretation
- `docs/ALERT_PROTOCOL.md` — alert-pathway decision tree and gate conditions
