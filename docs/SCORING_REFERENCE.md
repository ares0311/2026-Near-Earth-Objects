# Scoring Reference

Comprehensive reference for all scoring, ranking, and hazard-assessment
functions implemented in `score.py`.

---

## Overview

The scoring stage produces a `ScoredNEO` for every linked tracklet that
passes the orbit stage. Each `ScoredNEO` carries three priority scalars
and a full `HazardAssessment`, all derived from the upstream feature
vector and orbital elements.

```
ScoredNEO
├── tracklet           (Tracklet — linked observations)
├── features           (CandidateFeatures — [0,1] scores)
├── posterior          (NEOPosterior — 5-class probabilities)
├── hazard             (HazardAssessment — flag, MOID, class)
└── metadata           (ScoringMetadata — priorities, run ID)
```

---

## Priority Scalars

All three priority scalars live on `ScoredNEO.metadata` and are in [0, 1].

| Field | Formula | Description |
|---|---|---|
| `discovery_priority` | See §Discovery Score | Main ranking criterion |
| `followup_value` | See §Followup Value | Observational urgency |
| `scientific_interest` | Unusual orbital elements | Interest to researchers |

---

## Discovery Score

```python
from score import compute_discovery_score

score = compute_discovery_score(neo)   # float in [0, 1]
```

Weighted combination of:

```
score = 0.5 × discovery_priority
      + 0.3 × orbit_quality_score
      + 0.2 × brightness_score
```

Clamped to [0, 1]. Prioritises novel, well-characterised, bright candidates.

---

## Threat Score

```python
from score import compute_threat_score

threat = compute_threat_score(neo)   # float in [0, 1]
```

Geometric mean of three components:

| Component | Formula | Notes |
|---|---|---|
| MOID proximity | `1 - moid_au / 0.3` | 0.5 sentinel when MOID unknown |
| Size proxy | from H magnitude (albedo 0.14) | 0.5 sentinel when H unknown |
| Orbit quality | `orbit_quality_score` | 0.5 sentinel when unknown |

All three components are clipped to [0, 1] before the geometric mean.

---

## Weighted Hazard Score

```python
from score import compute_weighted_hazard_score

w_hazard = compute_weighted_hazard_score(neo)   # float in [0, 1]
```

Linear combination of three sub-scores:

```
weighted_hazard = 0.4 × threat_score
                + 0.4 × close_approach_score
                + 0.2 × arc_quality_bonus
```

---

## Hazard Grade

```python
from score import compute_hazard_grade

grade = compute_hazard_grade(neo)   # "A", "B", "C", or "D"
```

Maps `compute_weighted_hazard_score` to a letter grade:

| Grade | Threshold | Interpretation |
|---|---|---|
| A | ≥ 0.70 | Highest hazard priority — immediate follow-up required |
| B | ≥ 0.50 | High priority |
| C | ≥ 0.30 | Moderate priority |
| D | < 0.30 | Routine monitoring |

---

## Close-Approach Score

```python
from score import compute_close_approach_score

ca_score = compute_close_approach_score(neo)   # float in [0, 1]
```

Proximity score based on MOID:

```
proximity = 1 - moid_au / 0.3      (max_moid = 0.3 AU)
score = min(1.0, proximity + 0.2)  if hazard_flag == "pha_candidate"
score = proximity                   otherwise
score = 0.5                         if MOID unknown
```

Note: `max_moid = 0.3 AU`, not 0.05. A MOID of 0.03 AU gives
`proximity = 0.9`, which is very high.

---

## Priority Rank

```python
from score import compute_priority_rank

ranked = compute_priority_rank(neos)
# [{"rank": 1, "object_id": "...", "discovery_priority": 0.87, "hazard_flag": "pha_candidate"}, ...]
```

Returns a list of dicts sorted descending by `discovery_priority`.
Rank 1 = highest priority candidate. Candidates without metadata are
assigned priority 0.0 and placed last.

---

## Observation Priority

```python
from score import compute_observation_priority

obs_priority = compute_observation_priority(neo)   # float in [0, 1]
```

Urgency based on how soon new observations are needed:

```
obs_priority = 0.3 × (last_obs_gap_score)
             + 0.4 × discovery_priority
             + 0.3 × orbit_uncertainty_score
```

where `last_obs_gap_score = min(1.0, gap_days / 7.0)`.

---

## Novelty Score

```python
from score import compute_novelty_score

novelty = compute_novelty_score(neo, catalog_elements)   # float in [0, 1]
```

Orbital distance from the nearest known NEO in (a, e, i) space:

```
d = sqrt(Δa² + Δe² + (Δi/180)²)
novelty = min(1.0, d)
```

Returns 1.0 (fully novel) when `catalog_elements` is empty. Useful for
identifying objects with unusual orbits.

---

## Impact Energy

```python
from score import compute_impact_energy

e_mt = compute_impact_energy(diameter_m=200, velocity_km_s=20.0, density_kg_m3=2500)
```

Kinetic energy in **megatons TNT** (1 Mt = 4.184 × 10¹⁵ J):

```
KE = 0.5 × m × v²   where m = ρ × (4/3)π(D/2)³
```

For reference: a 200 m object at 20 km/s gives ~1000 Mt.

---

## Size Estimate

```python
from score import compute_size_estimate

size = compute_size_estimate(neo)   # {"min_m": ..., "max_m": ...} or None
```

Diameter range in metres from H magnitude assuming geometric albedo
in [0.05, 0.30]:

```
D = 1329 km × 10^(-H/5) / sqrt(p_v)
```

Returns `None` if H is unknown.

---

## PHA Flag Logic

A candidate is flagged as `pha_candidate` when **all** of:

1. `moid_au ≤ 0.05 AU`
2. `absolute_magnitude_h ≤ 22`
3. `orbit_quality_code ≥ 2`

The flag `close_approach` is assigned when `moid_au ≤ 0.2 AU` but
not PHA-eligible. Otherwise `nominal`.

---

## Alert Pathway Gate

The alert pathway is determined by an ordered gate (see `ALERT_PROTOCOL.md`):

| Pathway | Conditions |
|---|---|
| `known_object` | `known_object_score > 0.8` |
| `internal_candidate` | `rb < 0.90` OR `MOID > 0.05` OR `quality < 2` |
| `mpc_submission` | All gate conditions met; awaiting confirmation |
| `neocp_followup` | On NEOCP; requesting independent confirmation |
| `nasa_pdco_notify` | CNEOS impact probability ≥ 0.01% (external trigger) |

---

## Scoring Model

### Log-Score Model

The NEO posterior is computed from a log-score model:

```
ℓ_i = log P(H_i) + Σ_k w_{ik} · φ_k(D)
p_i = exp(ℓ_i - ℓ_max) / Σ_j exp(ℓ_j - ℓ_max)
```

### Priors

| Hypothesis | Prior |
|---|---|
| `neo_candidate` | 0.05 |
| `known_object` | 0.30 |
| `main_belt_asteroid` | 0.35 |
| `stellar_artifact` | 0.25 |
| `other_solar_system` | 0.05 |

### Feature Weights (neo_candidate hypothesis)

| Feature | Weight |
|---|---|
| `real_bogus_score` | +2.0 |
| `arc_coverage_score` | +1.5 |
| `nights_observed_score` | +1.5 |
| `motion_consistency_score` | +1.2 |
| `orbit_quality_score` | +1.0 |
| `known_object_score` | −2.5 |
| `stellar_artifact_score` | −2.0 |
| `main_belt_consistency_score` | −1.5 |

---

## Posterior Update

```python
from classify import compute_posterior_update

updated = compute_posterior_update(prior, {"neo_candidate": 2.0, "stellar_artifact": -1.5})
```

Applies additional log-likelihood weights to an existing `NEOPosterior`
and renormalises. Useful for incorporating new evidence (e.g. a new
observation arc or spectroscopic data) without re-running the full pipeline.

---

## Followup Urgency

```python
from score import compute_followup_urgency

urgency = compute_followup_urgency(neo)   # "URGENT", "HIGH", "MEDIUM", "ROUTINE"
```

| Tier | Conditions |
|---|---|
| URGENT | PHA candidate with MOID ≤ 0.02 AU OR priority > 0.9 |
| HIGH | PHA candidate OR MOID ≤ 0.05 AU OR priority > 0.7 |
| MEDIUM | Close approach OR priority > 0.4 |
| ROUTINE | All others |

---

## See Also

- `docs/ALERT_PROTOCOL.md` — gate conditions and submission protocol
- `docs/THREAT_ASSESSMENT.md` — threat score formula and CLI
- `docs/ORBITAL_MECHANICS.md` — vis-viva, MOID, orbital elements
- `docs/SCORING_MODEL.md` — original Bayesian scoring reference
- `Skills/compute_priority_ranks.py` — batch priority rank table
- `Skills/compute_hazard_grades.py` — batch A/B/C/D hazard grade table
- `Skills/compute_threat_scores.py` — batch threat score table
- `Skills/triage_candidates.py` — urgency-sorted triage table
