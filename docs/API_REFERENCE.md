# API Reference — NEO Detection Pipeline

Public interfaces for each pipeline module. All functions accept and return typed, immutable objects defined in `schemas.py`.

---

## schemas.py

Core data models. All use `ConfigDict(frozen=True)`.

### `Observation`
Single photometric detection.

| Field | Type | Notes |
|---|---|---|
| `obs_id` | `str` | Unique identifier |
| `ra_deg` | `float` | Right ascension, degrees |
| `dec_deg` | `float` | Declination, degrees |
| `jd` | `float` | Julian date |
| `mag` | `float \| None` | Apparent magnitude |
| `mag_err` | `float \| None` | Magnitude uncertainty |
| `filter_band` | `str` | Photometric band (g/r/i/o/c) |
| `mission` | `Mission` | Survey source |
| `real_bogus` | `float \| None` | Real/bogus score [0, 1] |
| `deep_real_bogus` | `float \| None` | Deep-learning RB score [0, 1] |

### `Tracklet`
Linked sequence of observations for one moving object.

| Field | Type | Notes |
|---|---|---|
| `object_id` | `str` | Pipeline-assigned identifier |
| `observations` | `tuple[Observation, ...]` | Sorted by JD |
| `arc_days` | `float` | Total arc length in days |
| `motion_rate_arcsec_per_hour` | `float` | Apparent motion rate |
| `motion_pa_degrees` | `float` | Position angle of motion |

### `CandidateFeatures`
All scores are `float \| None`, bounded [0, 1]. `None` means unavailable; contributes 0 (neutral) to scoring.

| Field | Purpose |
|---|---|
| `real_bogus_score` | Detection quality |
| `motion_consistency_score` | Linear motion fit quality |
| `arc_coverage_score` | Arc length relative to 30-day baseline |
| `nights_observed_score` | Number of nights observed |
| `brightness_score` | Proxy for object size |
| `color_score` | g−r color index |
| `lightcurve_variability_score` | Photometric variability |
| `orbit_quality_score` | Orbit determination quality |
| `moid_score` | 1 = MOID ≤ 0.05 AU |
| `known_object_score` | 1 = matches MPC catalog |

### `NEOPosterior`
Posterior probability over classification hypotheses. Values sum to 1.

| Field | Hypothesis |
|---|---|
| `neo_candidate` | Genuine new NEO |
| `known_object` | Matches MPC catalog |
| `main_belt_asteroid` | MBA on unusual orbit |
| `stellar_artifact` | Cosmic ray / satellite / artifact |
| `other_solar_system` | Comet, TNO, etc. |

### `HazardAssessment`

| Field | Type | Notes |
|---|---|---|
| `hazard_flag` | `HazardFlag` | `pha_candidate`, `close_approach`, `nominal`, `unknown` |
| `moid_au` | `float \| None` | Minimum Orbit Intersection Distance |
| `estimated_diameter_m` | `float \| None` | From H magnitude, albedo=0.14 |
| `alert_pathway` | `AlertPathway` | Determines external reporting action |

---

## fetch.py

```python
def fetch(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    jd_start: float,
    jd_end: float,
    surveys: tuple[str, ...] = ("ZTF",),
    force_refresh: bool = False,
) -> FetchResult
```

Query survey alert streams for observations in the specified sky region and time range. Set `force_refresh=True` to bypass the on-disk cache and re-download. ATLAS authentication falls back to the `ATLAS_TOKEN` environment variable when no token is passed.

**Returns** `FetchResult(alerts: tuple[Observation, ...], provenance: FetchProvenance)`

---

## preprocess.py

```python
def preprocess(alerts: tuple[Observation, ...]) -> PreprocessResult
```

Validate, normalize, and astrometrically correct raw alerts.

**Returns** `PreprocessResult(sources: tuple[Observation, ...], provenance: PreprocessProvenance)`

---

## detect.py

```python
def detect(
    sources: tuple[Observation, ...],
    rb_threshold: float = 0.65,
) -> DetectResult
```

Filter on real/bogus score, identify moving sources, cross-match against MPC catalog.

**Returns** `DetectResult(candidates: tuple[RawCandidate, ...], known_matches: tuple[KnownMatch, ...])`

---

## link.py

