# CLAUDE.md — NEO Detection & Ranking Project

This file is read automatically by Claude Code at session start.
It contains the facts a coding agent needs to work productively without re-reading every document.

---

## Standing Rules

- **Skills directory**: Any standalone `.py` utility script created to perform a task must be saved in `Skills/` at the project root.
- **No impact claims**: Never assert a probability of Earth impact from internally computed data alone. Always defer to MPC/CNEOS for authoritative hazard assessment.
- **Alert protocol is sacred**: The NASA/MPC alert pathway (see §Alert Protocol) must never be triggered on unconfirmed detections. Require independent confirmation first.

---

## Project

**Near-Earth Object Detection and Ranking Pipeline**
Automated pipeline for detecting, linking, classifying, and ranking Near-Earth Object (NEO) candidates from publicly available survey photometry, with MPC-compatible reporting and a NASA alert pathway for high-confidence hazard signals.

Repository: `<owner>/neo-detection` (to be created)
Active branch: `main`

---

## Scientific Context

Near-Earth Objects are small solar system bodies with perihelion distances $q < 1.3$ AU. They are divided into four dynamical classes:

| Class | Definition |
|---|---|
| Amor | $1.017 < q < 1.3$ AU |
| Apollo | $a > 1.0$ AU, $q < 1.017$ AU |
| Aten | $a < 1.0$ AU, $Q > 0.983$ AU |
| IEO (Atira) | $Q < 0.983$ AU |

Potentially Hazardous Asteroids (PHAs) are NEOs with absolute magnitude $H \leq 22$ (diameter $\gtrsim 140$ m) and Minimum Orbit Intersection Distance (MOID) $\leq 0.05$ AU. The pipeline must identify and flag PHA candidates.

The global NEO survey is dominated by:
- **ZTF** (Zwicky Transient Facility) — primary data source; public alert stream
- **ATLAS** — Asteroid Terrestrial-impact Last Alert System; 24–48 hr warning capability
- **Pan-STARRS** — deep survey; public catalog access
- **CSS** (Catalina Sky Survey) — MPC-feeding survey

As of 2026, approximately 35,000 NEOs are known. Rubin/LSST is expected to discover 100,000+ more over its 10-year survey.

---

## Architecture

```
Fetch → Preprocess → Detect → Link → Classify → Score → Alert
```

Each stage produces a typed, immutable result object. No shared mutable state.

### Module Build Order

| Module | Status | Tests | Description |
|---|---|---|---|
| `schemas.py` | complete | test_schemas.py | All pipeline data models (Pydantic, frozen) |
| `fetch.py` | complete | test_fetch.py | ZTF/ATLAS/MPC data retrieval |
| `preprocess.py` | complete | test_preprocess.py | Difference image handling, source extraction |
| `detect.py` | complete | test_detect.py | Moving object detection; streak/trail identification |
| `link.py` | complete | test_link.py | Tracklet linking across nights |
| `classify.py` | complete | test_classify.py | ML real/bogus + NEO type classification |
| `orbit.py` | complete | test_orbit.py | Preliminary orbit fitting; MOID calculation |
| `score.py` | complete | test_score.py | Hazard ranking; PHA flag; novelty score |
| `alert.py` | complete | test_alert.py | MPC report formatting; NASA alert protocol |
| `calibration.py` | complete | test_calibration.py | Classifier calibration (Platt / isotonic PAVA) |

Build in the order listed. Each module depends on all prior modules.

---

## Data Sources

### Primary Survey Data

**ZTF (recommended primary source)**
- Public alert stream via IRSA (`ztfquery` Python package or direct API)
- 3-night cadence over the full northern sky; $g$, $r$, $i$ bands
- Difference-image alerts include cutouts (science, reference, difference) — ideal for CNN input
- Access: `pip install ztfquery`; IRSA account required (free)
- Key fields per alert: `ra`, `dec`, `jd`, `magpsf`, `sigmapsf`, `fid`, `rb` (real/bogus score), `drb` (deep learning real/bogus), `ssdistnr`, `ssmagnr`

**ATLAS Forced Photometry Server**
- Public REST API; forced photometry at any sky position
- Orange ($o$) and cyan ($c$) bands; 2-day cadence
- Useful for confirming candidates found in ZTF
- Access: `https://fallingstar-data.com/forcedphot/`

**Minor Planet Center (MPC)**
- Known object catalog: `astroquery.mpc` or direct MPC API
- NEO Confirmation Page (NEOCP): unconfirmed candidates needing follow-up
- Submit formatted reports for new detections
- Access: `from astroquery.mpc import MPC`

**JPL Horizons / CNEOS**
- Ephemerides for known objects: `astroquery.jplhorizons`
- Close approach tables: CNEOS API
- Scout and Sentry impact monitoring output (read-only reference)

### Astrometric Reference
- **Gaia DR3** via `astroquery.gaia` — sub-milliarcsecond astrometry for calibration

---

## Core Design Decisions

### DECISION-001: ZTF as Primary Survey
ZTF provides the richest freely available alert stream with pre-computed difference images, a native real/bogus score, and a well-documented Python API. It is the most scientifically productive single choice for a new project without telescope access.

### DECISION-002: Tiered ML Architecture
Follow the same three-tier approach as the exoplanet pipeline:
- **Tier 1**: Gradient-boosted trees (XGBoost/LightGBM) on tabular features — fast, interpretable, works with small labeled sets (~500 examples)
- **Tier 2**: CNN on ZTF image triplets (science / reference / difference cutouts) — proven for real/bogus classification (Duev et al. 2019)
- **Tier 3**: Transformer on tracklet sequences — frontier method for multi-night linking and NEO type classification (Lin et al. 2022)

### DECISION-003: No Autonomous Impact Claims
The pipeline produces a ranked candidate list and hazard flags. It never autonomously asserts a probability of Earth impact. The alert pathway requires a computed MOID ≤ 0.05 AU AND independent MPC confirmation before any NASA notification.

