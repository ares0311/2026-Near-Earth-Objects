# Scoring Pipeline Guide

Technical reference for the scoring stage (`score.py`) of the NEO Detection Pipeline.

---

## NEOPosterior Hypotheses and Priors

The scoring model evaluates each candidate against five exclusive hypotheses:

| Hypothesis | Symbol | Prior | Description |
|---|---|---|---|
| `neo_candidate` | H_neo | 0.05 | Genuine new Near-Earth Object |
| `known_object` | H_ko | 0.30 | Matches a known MPC catalog object |
| `main_belt_asteroid` | H_mba | 0.35 | Main-belt asteroid on an unremarkable orbit |
| `stellar_artifact` | H_art | 0.25 | Instrumental artifact, cosmic ray, or satellite trail |
| `other_solar_system` | H_other | 0.05 | Comet, TNO, or other solar system body |

Priors are deliberately pessimistic about new NEOs: most moving detections are known objects or artifacts. Adjust priors for high-ecliptic-latitude fields where MBA contamination is lower.

---

## Log-Score Model Formula

The posterior probability for each hypothesis H_i is computed via a log-score model:

```
ℓ_i = log P(H_i) + Σ_k w_{ik} · φ_k(D)
```

```
p_i = exp(ℓ_i − ℓ_max) / Σ_j exp(ℓ_j − ℓ_max)
```

All feature scores φ_k ∈ [0, 1]. Missing features contribute 0 (neutral — no update from prior).

### Key Feature Weights for neo_candidate

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

## CandidateFeatures Fields

All feature scores are `float | None` (type alias `OptScore`) bounded in [0, 1].

| Field | Description |
|---|---|
| `real_bogus_score` | Real/bogus classifier output; 1.0 = genuine source |
| `streak_score` | Streak/trail probability; 1.0 = clear trail |
| `psf_quality_score` | PSF fit quality; 1.0 = stellar PSF |
| `motion_consistency_score` | Linear motion fit quality |
| `arc_coverage_score` | Arc length relative to target (multi-night) |
| `nights_observed_score` | Number of distinct observing nights (normalized) |
| `brightness_score` | Proxy for object size (brighter = larger) |
| `color_score` | g−r, r−i color index consistency |
| `lightcurve_variability_score` | Variability along the tracklet |
| `orbit_quality_score` | 0 = poor (short arc), 1 = good (multi-week) |
| `moid_score` | 1.0 if MOID ≤ 0.05 AU |
| `neo_class_confidence` | Confidence in NEO dynamical class |
| `pha_flag_confidence` | Confidence in PHA classification |
| `known_object_score` | 0 = new object, 1 = confirmed known object |

---

## HazardAssessment Construction

`HazardAssessment` is built in `score.py` after orbit fitting:

1. **moid_au**: computed by `orbit.compute_moid`; `None` if arc quality < 2
2. **estimated_diameter_m**: derived from absolute magnitude H using `p_v = 0.14` (default albedo)
3. **hazard_flag**: determined by gate conditions:
   - `"pha_candidate"`: MOID ≤ 0.05 AU AND H ≤ 22, orbit quality ≥ 2
   - `"close_approach"`: MOID ≤ 0.2 AU (but not PHA)
   - `"nominal"`: MOID > 0.2 AU, orbit quality ≥ 2
   - `"unknown"`: insufficient data
4. **alert_pathway**: from the ordered gate (see Alert Protocol):
   - `"known_object"` → skip external reporting
   - `"internal_candidate"` → below threshold
   - `"mpc_submission"` → MOID ≤ 0.05 AU, quality ≥ 2, rb ≥ 0.90, neo_prob ≥ 0.50

---

## ScoringMetadata Fields

| Field | Type | Description |
|---|---|---|
| `scorer_version` | str | Version of the scoring model |
| `scored_at_jd` | float | Julian Date when scoring ran |
| `pipeline_run_id` | str | Run identifier for provenance |
| `discovery_priority` | float | Combined novelty + orbit quality + PHA flag score |
| `followup_value` | float | Urgency for follow-up observation |
| `scientific_interest` | float | Unusual orbital parameters or short MOID |
| `close_approach_au` | float \| None | Close approach distance (from MOID when quality ≥ 2) |

---

## rank_candidates Sort Order

`rank_candidates(neos)` returns a list of `ScoredNEO` objects sorted by:

1. **PHA tier first**: PHA candidates (`hazard_flag == "pha_candidate"`) rank above all others
2. **discovery_priority descending**: within each tier, higher priority scores rank first

---

## Conservative Classification Policy

- `None` feature scores contribute 0 (neutral); they never penalize a candidate
- Unknown objects default to `"internal_candidate"` alert pathway, not `"mpc_submission"`
- PHA flag requires orbit quality code ≥ 2 before the `"pha_candidate"` hazard flag is set
- A `neo_candidate` posterior < 0.50 blocks the `mpc_submission` pathway even if MOID and orbit quality pass
- Never output "confirmed NEO" for internally detected objects — always `"neo_candidate"`
- All alerts include guardrail statements containing "NOT" to prevent misinterpretation