```python
def link(
    candidates: tuple[RawCandidate, ...],
    min_nights: int = 3,
    min_observations: int = 6,
    position_tolerance_arcsec: float = 10.0,
    max_rate_arcsec_per_hr: float = 60.0,
) -> LinkResult
```

Link single-night detections into multi-night tracklets using linear motion propagation.

**Returns** `LinkResult(tracklets: tuple[Tracklet, ...], provenance: LinkProvenance)`

**Notes**:
- Requires ≥`min_nights` distinct nights and ≥`min_observations` total detections.
- Motion rate gate: 0.01–`max_rate_arcsec_per_hr` arcsec/hr between seed nights.
- Seed pairs more than 30 days apart are skipped.
- Candidate pairs exhibiting purely E-W or N-S linear motion at rate ≥ 30 arcsec/hr are rejected as probable satellite trails (`_is_satellite_trail` filter).

---

## classify.py

```python
def classify(tracklet: Tracklet) -> tuple[CandidateFeatures, NEOPosterior]
```

Three-tier classification: XGBoost (Tier 1) → CNN on image triplets (Tier 2) → Transformer on sequences (Tier 3).

```python
def extract_features(tracklet: Tracklet) -> CandidateFeatures
```

Extract tabular feature vector from a tracklet (no ML inference).

```python
def classify_batch(
    tracklets: list[Tracklet],
    xgb_model=None,
    cnn_model=None,
    transformer_model=None,
) -> list[tuple[CandidateFeatures, NEOPosterior]]
```

Classify a list of tracklets in one call, loading models once. Returns one `(features, posterior)` pair per tracklet in the same order.

```python
def get_tier1_feature_importances(model_path: str | Path) -> dict[str, float] | None
```

Load a saved XGBoost model and return normalised gain-based feature importances. Returns `None` if the model cannot be loaded.

```python
def retrain_tier1(csv_path: str | Path, model_path: str | Path) -> dict
```

Retrain the XGBoost Tier 1 classifier from a labelled CSV. Saves the model to `model_path` and returns a JSON-serialisable training report.

```python
def retrain_stacker(
    tier1_outputs: list[float],
    labels: list[int],
    model_path: str | Path,
) -> dict
```

Retrain the logistic-regression stacking meta-learner from Tier 1 probabilities and binary labels. Saves coefficients to `model_path` as JSON and returns a report.

---

## orbit.py

```python
def fit_orbit(tracklet: Tracklet) -> OrbitalElements | None
```

Fit preliminary orbit via Gauss's method with differential correction. Returns `None` for arcs too short for reliable determination.

```python
def compute_moid(elements: OrbitalElements) -> float | None
```

Compute Minimum Orbit Intersection Distance relative to Earth's orbit. Returns `None` when orbit quality is too low.

```python
def arc_quality_report(tracklet: Tracklet) -> dict
```

Return a quality summary for the tracklet arc. Fields:

| Key | Type | Notes |
|---|---|---|
| `arc_days` | `float` | Total arc length |
| `n_observations` | `int` | Total observation count |
| `n_nights` | `int` | Number of distinct nights |
| `quality_code` | `int` | 1 = < 1 day; 2 = multi-night; 3 = ≥ 7 days; 4 = ≥ 30 days |
| `arc_warning` | `str \| None` | Human-readable caution for short arcs |
| `recommended_action` | `str` | Suggested follow-up step |

---

## score.py

```python
def score(
    tracklet: Tracklet,
    features: CandidateFeatures,
    posterior: NEOPosterior,
    orbital: OrbitalElements | None,
) -> ScoredNEO
```

Compute hazard assessment, discovery priority, and alert pathway for a classified tracklet.

**Hazard flag logic**:
- `pha_candidate`: MOID ≤ 0.05 AU AND H ≤ 22.0 AND orbit quality ≥ 2
- `close_approach`: MOID ≤ 0.15 AU (but not PHA criteria)
- `nominal`: does not meet close-approach criteria
- `unknown`: MOID unavailable or orbit quality < 2

`ScoringMetadata.close_approach_au` is populated with the MOID value when orbit quality ≥ 2; otherwise `None`.

```python
def score_batch(
    items: list[tuple[Tracklet, CandidateFeatures, NEOPosterior, OrbitalElements | None]],
    pipeline_run_id: str = "",
) -> list[ScoredNEO]
```