### DECISION-004: MPC-Compatible Output First
All detections must be expressible in MPC 80-column format or the newer MPC JSON format. This ensures interoperability with the global NEO community regardless of downstream ML additions.

### DECISION-005: Conservative Classification
Mirror the exoplanet pipeline's conservatism:
- `None` feature scores fail gate conditions
- Unknown objects default to "candidate" not "confirmed NEO"
- PHAs require orbit quality code ≥ 2 before flagging

---

## Key Types (schemas.py)

All models use `ConfigDict(frozen=True)` — immutable after construction.

```python
Mission = Literal["ZTF", "ATLAS", "PanSTARRS", "CSS", "MPC"]

NEOClass = Literal["amor", "apollo", "aten", "ieo", "unknown"]

HazardFlag = Literal["pha_candidate", "close_approach", "nominal", "unknown"]

AlertPathway = Literal[
    "mpc_submission",        # Report to MPC for confirmation
    "neocp_followup",        # Object on NEOCP; request observations
    "nasa_pdco_notify",      # High-confidence PHA; follow NASA protocol
    "internal_candidate",    # Below threshold for external reporting
    "known_object",          # Matches MPC catalog
]

# Core signal
@dataclass(frozen=True)
class Tracklet:
    object_id: str
    observations: tuple[Observation, ...]  # ≥2 obs per tracklet
    arc_days: float
    motion_rate_arcsec_per_hour: float
    motion_pa_degrees: float

# Feature vector (all OptScore = float | None, bounded [0,1])
class CandidateFeatures(BaseModel):
    # Detection quality
    real_bogus_score: OptScore
    streak_score: OptScore
    psf_quality_score: OptScore
    # Motion
    motion_consistency_score: OptScore
    arc_coverage_score: OptScore
    nights_observed_score: OptScore
    # Photometry
    brightness_score: OptScore       # proxy for size
    color_score: OptScore             # g-r, r-i
    lightcurve_variability_score: OptScore
    # Orbit (populated after orbit.py)
    orbit_quality_score: OptScore    # 0=poor, 1=good
    moid_score: OptScore             # 1 = MOID ≤ 0.05 AU
    neo_class_confidence: OptScore
    pha_flag_confidence: OptScore
    # Catalog
    known_object_score: OptScore     # 0 = new, 1 = known

# Posterior over NEO classification hypotheses
class NEOPosterior(BaseModel):
    neo_candidate: Score             # genuine new NEO
    known_object: Score              # matches MPC catalog
    main_belt_asteroid: Score        # MBA on unusual orbit
    stellar_artifact: Score          # cosmic ray / satellite / artifact
    other_solar_system: Score        # comet, TNO, etc.

class HazardAssessment(BaseModel):
    hazard_flag: HazardFlag
    moid_au: float | None
    estimated_diameter_m: float | None
    absolute_magnitude_h: float | None
    neo_class: NEOClass
    alert_pathway: AlertPathway
    explanation: CandidateExplanation

class ScoredNEO(BaseModel):
    tracklet: Tracklet
    features: CandidateFeatures
    posterior: NEOPosterior
    hazard: HazardAssessment
    metadata: ScoringMetadata
```

---

## Pipeline Stage Specifications

### 1. fetch.py
**Inputs**: sky region (RA, Dec, radius) or target list, date range, survey selection
**Process**:
- Query ZTF alert stream via IRSA or `ztfquery`
- Download ATLAS forced photometry for confirmed positions
- Query MPC for known objects in the search field
- Query JPL Horizons for ephemerides of known NEOs

**Output**: `FetchResult(alerts, provenance: FetchProvenance)`

**Notes**:
- Lazy-import all survey-specific libraries inside functions
- Cache raw alerts to disk; never re-download what is already cached
- Record survey, filter, limiting magnitude, and epoch in provenance

### 2. preprocess.py
**Inputs**: raw alerts with image cutouts
**Process**:
- Validate difference image quality (PSF, background RMS)
- Normalize cutout pixel values to [0,1] for CNN input
- Extract aperture photometry and morphological features
- Apply astrometric correction relative to Gaia DR3

**Output**: `PreprocessResult(sources, provenance: PreprocessProvenance)`

**Notes**:
- No external image-subtraction pipeline needed — ZTF alerts already include difference cutouts
- For ATLAS: use forced-photometry magnitudes directly

### 3. detect.py
**Inputs**: preprocessed source catalog
**Process**:
- Filter on real/bogus score (`rb ≥ 0.65` default threshold; configurable)
- Identify moving sources: compare positions across epochs; compute apparent motion rate
- Flag streaks/trails (fast-moving NEOs may trail in 30s ZTF exposures)
- Cross-match against MPC known object ephemerides to separate new vs. known

**Output**: `DetectResult(candidates: list[RawCandidate], known_matches: list[KnownMatch])`

### 4. link.py
**Inputs**: single-night candidates across multiple nights
**Process**:
- Implement a simplified tracklet linker (THOR-inspired; Moeyens et al. 2021):
  - Pair detections consistent with solar system object motion (0.01–60 arcsec/hr)
  - Extend pairs to triplets and longer arcs using a $\chi^2$ orbit-consistency test
- Require ≥3 detections on ≥2 nights for a reportable tracklet
- Compute arc length, motion rate, position angle, and rate uncertainty

**Output**: `LinkResult(tracklets: list[Tracklet])`

**Notes**:
- Pure numpy/scipy implementation; no external orbit-determination dependency at this stage
- `orbit.py` handles full orbit fitting downstream

### 5. classify.py
**Inputs**: linked tracklets + image cutouts
**Process** (three-tier, build in order):

**Tier 1 — XGBoost on tabular features**
- Features: real/bogus score, motion rate, arc length, nights observed, brightness, color index, streak score, PSF elongation, MPC match distance
- Labels: ZTF real/bogus labels + MPC confirmed NEO catalog
- Output: `real_bogus_score`, `neo_class_confidence` as `OptScore`

