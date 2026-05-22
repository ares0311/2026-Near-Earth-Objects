# Scoring Model v2 — Updated Reference

This document extends the original `docs/SCORING_MODEL.md` with three new scoring
primitives added in v0.40.0: `compute_size_estimate`, `compute_close_approach_score`,
and `compute_observation_priority`.  It also documents the `compute_true_anomaly`
orbital utility used to propagate orbits more accurately.

---

## Scope

The scoring stage (`score.py`) converts classified tracklets with preliminary
orbital elements into a ranked list of NEO candidates.  This document covers the
updated set of scalar scores available as of v0.40.0.

---

## Size Estimate

**Function**: `compute_size_estimate(neo) → dict | None`

Uses the standard H–D relationship:

```
D = 1329 / sqrt(p_v) × 10^(−H/5)   [km]
```

where *H* is the absolute magnitude and *p_v* is the geometric albedo.  The
pipeline evaluates the formula at two extreme albedo values to produce a diameter
range:

| Albedo | Diameter |
|--------|----------|
| p_v = 0.30 (bright, high-albedo) | D_min |
| p_v = 0.05 (dark, low-albedo)    | D_max |

### Output

```python
{
    "min_m": float,            # minimum diameter in metres
    "max_m": float,            # maximum diameter in metres
    "assumed_albedo_range": [0.05, 0.30],
}
```

Returns `None` if `absolute_magnitude_h` is `None` or not finite.

### Interpretation

| H | Approx. diameter (p_v = 0.14) |
|---|-------------------------------|
| 17 | ~1 km |
| 22 | ~140 m |
| 25 | ~40 m |
| 28 | ~10 m |

---

## Close-Approach Score

**Function**: `compute_close_approach_score(neo) → float`

Combines MOID proximity with PHA status into a single [0, 1] urgency scalar:

```
proximity = max(0, 1 − MOID / 0.3 AU)
bonus     = 0.2  if  hazard_flag == "pha_candidate"  else  0.0
score     = min(1.0, proximity + bonus)
```

| MOID (AU) | PHA? | Score |
|-----------|------|-------|
| 0.00 | yes | 1.00 |
| 0.00 | no  | 1.00 |
| 0.05 | yes | 1.00 (clamped) |
| 0.05 | no  | 0.83 |
| 0.15 | no  | 0.50 |
| 0.30 | no  | 0.00 |
| None | any | 0.50 (sentinel) |

---

## Observation Priority

**Function**: `compute_observation_priority(neo) → float`

Weighted combination of three urgency signals:

```
priority = 0.3 × gap_score + 0.4 × discovery_priority + 0.3 × orbit_urgency
```

Where:

- **gap_score** = min(1, days_since_last_obs / 30) — older observations are more
  urgent to re-observe.
- **discovery_priority** = `metadata.discovery_priority` — pipeline discovery score.
- **orbit_urgency** = 1 − `orbit_quality_score` — poorly constrained orbits need
  more data.

---

## True Anomaly

**Function**: `compute_true_anomaly(E_rad, e) → float`

Converts eccentric anomaly *E* to true anomaly *ν* via the half-angle formula:

```
ν = 2 · atan( sqrt((1+e)/(1−e)) · tan(E/2) )
```

Result is returned in [0, 2π).  Raises `ValueError` for e ≥ 1.

Used internally by `propagate_orbit` and available for custom ephemeris
calculations in Skills scripts.

---

## Score Combination Table (v0.40.0)

| Function | Range | Primary Use |
|----------|-------|-------------|
| `compute_discovery_score` | [0, 1] | Ranking new candidates |
| `compute_threat_score` | [0, 1] | Hazard triage |
| `compute_close_approach_score` | [0, 1] | Close-approach urgency |
| `compute_observation_priority` | [0, 1] | Follow-up scheduling |
| `compute_followup_urgency` | URGENT/HIGH/MEDIUM/ROUTINE | Human triage tier |
| `compute_novelty_score` | [0, 1] | Scientific interest |
| `compute_size_estimate` | dict (min/max m) | Physical characterisation |

---

## CLI Usage

```bash
# Batch close-approach scores
python Skills/compute_discovery_scores.py data/sample_tracklets.json --json

# Triage by urgency
python Skills/triage_candidates.py data/sample_tracklets.json --urgency URGENT

# Compute true anomaly for tracklets with orbital elements
python Skills/compute_true_anomaly.py data/sample_tracklets.json --json

# Export full candidate dossiers
python Skills/export_candidate_dossiers.py data/sample_tracklets.json --out-dir reports/
```

---

## Guardrails

- Never quote an impact probability in any score output.
- All scores are internal pipeline rankings — not authoritative hazard assessments.
- Defer hazard communication to MPC/CNEOS following the alert protocol.

*See `docs/ALERT_PROTOCOL.md` and `docs/THREAT_ASSESSMENT.md` for the
authoritative alert decision tree.*
