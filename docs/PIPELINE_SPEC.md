# Pipeline Specification

Full stage-by-stage specification for the NEO Detection and Ranking Pipeline.

---

## Architecture

```
Fetch → Preprocess → Detect → Link → Classify → Score → Alert
```

Each stage produces a typed, immutable result object. No shared mutable state.

---

## Stage 1: fetch.py

**Inputs**: sky region (RA, Dec, radius), date range (JD), survey selection

**Process**:
- Query ZTF alert stream via IRSA TAP or `ztfquery`
- Download ATLAS forced photometry via REST API with polling
- Query MPC for known objects in the search field
- Query JPL Horizons for ephemerides of known NEOs
- Cache all results to disk; never re-download what is already cached

**Output**: `FetchResult(alerts: tuple[Observation, ...], provenance: FetchProvenance)`

**Key parameters**:
| Parameter | Default | Description |
|---|---|---|
| `radius_deg` | — | Cone search radius |
| `surveys` | `("ZTF",)` | Which surveys to query |
| `atlas_token` | `None` | ATLAS authentication token |

---

## Stage 2: preprocess.py

**Inputs**: raw `Observation` tuple from fetch stage

**Process**:
1. Reject observations with invalid coordinates or impossible magnitudes (mag ≤ 0 or > 35)
2. Decode base64 image cutouts and normalize pixel values to [0, 1] (1st–99th percentile)
3. Estimate PSF quality (peak-to-background SNR) and elongation (image moments)
4. Optionally apply Gaia DR3 astrometric correction via cone-search cross-match

**Output**: `PreprocessResult(sources: tuple[Observation, ...], provenance: PreprocessProvenance)`

**Notes**:
- ZTF alerts already include difference cutouts; no external image subtraction needed
- ATLAS: uses forced-photometry magnitudes directly (no cutouts)
- `apply_astrometry=False` skips the Gaia query (offline mode)

---

## Stage 3: detect.py

**Inputs**: preprocessed source catalog

**Process**:
1. Filter on real/bogus score (`rb ≥ 0.65` default; configurable)
2. Identify moving sources: compare positions across epochs; compute apparent motion rate
3. Accept motion rates in `[0.01, 60]` arcsec/hr (solar system window)
4. Flag streaks/trails via image moment elongation test
5. Cross-match against MPC known object ephemerides

**Output**: `DetectResult(candidates: list[RawCandidate], known_matches: list[KnownMatch])`

**Key parameters**:
| Parameter | Default | Description |
|---|---|---|
| `real_bogus_threshold` | `0.65` | Minimum real/bogus score |
| `motion_min_arcsec_per_hr` | `0.01` | Minimum motion for solar system object |
| `motion_max_arcsec_per_hr` | `60.0` | Maximum motion (above = satellite/artifact) |
| `mpc_cross_match` | `True` | Cross-match against MPC catalog |

---

## Stage 4: link.py

**Inputs**: single-night candidates across multiple nights

**Process**:
- Pair detections consistent with solar system object motion (0.01–60 arcsec/hr)
- Extend pairs to triplets and longer arcs using χ² orbit-consistency test
- Require ≥ 3 detections on ≥ 2 nights for a reportable tracklet
- Compute arc length, motion rate, position angle, and rate uncertainty

**Output**: `LinkResult(tracklets: list[Tracklet])`

**Notes**:
- Pure numpy/scipy implementation (THOR-inspired; Moeyens et al. 2021)
- No external orbit-determination dependency at this stage

---

## Stage 5: classify.py

**Inputs**: linked tracklets + image cutouts

### Tier 1 — XGBoost on tabular features

Features extracted by `extract_features()`:
| Feature | Description |
|---|---|
| `real_bogus_score` | Mean real/bogus score across tracklet |
| `arc_coverage_score` | Arc length normalized to [0, 1] at 30-day reference |
| `nights_observed_score` | Number of distinct nights observed |
| `brightness_score` | Mean magnitude proxy for size |
| `color_score` | g–r color index (None if single-band) |
| `lightcurve_variability_score` | Std of magnitudes (None if < 3 obs) |
| `motion_consistency_score` | Linear residual of sky positions |
| `streak_score` | Image moment elongation |

