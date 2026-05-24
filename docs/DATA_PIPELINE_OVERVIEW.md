# Data Pipeline Overview

End-to-end data flow for the NEO Detection & Ranking Pipeline, including
stage-by-stage I/O contracts, schema types, provenance chain, and guardrail
checkpoints.

---

## Architecture Summary

```
Fetch → Preprocess → Detect → Link → Classify → Score → Alert
```

Each stage:
- Accepts typed, immutable inputs (Pydantic frozen models or dataclasses)
- Produces typed, immutable result objects
- Records provenance (timestamps, versions, counts)
- Has no shared mutable state

---

## Stage-by-Stage I/O

### 1. Fetch

| | Type | Description |
|---|---|---|
| **Input** | `ObservationWindow` | Sky position, time range, survey selection |
| **Output** | `FetchResult` | Raw alerts + `FetchProvenance` |
| **Key schema** | `Observation` | Single photometric detection |

`FetchResult` carries:
- `alerts: tuple[Observation, ...]` — all retrieved observations
- `provenance: FetchProvenance` — survey, epoch, count, cache status

Data sources: ZTF (IRSA), ATLAS (REST), MPC, JPL Horizons.
All network calls are disk-cached; `force_refresh=True` bypasses cache.

---

### 2. Preprocess

| | Type | Description |
|---|---|---|
| **Input** | `tuple[Observation, ...]` | Raw observations from Fetch |
| **Output** | `PreprocessResult` | Validated sources + `PreprocessProvenance` |
| **Key schema** | `Observation` (enriched) | Normalized cutouts, astrometry-corrected |

Steps applied per observation:
1. Quality cuts (RA/Dec bounds, magnitude range)
2. Cutout normalization to [0, 1] (float32, base64-encoded)
3. Gaia DR3 astrometric correction (when available)

Key metrics: `compute_source_snr`, `compute_background_level`,
`compute_psf_asymmetry`, `compute_source_compactness`.

---

### 3. Detect

| | Type | Description |
|---|---|---|
| **Input** | `PreprocessResult` | Preprocessed sources |
| **Output** | `DetectResult` | Candidates + known matches + `DetectProvenance` |
| **Key schema** | `RawCandidate`, `KnownMatch` | Moving-source candidates |

Steps:
1. Real/bogus filter (`rb ≥ 0.65` default)
2. Pairwise motion rate computation (0.01–60 arcsec/hr)
3. Streak/trail identification via image moments
4. MPC cross-match (5 arcsec radius)

Satellites rejected if motion > 30 arcsec/hr along a single axis (≥ 98%).

---

### 4. Link

| | Type | Description |
|---|---|---|
| **Input** | `DetectResult` | Single-night raw candidates |
| **Output** | `LinkResult` | Linked tracklets + `LinkProvenance` |
| **Key schema** | `Tracklet` | ≥ 2 obs, ≥ 2 nights, orbit-consistent |

Algorithm (THOR-inspired):
1. Seed pairs from consecutive nights within position tolerance (10 arcsec)
2. Extend to triplets+ using quadratic/linear arc prediction
3. χ² orbit-consistency filter (reduced χ² < 5)
4. Deduplicate overlapping tracklets (longest arc wins)
5. Satellite trail rejection

Output tracklets carry: `arc_days`, `motion_rate_arcsec_per_hour`,
`motion_pa_degrees`, `observations: tuple[Observation, ...]`.

---

### 5. Classify

| | Type | Description |
|---|---|---|
| **Input** | `list[Tracklet]` | Linked tracklets |
| **Output** | `(CandidateFeatures, NEOPosterior)` per tracklet | Features + posterior |
| **Key schema** | `CandidateFeatures`, `NEOPosterior` | 14 feature scores, 5-class posterior |

Three-tier ML architecture:

**Tier 1** — XGBoost on `CandidateFeatures` (14 tabular scores)
**Tier 2** — CNN on 63×63 image triplets (science / reference / difference)
**Tier 3** — Transformer on observation sequences (RA, Dec, mag, JD, filter)
**Ensemble** — Logistic regression meta-learner over Tier 1/2/3 outputs

Posterior hypotheses: `neo_candidate`, `known_object`, `main_belt_asteroid`,
`stellar_artifact`, `other_solar_system`.

Confidence: `compute_tier1_confidence(features)` returns fraction of non-None features.

---

### 6. Orbit

| | Type | Description |
|---|---|---|
| **Input** | `Tracklet` | Linked tracklet (≥ 3 nights recommended) |
| **Output** | `OrbitalElements` | Keplerian elements + quality code |
| **Key schema** | `OrbitalElements` | a, e, i, Ω, ω, M₀, quality_code |