Score a list of classified tracklets in one call. Returns one `ScoredNEO` per item in the same order. Shares the same pipeline-run ID across all results.

---

## alert.py

```python
def process_alert(neo: ScoredNEO, dry_run: bool = True) -> dict[str, Any]
```

Execute the alert protocol for a scored NEO candidate. In `dry_run=True` mode, all external submissions are simulated and logged locally.

```python
def format_mpc_report(neo: ScoredNEO) -> str
```

Format all observations in MPC 80-column format with header lines.

```python
def format_mpc_observation(obs: Observation, designation: str, is_discovery: bool = False) -> str
```

Format a single observation as one 80-character MPC line.

```python
def format_mpc_json(neo: ScoredNEO, obs_code: str = "500") -> dict
```

Return a MPC JSON submission dict. Fields: `type`, `provId`, `submissions` (list of observation dicts with the discovery observation marked `"remarks": "discovery"`), `moid_au`, `neo_class`, `hazard_flag`.

```python
def batch_process_alerts(
    neos: list[ScoredNEO],
    dry_run: bool = True,
    mpc_obs_code: str = "500",
) -> list[dict]
```

Process a list of `ScoredNEO` objects through the alert protocol. Returns one result dict per item. Per-item exceptions are caught and recorded as `{"error": ...}` entries.

```python
def monitor_neocp(
    object_id: str,
    max_wait_hr: float = 48.0,
    poll_interval_hr: float = 1.0,
    _sleep_fn=None,
) -> dict
```

Blocking NEOCP poll loop. Checks the MPC NEOCP page for `object_id` at `poll_interval_hr` intervals up to `max_wait_hr`. Returns `{"confirmed": bool, "elapsed_hr": float, "confirmations": int}`. Use `_sleep_fn` to inject a no-op in tests.

```python
def summarise(neo: ScoredNEO) -> str
```

Generate a human-readable candidate summary. Never asserts impact probability.

---

## calibration.py

```python
def calibrate_platt(
    scores: np.ndarray,
    labels: np.ndarray,
) -> PlattCalibrator
```

Fit a Platt (logistic) calibrator on training scores and binary labels.

```python
def calibrate_isotonic(
    scores: np.ndarray,
    labels: np.ndarray,
) -> IsotonicCalibrator
```

Fit an isotonic regression calibrator (PAVA algorithm).

Both calibrators expose `.predict(scores: np.ndarray) -> np.ndarray` returning calibrated probabilities in [0, 1].

---

## background.py

```python
def background_run_once(
    input_path: Path | None = None,
    db_path: Path | None = None,
    report_dir: Path | None = None,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> BackgroundRunResult
```

Execute exactly one offline background-search cycle, write one row to the
top-level SQLite run ledger, write exactly one reviewed or needs-follow-up
outcome row, and return the structured result.

```python
def ledger_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def reviewed_log_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def needs_follow_up_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def target_priority_summary(...) -> dict[str, Any]
def follow_up_test_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def submission_recommendation_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def validation_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def record_human_signoff(...) -> HumanSignoffEntry
def human_signoff_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def run_detail(run_id: str, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def target_history(target_id: str, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def signoff_readiness_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
```

Summarize the SQLite background logs, target priorities, follow-up tests,
recommendations, human signoffs, report readiness, and log invariants for
manual review. The supported command-line entrypoint is `Skills/background.py`
with subcommands; deprecated one-file wrappers have been removed.

Default background log path:

```text
Logs/background.sqlite
```

The background automation is fixture-only and manual-first by default. It never
submits or contacts external destinations.

---

## Alert Pathway Decision Tree

```
neo_candidate probability ≥ 0.5
AND real_bogus_score ≥ 0.90
AND orbit_quality_code ≥ 2
AND MOID ≤ 0.05 AU
AND NOT known_object
         │
         ├── known_object_score ≥ 0.8  →  known_object
         ├── real_bogus_score < 0.90   →  internal_candidate
         ├── orbit_quality < 2         →  internal_candidate
         ├── MOID > 0.05 AU            →  internal_candidate
         └── all gates passed          →  mpc_submission
```

PDCO notification (`nasa_pdco_notify`) requires independent MPC confirmation
and CNEOS Scout/Sentry impact probability ≥ 0.01%. Never triggered autonomously.
