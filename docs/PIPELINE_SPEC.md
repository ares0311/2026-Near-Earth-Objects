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
| `force_refresh` | `False` | Bypass on-disk cache and re-download |

**Batch API**: `fetch_batch(targets, radius_deg, start_jd, end_jd, ...)` accepts a list of `(ra_deg, dec_deg)` tuples and returns one `FetchResult` per target.

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

**Batch API**: `preprocess_batch(fetch_results, apply_astrometry)` accepts a list of `FetchResult` objects and returns one `PreprocessResult` per input.

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

**Batch API**: `detect_batch(preprocess_results, real_bogus_threshold, mpc_cross_match)` accepts a list of `PreprocessResult` objects and returns one `DetectResult` per input.

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

**Additional APIs**:
- `merge_tracklets(a, b)` — combine two tracklets into a longer arc; deduplicates by `obs_id`, recomputes motion rate and PA.

**Notes**:
- Pure numpy/scipy implementation (THOR-inspired; Moeyens et al. 2021)
- No external orbit-determination dependency at this stage
- Satellite/debris trail filter: candidate pairs with purely E-W or N-S motion at rate ≥ 30 arcsec/hr are rejected.

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

**Additional APIs** (v0.13.0):
- `arc_quality_report(tracklet)` — returns quality dict with `arc_days`, `n_observations`, `n_nights`, `quality_code` (1–4), `arc_warning`, and `recommended_action`.
- `propagate_orbit(elements, dt_days)` — two-body Keplerian propagation; advances `mean_anomaly_deg` and `epoch_jd`.
- `predict_ephemeris(elements, jd)` — approximate geocentric RA/Dec at a target JD; returns `{ra_deg, dec_deg, helio_dist_au, jd}`.

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

**Additional APIs** (v0.13.0):
- `score_batch(items, pipeline_run_id)` — score a list of `(tracklet, features, posterior, orbital)` tuples; returns `list[ScoredNEO]`.
- `rank_candidates(neos)` — sort a list of `ScoredNEO` objects by descending discovery priority; PHA candidates always rank above non-PHA.
- `ScoringMetadata.close_approach_au` — populated with MOID value when orbit quality ≥ 2.

---

## Stage 8: alert.py

**Inputs**: `ScoredNEO` objects

**Process**:
1. Format MPC 80-column observation report
2. Generate human-readable candidate summary
3. For `nasa_pdco_notify`: generate structured alert package
4. Log all alert actions with timestamps and provenance

**Output**: alert result dict

**Additional APIs** (v0.13.0):
- `generate_alert_package(neo, obs_code)` — bundle MPC report, MPC JSON, summary, hazard flag, alert pathway, and observation count into a single dict.
- `batch_process_alerts(neos, dry_run, mpc_obs_code)` — process a list of `ScoredNEO` objects; per-item exceptions recorded as `{"error": ...}` entries.
- `monitor_neocp(object_id, max_wait_hr, poll_interval_hr)` — blocking NEOCP poll loop with injectable sleep for testing.
- `format_mpc_json(neo, obs_code)` — MPC JSON submission dict.

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

## Top-level container: PipelineResult

`PipelineResult` (v0.13.0) is an immutable Pydantic model that bundles the outputs of all pipeline stages into a single object.

| Field | Type | Description |
|---|---|---|
| `run_id` | `str` | Unique identifier for this pipeline run |
| `started_at_jd` | `float` | JD when the run began |
| `finished_at_jd` | `float` | JD when the run completed |
| `fetch` | `FetchResult` | Raw fetch output |
| `preprocess` | `PreprocessResult` | Preprocessed sources |
| `detect` | `DetectResult` | Candidate detections |
| `link` | `LinkResult` | Linked tracklets |
| `scored_neos` | `tuple[ScoredNEO, ...]` | Ranked scored candidates |
| `pipeline_version` | `str` | Version tag (default `""`) |
| `n_pha_candidates` | `int` | Count of PHA-flagged candidates |

---

## Running the Pipeline

```bash
# Full end-to-end (offline synthetic data)
PYTHONPATH=src python Skills/run_pipeline.py

# Generate synthetic survey observations
PYTHONPATH=src python Skills/simulate_survey.py --objects 10 --nights 3

# Batch score from JSON file
PYTHONPATH=src python Skills/batch_score.py --input data/sample_tracklets.json

# Export ranked table (CSV or HTML)
PYTHONPATH=src python Skills/export_ranked_table.py scored.json --format html --out ranked.html

# Check orbit quality for tracklets
PYTHONPATH=src python Skills/check_orbit_quality.py data/sample_tracklets.json

# Injection-recovery benchmark
PYTHONPATH=src python Skills/injection_recovery.py --n-inject 50

# Cross-match against MPC
PYTHONPATH=src python Skills/check_mpc_known.py --input data/sample_tracklets.json

# Validate MPC 80-column report
PYTHONPATH=src python Skills/validate_mpc_report.py report.txt

# Compare injection-recovery baselines
PYTHONPATH=src python Skills/compare_baselines.py data/injection_recovery_baseline.json data/injection_recovery_n200.json
```