Steps:
1. Gauss's method → initial state vector
2. Differential correction (least-squares)
3. NEO class assignment (Amor/Apollo/Aten/IEO/MBA)
4. MOID computation vs Earth's orbit
5. Quality code: 1 (< 1 day) → 4 (multi-opposition)

Short arcs (< 24 hr): MOID unreliable; flagged `quality_code = 1`.

---

### 7. Score

| | Type | Description |
|---|---|---|
| **Input** | `(Tracklet, CandidateFeatures, NEOPosterior, OrbitalElements)` | All prior stage outputs |
| **Output** | `ScoredNEO` | Full hazard assessment + scoring metadata |
| **Key schema** | `ScoredNEO`, `HazardAssessment`, `ScoringMetadata` | |

`HazardAssessment` fields:
- `hazard_flag`: `pha_candidate` / `close_approach` / `nominal` / `unknown`
- `moid_au`: minimum orbit intersection distance
- `estimated_diameter_m`: from H and albedo 0.14
- `alert_pathway`: gate-selected routing

Discovery/followup/scientific priority scores in `ScoringMetadata`.
Risk metrics: `compute_weighted_risk_score`, `compute_threat_score`.

---

### 8. Alert

| | Type | Description |
|---|---|---|
| **Input** | `list[ScoredNEO]` | Ranked scored candidates |
| **Output** | Formatted reports + audit log | MPC/NEOCP/NASA bundles |
| **Key schema** | `AlertPackage` | Submission bundle with guardrail |

Alert pathways (ordered gate):

| Pathway | Trigger condition |
|---|---|
| `known_object` | `known_object_score > 0.8` |
| `internal_candidate` | rb < 0.90, or orbit quality < 2, or MOID > 0.05 AU |
| `mpc_submission` | MOID ≤ 0.05 AU, quality ≥ 2, rb ≥ 0.90, not known |
| `neocp_followup` | Object appears on NEOCP |
| `nasa_pdco_notify` | Scout/Sentry assigns P_impact ≥ 0.01% (Step 3 only) |

All alert actions are logged with timestamps and full provenance.

---

## Provenance Chain

Each stage records a provenance object:

```
FetchProvenance → PreprocessProvenance → DetectProvenance → LinkProvenance
                                                               ↓
                                                         ScoringMetadata
```

`ScoringMetadata` carries: `scorer_version`, `pipeline_run_id`,
`discovery_priority`, `followup_value`, `scientific_interest`.

---

## Guardrail Checkpoints

| Stage | Guardrail |
|---|---|
| Classify | Unknown objects default to "candidate", not "confirmed NEO" |
| Orbit | MOID unreliable for arcs < 24 hr (quality_code = 1) |
| Score | PHA flag requires quality_code ≥ 2 |
| Alert (Step 1) | MPC submission before any external notification |
| Alert (Step 2) | Wait ≥ 24 hr or ≥ 2 independent confirmations |
| Alert (Step 3) | NASA PDCO notified only after Scout/Sentry impact signal |
| All outputs | Never assert impact probability without MPC/CNEOS confirmation |

---

## Schema Evolution Notes

All models use `ConfigDict(frozen=True)` — immutable after construction.
New optional fields should have `default=None` to maintain backward compatibility
with cached/serialized data.  Breaking changes (renaming, removing fields) require
a version bump and migration note in `CHANGELOG.md`.

Key schema types by pipeline stage:

| Stage | Primary Input | Primary Output |
|---|---|---|
| Fetch | `ObservationWindow` | `FetchResult` |
| Preprocess | `FetchResult` | `PreprocessResult` |
| Detect | `PreprocessResult` | `DetectResult` |
| Link | `DetectResult` | `LinkResult` |
| Classify | `Tracklet` | `CandidateFeatures`, `NEOPosterior` |
| Orbit | `Tracklet` | `OrbitalElements` |
| Score | All above | `ScoredNEO` |
| Alert | `list[ScoredNEO]` | Reports, `AlertPackage` |

---

## Running the Pipeline

```bash
# Full end-to-end synthetic run
PYTHONPATH=src python Skills/run_pipeline.py

# Diagnose each stage individually
PYTHONPATH=src python Skills/diagnose_pipeline.py

# Injection-recovery test (n=200)
PYTHONPATH=src python Skills/injection_recovery.py --n 200 --seed 42 --json data/out.json

# Background automation (offline scheduling)
PYTHONPATH=src python Skills/background.py automation-readiness
```