**Tier 2 — CNN on image triplets** (build after Tier 1 is calibrated)
- Input: 63×63 pixel cutout triplets (science, reference, difference) normalized to [0,1]
- Architecture: adapted from Duev et al. (2019) — three parallel convolutional branches merged at dense layer
- Pre-trained weights from ZTF real/bogus training set (public) available as starting point
- Fine-tune on confirmed NEO vs. artifact subset
- Output: calibrated real/bogus probability

**Tier 3 — Transformer on tracklet sequences** (frontier; build after Tier 2)
- Input: sequence of (RA, Dec, magnitude, time, filter) observations per tracklet, tokenized per observation
- Architecture: standard encoder-only transformer (BERT-style) with positional encoding based on observation time
- Task: multi-class classification (neo_candidate / known_object / main_belt / artifact / other)
- Training data: MPC observation history for confirmed NEOs + MBA sample + artifact labels from ZTF
- Reference: Lin et al. (2022) applied transformers to asteroid light-curve classification

**Ensemble (Tier 3 output)**
- Stacking meta-learner (logistic regression) over Tier 1 + Tier 2 + Tier 3 outputs
- Calibrate final probabilities via `calibration.py` (Platt or isotonic)

### 6. orbit.py
**Inputs**: linked tracklets (≥3 nights recommended)
**Process**:
- Initial orbit determination via Gauss's method (pure Python/numpy)
- Improve with differential correction (least-squares fit to observed positions)
- Compute orbital elements: $a$, $e$, $i$, $\Omega$, $\omega$, $M_0$
- Classify as Amor/Apollo/Aten/IEO/MBA from $(a, e, q, Q)$
- Compute MOID (Minimum Orbit Intersection Distance) relative to Earth's orbit
- Assign orbit quality code (1 = arc < 1 day, 2 = multi-night, 3 = multi-week, 4 = opposition)

**Notes**:
- Use `astropy` for coordinate transformations
- For short arcs (<24 hr), MOID is unreliable — flag accordingly
- Do not use `skyfield` or `rebound` in v0; keep dependencies minimal

### 7. score.py
**Inputs**: classified tracklets with orbital elements
**Process**:
- Compute `HazardAssessment` for each candidate:
  - `moid_au` from `orbit.py`
  - `estimated_diameter_m` from absolute magnitude H using geometric albedo assumption ($p_v = 0.14$ default)
  - `hazard_flag`: PHA candidate if MOID ≤ 0.05 AU AND $H \leq 22$
  - `alert_pathway` from ordered gate (see §Alert Protocol)
- Compute derived scores:
  - `discovery_priority`: combination of novelty, orbit quality, and PHA flag
  - `followup_value`: based on brightness, arc length, orbit uncertainty
  - `scientific_interest`: unusual orbital elements, extreme $a$ or $e$, short MOID

### 8. alert.py
**Inputs**: `ScoredNEO` objects
**Process**:
- Format MPC 80-column observation report for any `alert_pathway` ≥ `mpc_submission`
- Generate human-readable candidate summary
- For `nasa_pdco_notify`: generate structured alert package (see §Alert Protocol)
- Log all alert actions with timestamps and provenance

---

## Alert Protocol

This section defines the mandatory decision tree for external reporting. **No step may be skipped.**

```
Computed MOID ≤ 0.05 AU
AND orbit quality code ≥ 2
AND Tier 1 real_bogus_score ≥ 0.90
AND NOT matched to MPC known object
         │
         ▼
Step 1: Submit to MPC via standard report format
        (astroquery.mpc or direct HTTP POST to minorplanetcenter.net)
         │
         ▼
Step 2: Monitor NEOCP for independent confirmation
        (wait ≥ 24 hours or ≥ 2 independent observatory confirmations)
         │
         ▼
Step 3: If CNEOS Scout/Sentry assigns impact probability ≥ 0.01%:
        → Open GitHub Issue tagged [HAZARD-ALERT]
        → Generate report to:
            NASA PDCO: https://www.nasa.gov/planetarydefense/contact
            IAU CBAT:  https://www.cbat.eps.harvard.edu/
        → Do NOT publicly announce impact probability;
          defer all public communication to NASA/CNEOS
```

**Guardrails**:
- Never skip MPC submission and independent confirmation before Step 3
- Never quote an impact probability in any public output
- Never suppress a genuine alert out of uncertainty — report and let authorities assess
- Store full provenance (observations, orbit fit, MOID computation) with every alert

---

## ML Training Data

| Dataset | Source | Size | Use |
|---|---|---|---|
| ZTF real/bogus labels | Duev et al. (2019) / Broker APIs | ~100,000 alerts | Tier 1 + Tier 2 training |
| MPC confirmed NEO catalog | `astroquery.mpc` | ~35,000 objects | Positive labels |
| MPC MBA sample | `astroquery.mpc` | large | Negative labels for NEO classifier |
| ZTF NEO observation history | IRSA | varies | Tracklet sequence training |
| ATLAS detections of known NEOs | ATLAS server | varies | Tier 1 feature validation |

**Label quality note**: Use only MPC-numbered objects as high-confidence positives. Provisional designations may be reassigned and should be treated with lower weight.

---

## Scoring Model

### Hypotheses

| Symbol | Hypothesis | Prior |
|---|---|---|
| $H_\text{neo}$ | Genuine new NEO candidate | 0.05 |
| $H_\text{ko}$ | Known MPC object | 0.30 |
| $H_\text{mba}$ | Main-belt asteroid | 0.35 |
| $H_\text{art}$ | Instrumental artifact | 0.25 |
| $H_\text{other}$ | Other solar system body | 0.05 |

Priors are deliberately pessimistic about new NEOs (most moving objects are known MBAs or artifacts). Adjust priors for high-ecliptic-latitude fields where MBA contamination is lower.

### Log-Score Model

$$\ell_i = \log P(H_i) + \sum_k w_{ik}\,\phi_k(\mathbf{D})$$

$$p_i = \frac{\exp(\ell_i - \ell_{\max})}{\sum_j \exp(\ell_j - \ell_{\max})}$$