### Tier 2 — CNN on image triplets (Milestone 5)

63×63 pixel cutout triplets (science / reference / difference) normalized to [0, 1].
Based on Duev et al. (2019) architecture.

### Tier 3 — Transformer on tracklet sequences (Milestone 6)

BERT-style encoder over `(RA, Dec, magnitude, JD, filter)` observation tokens.

### Ensemble

Stacking meta-learner over Tier 1 + Tier 2 + Tier 3 outputs, calibrated via `calibration.py`.

**Output**: `(CandidateFeatures, NEOPosterior)`

---

## Stage 6: orbit.py

**Inputs**: linked tracklets (≥ 3 observations recommended)

**Process**:
1. Initial orbit determination via Gauss's method (pure Python/numpy)
2. Improve with one Gauss-Newton differential correction step
3. Compute Keplerian elements: a, e, i, Ω, ω, M₀
4. Classify as Amor/Apollo/Aten/IEO/MBA from (a, e, q, Q)
5. Compute MOID via simplified Öpik method (nodal crossing distances)
6. Assign orbit quality code (1 = arc < 1 day, 2 = multi-night, 3 = multi-week, 4 = opposition)

**Output**: `OrbitalElements | None`

**Dynamical classification boundaries**:
| Class | Condition |
|---|---|
| IEO (Atira) | Q < 0.983 AU |
| Aten | a < 1.0 AU, Q > 0.983 AU |
| Apollo | a ≥ 1.0 AU, q < 1.017 AU |
| Amor | 1.017 AU < q ≤ 1.3 AU |

---

## Stage 7: score.py

**Inputs**: classified tracklets with orbital elements

**Process**:
1. Compute `HazardAssessment`:
   - `moid_au` from orbit.py
   - `estimated_diameter_m` from H magnitude (geometric albedo p_v = 0.14)
   - `hazard_flag`: `pha_candidate` if MOID ≤ 0.05 AU and H ≤ 22
   - `alert_pathway` from ordered gate
2. Bayesian log-score model over 5 hypotheses
3. Compute `discovery_priority`, `followup_value`, `scientific_interest`

**Priors**:
| Hypothesis | Prior |
|---|---|
| neo_candidate | 0.05 |
| known_object | 0.30 |
| main_belt_asteroid | 0.35 |
| stellar_artifact | 0.25 |
| other_solar_system | 0.05 |

**Output**: `ScoredNEO`

---

## Stage 8: alert.py

**Inputs**: `ScoredNEO` objects

**Process**:
1. Format MPC 80-column observation report
2. Generate human-readable candidate summary
3. For `nasa_pdco_notify`: generate structured alert package
4. Log all alert actions with timestamps and provenance

**Output**: `AlertResult`

**Alert pathway gate** (ordered priority):
1. `internal_candidate` — below all external thresholds
2. `mpc_submission` — new candidate, meets quality threshold
3. `neocp_followup` — object on NEOCP; request observations
4. `nasa_pdco_notify` — MOID ≤ 0.05 AU + quality ≥ 2 + rb ≥ 0.90 + not known

---

## Data Flow Summary

```
Observation (raw)
  → Observation (preprocessed, cutouts normalized)
    → RawCandidate (motion detected)
      → Tracklet (multi-night arc)
        → CandidateFeatures + NEOPosterior (classified)
          → OrbitalElements (orbit fit)
            → ScoredNEO (hazard + alert pathway)
              → AlertResult (MPC report / NASA notification)
```

---

## Running the Pipeline

```bash
# Full end-to-end (offline synthetic data)
PYTHONPATH=src python Skills/run_pipeline.py

# Batch score from JSON file
PYTHONPATH=src python Skills/batch_score.py --input data/sample_tracklets.json

# Injection-recovery benchmark
PYTHONPATH=src python Skills/injection_recovery.py --n-inject 50

# Cross-match against MPC
PYTHONPATH=src python Skills/check_mpc_known.py --input data/sample_tracklets.json
```