All features $\phi_k \in [0,1]$; missing features contribute 0 (neutral).

### Key Feature Weights (planet_candidate analogue → neo_candidate)

```
log_score_neo =
    log_prior_neo
    + 2.0 * real_bogus_score
    + 1.5 * arc_coverage_score
    + 1.5 * nights_observed_score
    + 1.2 * motion_consistency_score
    + 1.0 * orbit_quality_score
    - 2.5 * known_object_score
    - 2.0 * stellar_artifact_score
    - 1.5 * main_belt_consistency_score
```

---

## Quality Commands

```bash
# Lint
ruff check .
ruff check . --fix

# Type-check
python -m mypy src

# Tests
PYTHONPATH=src python -m pytest

# All three
ruff check . && python -m mypy src && PYTHONPATH=src python -m pytest
```

Live integration tests (require network access to ZTF/ATLAS/MPC) must be marked:

```python
@pytest.mark.integration_live
```

and excluded from CI.

---

## Guardrails

- Never output "confirmed NEO" for internally detected objects
- Never state or imply an impact probability without MPC/CNEOS confirmation
- Always expose artifact and known-object evidence alongside every candidate score
- Store scoring model version and observation provenance with every result
- Prefer conservative classifications; when uncertain, flag for human review
- The alert protocol is non-negotiable and must be followed in full

---

## Key Literature

- Bellm, Eric C., et al. "The Zwicky Transient Facility: System Overview, Performance, and First Results." *PASP*, vol. 131, 2019, p. 018002.
- Duev, Dmitry A., et al. "Real-bogus Classification for the Zwicky Transient Facility Using Deep Learning." *MNRAS*, vol. 489, no. 3, 2019, pp. 3582–3590.
- Lin, Hsing-Wen, et al. "Astronomical Image Time Series Classification Using CONVolutional Neural nETworks (ConvNet)." *AJ*, vol. 163, 2022, p. 154.
- Moeyens, Joachim, et al. "THOR: An Algorithm for Cadence-independent Asteroid Discovery." *AJ*, vol. 162, no. 4, 2021, p. 143.
- Ye, Quanzhi, et al. "Hundreds of New Near-Earth Asteroids Found with ZTF." *AJ*, vol. 159, no. 2, 2020, p. 70.
- Jedicke, Robert, et al. "Observational Selection Effects in Asteroid Surveys." *Asteroids III*, Univ. of Arizona Press, 2002, pp. 71–87.
- Mainzer, Amy, et al. "Initial Performance of the NEOWISE Reactivation Mission." *ApJ*, vol. 792, no. 1, 2014, p. 30.

---

## Current State (v0.20.0)

All 10 pipeline modules are complete. 949 tests passing (100% coverage). CI green on Python 3.11 & 3.12. Coverage threshold 100%. Background automation uses one unified manual CLI with top-level SQLite logs and auditable signoff readiness.

### Skills

| Script | Purpose |
|---|---|
| `Skills/smoke_test.py` | Happy-path check for all modules; exits 0 on success |
| `Skills/evaluate_calibration.py` | Brier/ECE evaluation for Platt and isotonic calibrators |
| `Skills/generate_training_labels.py` | Download MPC NEO + MBA catalog as training label CSV |
| `Skills/batch_score.py` | Score a list of tracklets from a JSON file; print ranked table |
| `Skills/run_pipeline.py` | Full end-to-end pipeline run |
| `Skills/injection_recovery.py` | Injection-recovery test: injects synthetic NEOs, measures detection/link/score rates |
| `Skills/check_mpc_known.py` | Cross-match candidate observations against MPC known object catalog |
| `Skills/visualize_tracklets.py` | Plot sky positions and light curves for a tracklet JSON file |
| `Skills/export_mpc_report.py` | Export MPC 80-column reports from a scored NEO JSON file |
| `Skills/benchmark_pipeline.py` | Time classify + score on N synthetic tracklets; print throughput table |
| `Skills/train_tier2_cnn.py` | Fine-tune CNN on labeled ZTF cutout CSV; saves `models/tier2_cnn.pt` |
| `Skills/train_tier3_transformer.py` | Train Transformer on MPC tracklet CSV; saves `models/tier3_transformer.pt` |
| `Skills/tune_linker.py` | Parametric sweep of `position_tolerance_arcsec` × `chi2_threshold` vs link/score rate |
| `Skills/background.py` | Unified background automation CLI with run, summary, detail, history, and signoff subcommands |
| `Skills/stress_test_high_motion.py` | Stress-test linker across 3 motion bins (1–10, 10–30, 30–60 arcsec/hr); saves results to `data/` |
| `Skills/build_cutout_dataset.py` | Convert ZTF alert JSON (base64 cutouts) to `.npz` + CSV index for Tier 2 CNN training |
| `Skills/build_sequence_dataset.py` | Convert tracklet JSON to flat token CSV for Tier 3 Transformer training |
| `Skills/validate_mpc_report.py` | Validate MPC 80-column observation report files; CLI with `--json` flag |
| `Skills/diagnose_pipeline.py` | Run each pipeline stage with synthetic data; report pass/fail per stage |
| `Skills/compare_baselines.py` | Compare two injection-recovery JSON baselines; exits 1 on regression |
| `Skills/simulate_survey.py` | Generate synthetic ZTF-like survey observations for a sky field |
| `Skills/export_ranked_table.py` | Export a ranked ScoredNEO table to CSV or HTML |
| `Skills/check_orbit_quality.py` | Check orbit quality and fit preliminary orbit for tracklets from JSON |
| `Skills/generate_obs_schedule.py` | Generate prioritized follow-up observation schedule with urgency tiers |
| `Skills/photometric_calibration.py` | Per-field photometric zero-point fit and magnitude correction |
| `Skills/export_mpc_bulk.py` | Bulk export MPC 80-column reports for a list of ScoredNEOs to a directory |
| `Skills/filter_candidates.py` | Filter scored NEO JSON by hazard flag, alert pathway, or minimum priority |
| `Skills/summarise_run.py` | Print or JSON-export a pipeline run summary from scored NEO JSON |
| `Skills/plot_sky_coverage.py` | RA/Dec scatter plot of tracklet positions colour-coded by hazard flag |
| `Skills/export_candidate_report.py` | Per-candidate plain-text reports from scored NEO JSON; `--split` writes one file per candidate |
| `Skills/tag_neo_class.py` | Batch-tag NEO class for tracklets or ScoredNEO dicts using `classify_neo_class` from orbit.py |
| `Skills/check_tisserand.py` | Batch-compute Tisserand parameter for tracklets/ScoredNEO dicts; flags T_J < threshold as comet-like |
| `Skills/export_followup_requests.py` | Generate NEOCP follow-up request files for candidates above priority threshold; supports `--obs-code` and `--out-dir` |
| `Skills/ephemeris_check.py` | Predict sky positions for tracklets at a given JD; observer-ready RA/Dec/dist table; `--jd` and `--json` flags |
| `Skills/flag_comet_candidates.py` | Combined Tisserand + eccentricity comet-candidate flag; `--threshold`, `--min-ecc`, `--json` flags |
| `Skills/compute_orbital_energy.py` | Batch orbital energy computation; bound/parabolic/hyperbolic label; `--json` flag |
| `Skills/assess_survey_coverage.py` | Survey field coverage report (area, limiting mag, source count, fields per night); `--json` flag |
| `Skills/grade_tracklets.py` | Batch-grade tracklets from JSON (A/B/C/D) using arc, nights, and astrometric RMS; `--json` flag |
| `Skills/query_mpc_observations.py` | Query MPC observation history for a designation; prints table or JSON |

### Docs

| File | Purpose |
|---|---|
| `docs/PIPELINE_SPEC.md` | Full stage-by-stage pipeline specification |
| `docs/SCORING_MODEL.md` | Bayesian scoring model: hypotheses, priors, feature weights |
| `docs/TRAINING_GUIDE.md` | Step-by-step ML training guide: Tier 1–3 training, calibration, injection-recovery |
| `docs/DATA_SOURCES.md` | External data sources: ZTF, ATLAS, MPC, JPL Horizons, Gaia DR3 |
| `docs/API_REFERENCE.md` | Public function signatures and schema field reference for all modules |
| `docs/BACKGROUND_SEARCH_AUTOMATION.md` | Implemented one-run background automation, SQLite logs, and scheduler notes |
| `docs/ORBIT_FITTING.md` | Technical reference for orbit fitting: Gauss's method, differential correction, MOID, Tisserand parameter |
| `docs/ALERT_PROTOCOL.md` | Technical reference for alert-pathway decision tree, gate conditions, MPC submission, NEOCP monitoring, NASA PDCO notification |
| `docs/CLASSIFICATION_GUIDE.md` | Technical reference for three-tier ML classification, morphology, ensemble stacking, calibration, and conservative classification policy |
| `docs/QUALITY_METRICS.md` | Reference for all pipeline quality metrics: detection, astrometric, photometric, orbital, calibration, and hazard scoring |

### Data

| File | Purpose |
|---|---|
| `data/sample_tracklets.json` | Two synthetic tracklets for testing batch Skills |
| `data/README.md` | Data directory documentation and format reference |
| `data/injection_recovery_baseline.json` | Injection-recovery results (n=50, seed=42): 100% detection, 62% link, 62% score |
| `data/injection_recovery_n200.json` | Injection-recovery results (n=200, seed=42): 100% detection, 100% link, 100% score |
| `data/stress_test_high_motion.json` | Stress-test results: 100% link rate across all three motion bins |
| `background/config.json` | Manual-first background automation configuration |
| `background/config.schema.json` | JSON Schema for manual-first background config |
| `background/targets.json` | Stable background automation fixture manifest |

### Coverage by Module (v0.13.0)

| Module | Coverage |
|---|---|
| `schemas.py` | 100% |
| `score.py` | 100% |
| `calibration.py` | 100% |
| `link.py` | 100% |
| `alert.py` | 100% |
| `preprocess.py` | 100% |
| `orbit.py` | 100% |
| `detect.py` | 100% |
| `classify.py` | 100% |
| `fetch.py` | 100% (ztfquery, ATLAS, astroquery.mpc, jplhorizons all mocked) |

### What Is Not Yet Built (Milestones 4–7)

| Milestone | Description |
|---|---|
| 4 | Live ZTF/ATLAS data integration (requires network + API tokens) |
| 5 | CNN image classifier Tier 2 (requires GPU + labeled cutouts) |
| 6 | Transformer tracklet model Tier 3 (requires multi-night training set) |
| 7 | Ensemble calibration + injection-recovery testing |

### Immediate Next Steps

- Collect labeled training data via `Skills/generate_training_labels.py`
- Integrate live ZTF alert stream (Milestone 4)
- Train and evaluate Tier 2 CNN on real cutouts (Milestone 5)

### Key Changes in v0.20.0

- `orbit.py`: added `compute_phase_angle(elements, target_jd)` — Sun–target–observer phase angle via law of cosines; returns NaN on degenerate geometry.
- `detect.py`: added `compute_psf_fwhm(obs)` — PSF FWHM in arcsec from 2D Gaussian moment fit; returns None if no cutout or degenerate.
- `link.py`: added `compute_tracklet_grade(tracklet)` — A/B/C/D quality grade from arc length, nights observed, and astrometric RMS.
- `classify.py`: added `summarize_classifications(neos)` — aggregate summary dict: total, dominant_hypothesis_counts, mean_entropy_bits, mean_real_bogus_score, pha_candidate_count.
- `score.py`: added `compute_novelty_score(neo, catalog_elements)` — orbital distance from nearest known NEO in (a, e, i) space; 1.0 = fully novel.
- `alert.py`: added `generate_observation_request(neo, obs_code)` — structured NEOCP follow-up request with urgency tier (URGENT/HIGH/MEDIUM/ROUTINE) and guardrail.
- `fetch.py`: added `fetch_mpc_observations(designation)` — query MPC observation history for a designation; caches to disk; returns list[Observation].
- `preprocess.py`: added `compute_astrometric_scatter(observations)` — RMS of linear RA/Dec fit residuals in arcsec; None for <2 obs or identical JDs.
- `schemas.py`: added `PipelineConfig` — frozen Pydantic model capturing sky position, time window, survey selection, and detection thresholds for a pipeline run.
- `calibration.py`: added `compute_log_loss(probs, labels, eps)` — binary cross-entropy with clipping; returns 0.0 for empty inputs.
- `Skills/grade_tracklets.py`: new — batch-grade tracklets from JSON; `--json` flag.
- `Skills/query_mpc_observations.py`: new — query MPC observation history for a designation; `--json` flag.
- `docs/QUALITY_METRICS.md`: new — comprehensive quality metrics reference for all pipeline stages.
- 69 new tests (949 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.20.0.

### Key Changes in v0.19.0

- `orbit.py`: added `orbital_energy(elements)` — specific orbital energy in AU²/yr²; negative = bound, inf for a ≤ 0.
- `detect.py`: added `compute_trail_length(obs)` — trail length in arcsec from difference-image second moments.
- `link.py`: added `assess_link_confidence(tracklet)` — [0, 1] confidence from linear-fit RMS residual vs 10 arcsec reference.
- `classify.py`: added `batch_morphology(tracklet)` — modal_class, class_counts, streak_fraction across all observations.
- `score.py`: added `compute_impact_energy(diameter_m, velocity_km_s, density_kg_m3)` — kinetic impact energy in megatons TNT.
- `alert.py`: added `format_alert_summary(neos, max_rows)` — plain-text ranked summary table with hazard flag, pathway, MOID, priority.
- `fetch.py`: added `count_known_objects_in_field(ra_deg, dec_deg, radius_deg)` — count MPC known objects in a circular field; returns 0 on failure.
- `preprocess.py`: added `detect_bad_pixels(obs, sigma_threshold)` — MAD-based sigma clipping; returns list of (row, col) tuples.
- `schemas.py`: added `SurveyField` — frozen Pydantic model for survey field metadata (field_id, ra_deg, dec_deg, radius_deg, limiting_mag, n_sources, jd).
- `calibration.py`: added `cross_validate_calibration(probs, labels, n_folds, metric)` — K-fold CV returning (mean, std). Fixed `bootstrap_confidence_interval` empty-guard for numpy arrays.
- `Skills/compute_orbital_energy.py`: new — batch orbital energy CLI; `--json` flag.
- `Skills/assess_survey_coverage.py`: new — survey field coverage report; `--json` flag.
- `docs/CLASSIFICATION_GUIDE.md`: new — three-tier ML classification reference.
- 81 new tests (880 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.19.0.

### Key Changes in v0.18.0

- `orbit.py`: added `ephemeris_uncertainty(elements, target_jd)` — sky-plane uncertainty propagated from quality code; scales with propagation time.
- `detect.py`: added `cluster_detections(observations, radius_arcsec)` — greedy spatial clustering; returns list of Observation tuples.
- `link.py`: added `compute_arc_statistics(tracklet)` — summary dict: n_observations, n_nights, arc_days, mean_motion_arcsec_hr, motion_pa_std_deg.
- `classify.py`: added `classify_morphology(obs)` — source morphology from image moments: 'point_source', 'extended', or 'streak'.
- `score.py`: added `absolute_magnitude_from_diameter(diameter_m, albedo)` — H from diameter and albedo; returns inf for zero/negative inputs. Fixed formula.
- `alert.py`: added `format_discovery_circular(neo)` — IAU CBET-style discovery circular; does not transmit.
- `fetch.py`: added `build_observation_window(ra_deg, dec_deg, ...)` — validated ObservationWindow factory with ValueError for bad inputs.
- `preprocess.py`: added `compute_source_snr(obs)` — peak-to-background SNR from difference-image cutout.
- `schemas.py`: added `CloseApproachEvent` — frozen model for a close approach event.
- `calibration.py`: added `bootstrap_confidence_interval(probs, labels, n_bootstrap, metric)` — bootstrap 95% CI for Brier or ECE.
- `Skills/ephemeris_check.py`: new — ephemeris prediction table at user-specified JD.
- `Skills/flag_comet_candidates.py`: new — combined T_J + eccentricity comet-candidate flag.
- `docs/ALERT_PROTOCOL.md`: new — alert pathway technical reference.
- 70 new tests (799 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.18.0.

### Key Changes in v0.17.0

- `orbit.py`: added `batch_predict_ephemeris(elements_list, target_jd)` — batch sky-position prediction; per-element error isolation.
- `orbit.py`: added `resonance_check(elements, tolerance)` — mean-motion resonance detection with Jupiter; checks T_J/T_asteroid ratio against p:q pairs; returns resonance label or None.
- `detect.py`: added `compute_streak_metric(obs)` — streak severity from difference-image second moments; [0, 1]; handles degenerate zero-eigenvalue (perfectly elongated) case.
- `link.py`: added `split_tracklet(tracklet, split_jd)` — split tracklet at a JD boundary into two sub-tracklets; raises ValueError if either part has fewer than 2 observations.
- `classify.py`: added `dominant_hypothesis(posterior)` — return (name, probability) for highest-probability class; ("unknown", 0.0) for all-zero posterior.
- `score.py`: added `close_approach_candidates(neos, max_moid_au)` — filter by MOID ≤ threshold; None MOID excluded.
- `alert.py`: added `ready_for_submission(neo)` — boolean gate for all alert-protocol preconditions; returns (bool, unmet list); fixed field name orbit_quality_code → quality_code.
- `fetch.py`: added `filter_alerts_by_motion(alerts, min_rate, max_rate)` — filter by ssdistnr-based motion proxy; observations without ssdistnr pass through.
- `preprocess.py`: added `estimate_source_density(observations, field_radius_deg)` — source count per square degree via great-circle centroid.
- `schemas.py`: added `TrackletSummary` — lightweight frozen model for tracklet display/export.
- `Skills/check_tisserand.py`: new — batch Tisserand parameter check; comet-like flag; `--threshold` and `--json` CLI flags.
- `Skills/export_followup_requests.py`: new — NEOCP follow-up request generator; `--min-priority`, `--out-dir`, `--obs-code`, `--summary` CLI flags.
- `docs/ORBIT_FITTING.md`: new — orbit fitting technical reference.
- 146 new tests (729 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.17.0.

### Key Changes in v0.16.0

- `orbit.py`: added `classify_neo_class(elements)` — derive NEO dynamical class from orbital elements.
- `orbit.py`: added `tisserand_parameter(elements)` — Tisserand parameter relative to Jupiter; T_J < 3 distinguishes comets.
- `detect.py`: added `filter_by_real_bogus(result, threshold)` — filter DetectResult by max real/bogus score.
- `link.py`: added `deduplicate_tracklets(tracklets)` — remove tracklets with ≥ 50% overlapping obs_ids; longer arc wins.
- `score.py`: added `pha_candidates(neos)` — filter to PHA candidates only.
- `score.py`: added `compute_statistics(neos)` — aggregate NEOStatistics (counts, priority, class distribution).
- `classify.py`: added `posterior_entropy(posterior)` — Shannon entropy of NEOPosterior in bits.
- `alert.py`: added `format_neocp_report(neo, obs_code)` — plain-text NEOCP follow-up request with guardrails.
- `fetch.py`: added `merge_survey_alerts(results)` — merge and deduplicate multiple FetchResults.
- `preprocess.py`: added `compute_color_index(obs1, obs2)` — magnitude difference for observations in different bands.
- `schemas.py`: added `NEOStatistics` — frozen Pydantic model for aggregate pipeline statistics.
- `Skills/export_candidate_report.py`: new — per-candidate plain-text reports; `--split` writes one file per candidate.
- `Skills/tag_neo_class.py`: new — batch-tag NEO class using `classify_neo_class`.
- `docs/TRAINING_GUIDE.md`: new — step-by-step ML training guide (Tier 1–3, calibration, injection-recovery).
- 77 new tests; 660 total; 100% coverage maintained.
- Version bumped to 0.16.0.

### Key Changes in v0.15.0

- `orbit.py`: added `compute_orbital_period` — Kepler's third law; T = 365.25 × √(a³) days.
- `link.py`: added `filter_high_motion(tracklets, min_rate_arcsec_hr)` — filter by motion rate threshold (default 10 arcsec/hr).
- `score.py`: added `followup_priority_table(neos)` — flat ranked table dict list sorted by discovery priority.
- `classify.py`: added `batch_explain(tracklets)` — batch version of `explain_classification`.
- `alert.py`: added `alert_summary_table(neos)` — flat per-NEO alert summary with ready_to_submit flag.
- `fetch.py`: added `summarise_fetch_result(result)` — summary dict of a FetchResult.
- `preprocess.py`: added `flag_saturated_sources(result, saturation_mag)` — return obs_ids of likely saturated sources.
- `schemas.py`: added `CandidateSummary` — lightweight frozen Pydantic model for NEO display/export.
- `Skills/filter_candidates.py`: new — filter scored NEO JSON by hazard flag, pathway, or priority.
- `Skills/summarise_run.py`: new — human-readable or JSON pipeline run summary.
- `Skills/plot_sky_coverage.py`: new — RA/Dec scatter plot colour-coded by hazard flag (matplotlib).
- `docs/API_REFERENCE.md`: updated with all v0.14.0 and v0.15.0 APIs.
- 55 new tests; 583 total; 100% coverage maintained.
- Version bumped to 0.15.0.

### Key Changes in v0.14.0

- `orbit.py`: added `close_approach_table` — tabulate geocentric distance over a time window.
- `link.py`: added `estimate_motion_uncertainty` — rate and PA error from linear fit residuals.
- `score.py`: added `discovery_report` — comprehensive nested summary dict for human review.
- `classify.py`: added `explain_classification` — structured classification breakdown with Tier 1 importances. Fixed Pydantic v2.11 `model_fields` deprecation.
- `alert.py`: added `draft_mpc_submission` — complete MPC submission bundle with guardrail cover letter.
- `schemas.py`: added `ObservationWindow` — frozen typed model for sky/time search queries.
- `fetch.py`: added `estimate_limiting_magnitude` — survey depth proxy from faint-end magnitude tail.
- `preprocess.py`: added `quality_summary` — per-field PSF quality, background RMS, and elongation statistics.
- `detect.py`: added `streak_candidates` — filter `DetectResult` for streak/trail detections only.
- `background.py`: added `audit_report` — consolidated cross-log audit report.
- `Skills/generate_obs_schedule.py`: prioritized follow-up observation schedule with urgency tiers.
- `Skills/photometric_calibration.py`: per-field photometric zero-point fit via Gaia DR3.
- `Skills/export_mpc_bulk.py`: bulk MPC 80-column report export with manifest.
- `docs/SCORING_MODEL.md`: updated with ranking, discovery report, motion uncertainty, close-approach table, and photometric calibration.
- 63 new tests; 528 total; 100% coverage maintained.
- Version bumped to 0.14.0.

### Key Changes in v0.13.0

- `fetch.py`: added `fetch_batch` — fetch multiple sky positions in one call.
- `preprocess.py`: added `preprocess_batch` — batch preprocessing from `FetchResult` list.
- `detect.py`: added `detect_batch` — batch detection from `PreprocessResult` list.
- `link.py`: added `merge_tracklets` — merge two tracklets into a longer deduplicated arc.
- `orbit.py`: added `propagate_orbit` (Keplerian propagation), `predict_ephemeris` (geocentric RA/Dec at target JD).
- `score.py`: added `rank_candidates` — sort `ScoredNEO` list by priority with PHA tier.
- `alert.py`: added `generate_alert_package` — bundle all alert artifacts into one dict.
- `schemas.py`: added `PipelineResult` — immutable top-level pipeline run container.
- `Skills/simulate_survey.py`: synthetic ZTF-like survey generator.
- `Skills/export_ranked_table.py`: CSV/HTML ranked table export.
- `Skills/check_orbit_quality.py`: orbit quality CLI for tracklet JSON.
- `tests/conftest.py`: extended with `build_raw_candidate`, `build_scored_neo`, and `scored_neo`/`raw_candidate` fixtures.
- `docs/PIPELINE_SPEC.md`: updated with all v0.13.0 APIs and `PipelineResult` container.
- 54 new tests; 465 total; 100% coverage maintained.
- Version bumped to 0.13.0.

### Key Changes in v0.12.0

- `link.py`: added `_is_satellite_trail` — rejects purely E-W or N-S fast-moving pairs (≥30 arcsec/hr) as satellite/debris trails.
- `classify.py`: added `classify_batch` and `get_tier1_feature_importances` public APIs.
- `orbit.py`: added `arc_quality_report` — returns quality dict with codes 1–4.
- `score.py`: added `score_batch`; `ScoringMetadata.close_approach_au` now populated from MOID when orbit quality ≥ 2.
- `schemas.py`: added `close_approach_au: float | None = None` to `ScoringMetadata`.
- `alert.py`: added `format_mpc_json` and `batch_process_alerts` public APIs.
- `Skills/validate_mpc_report.py`: new — validate MPC 80-column report format.
- `Skills/diagnose_pipeline.py`: new — per-stage diagnostic runner with synthetic data.
- `Skills/compare_baselines.py`: new — compare injection-recovery baselines; regression detection.
- `docs/API_REFERENCE.md`: updated with all v0.12.0 public APIs.
- 34 new tests; 411 total; 100% coverage maintained.
- Version bumped to 0.12.0.

### Key Changes in v0.11.0

- `link.py`: fixed chi² error proxy (`max(mag_err * 0.1, 0.1)` → `max(mag_err, 0.5)`) — link rate 62% → 100%
- `link.py`: added `_predict_from_arc` (quadratic polyfit for ≥3 obs, linear fallback) for more accurate position prediction
- `fetch.py`: added `force_refresh` flag to bypass on-disk cache; ATLAS token now falls back to `ATLAS_TOKEN` env var
- `alert.py`: added public `monitor_neocp` with injectable sleep for NEOCP polling loop
- `classify.py`: added `retrain_tier1` and `retrain_stacker` public APIs for incremental retraining
- `Skills/run_pipeline.py`: added `--atlas-token`, `--force-refresh`, `--neocp-timeout-hours`, `--neocp-poll-interval` flags
- `Skills/stress_test_high_motion.py`: stress-test linker across 3 motion bins; all bins 100%
- `Skills/build_cutout_dataset.py`: build `.npz` + CSV index from ZTF alert JSON for Tier 2 training
- `Skills/build_sequence_dataset.py`: build flat token CSV from tracklet JSON for Tier 3 training
- `Skills/train_tier2_cnn.py`: updated to read `.npz` cutout files from `cutout_path` column
- `Skills/train_tier3_transformer.py`: updated to read flat `tok_i_j` columns
- `Skills/smoke_test.py`: added `monitor_neocp` and `retrain` smoke tests
- `Skills/check_mpc_known.py`: added `--neocp` CLI flag and `check_neocp` function
- `data/injection_recovery_n200.json`: n=200 baseline: 100% detection, link, score
- `data/stress_test_high_motion.json`: stress-test results
- CHANGELOG.md: full Keep-a-Changelog history added (v0.1.0–v0.11.0)
- 31 new tests; 377 total; 100% coverage maintained
- Version bumped to 0.11.0.

### Key Changes in v0.10.0

- Removed deprecated background wrapper scripts; `Skills/background.py` is the single supported CLI.
- Added versioned background target manifest support and `background/config.schema.json`.
- Added run detail, target history, signoff readiness, and unsigned follow-up audit views.
- Added CLI and manifest regression tests; 346 total; 100% coverage.
- Version bumped to 0.10.0.

### Key Changes in v0.9.0

- `link.py`: fixed prediction bug — `_predict_position` now uses `obs_c.jd` instead of integer night key; link rate 2% → 62%
- `Skills/tune_linker.py`: parametric sweep of tolerance × chi² vs link/score rate
- 4 new tests (regression test for prediction fix + arc_below_min_obs + tune_linker smoke); 328 total; 100% coverage
- Injection-recovery baseline updated: 62% link rate (n=50, seed=42)
- Version bumped to 0.9.0

### Key Changes in v0.8.0

- `classify.py`: added `_build_ensemble` (sklearn LogisticRegression meta-learner) + `ensemble_predict` public API
- `Skills/injection_recovery.py`: added `--json PATH` flag to save results
- Baseline injection-recovery run saved to `data/injection_recovery_baseline.json`
- 8 new tests; 324 total; 100% coverage maintained
- Version bumped to 0.8.0

### Key Changes in v0.7.0

- fetch.py: 75% → 100% via mocks for ztfquery, ATLAS network, astroquery.mpc, jplhorizons
- CI coverage gate raised from 95% → 100%; actual coverage 100.00%
- New Skills: `benchmark_pipeline.py`, `train_tier2_cnn.py`, `train_tier3_transformer.py`
- New infra: `.github/ISSUE_TEMPLATE/` (bug + feature request templates), `models/` directory
- Version bumped to 0.7.0 in `pyproject.toml` and `src/__init__.py`

### Key Changes in v0.6.0

- torch installed; CNN (Tier 2) and Transformer (Tier 3) paths fully tested (100% classify.py coverage)
- Alert module: `process_alert` accepts `cneos_assessment` parameter for PDCO path testing
- Coverage gate raised from 85% → 95% in CI; actual coverage 97.44%
- 40 new tests added across orbit, detect, preprocess, calibration, classify, alert modules
- Version bumped to 0.6.0 in `pyproject.toml` and `src/__init__.py`
