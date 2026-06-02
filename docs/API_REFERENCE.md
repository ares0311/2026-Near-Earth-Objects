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
def internal_follow_up_disposition_summary(
    db_path: Path = DEFAULT_DB_PATH,
    required_approval_count: int = 1,
) -> dict[str, Any]
def target_priority_summary(...) -> dict[str, Any]
def follow_up_test_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def submission_recommendation_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def validation_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def background_schema_status_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def background_schema_migration_preview(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def background_schema_operations_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def background_operator_next_action_summary(
    config_path: Path = DEFAULT_CONFIG_PATH,
    db_path: Path = DEFAULT_DB_PATH,
    input_path: Path = DEFAULT_INPUT_PATH,
) -> dict[str, Any]
def migrate_background_log_db(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def background_blueprint_compliance_summary(
    db_path: Path = DEFAULT_DB_PATH,
    input_path: Path = DEFAULT_INPUT_PATH,
) -> dict[str, Any]
def record_blueprint_compliance_summary(
    db_path: Path = DEFAULT_DB_PATH,
    input_path: Path = DEFAULT_INPUT_PATH,
) -> dict[str, Any]
def blueprint_compliance_log_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def background_operations_snapshot(
    config_path: Path = DEFAULT_CONFIG_PATH,
    db_path: Path = DEFAULT_DB_PATH,
    input_path: Path = DEFAULT_INPUT_PATH,
) -> dict[str, Any]
def record_background_operations_snapshot(
    config_path: Path = DEFAULT_CONFIG_PATH,
    db_path: Path = DEFAULT_DB_PATH,
    input_path: Path = DEFAULT_INPUT_PATH,
) -> dict[str, Any]
def background_operations_snapshot_log_summary(
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]
def record_human_signoff(...) -> HumanSignoffEntry
def human_signoff_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def run_detail(run_id: str, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def target_history(target_id: str, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def signoff_readiness_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def signoff_packet(run_id: str, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def latest_unsigned_signoff_packet(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def write_signoff_packet(
    run_id: str,
    db_path: Path = DEFAULT_DB_PATH,
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> dict[str, Any]
def record_signoff_packet(
    run_id: str,
    db_path: Path = DEFAULT_DB_PATH,
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> dict[str, Any]
def signoff_packet_log_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def record_signoff_from_packet(
    packet_id: str,
    reviewer: str,
    decision: SignoffDecision,
    scope: str,
    notes: str = "",
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]
def signoff_packet_decision_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def signoff_packet_decision_readiness(
    db_path: Path = DEFAULT_DB_PATH,
    required_approval_count: int = 1,
) -> dict[str, Any]
def latest_undecided_signoff_packet(
    db_path: Path = DEFAULT_DB_PATH,
    required_approval_count: int = 1,
) -> dict[str, Any]
def automation_readiness_summary(config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]
def record_automation_readiness(
    config_path: Path = DEFAULT_CONFIG_PATH,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]
def automation_readiness_log_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def live_policy_contract_summary(config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]
def live_provider_capabilities() -> tuple[dict[str, Any], ...]
def live_provider_readiness(config_path: Path = DEFAULT_CONFIG_PATH) -> tuple[dict[str, Any], ...]
def live_credential_inventory(config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]
def write_live_credential_inventory_report(
    config_path: Path = DEFAULT_CONFIG_PATH,
    report_path: Path = DEFAULT_REPORT_DIR / "credential_inventory_latest.json",
) -> dict[str, Any]
def live_dry_run_approval_bundle(config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]
def record_live_dry_run_approval_bundle(
    config_path: Path = DEFAULT_CONFIG_PATH,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]
def live_dry_run_approval_bundle_log_summary(
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]
def live_dry_run_operator_handoff(config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]
def write_live_dry_run_operator_handoff(
    config_path: Path = DEFAULT_CONFIG_PATH,
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> dict[str, Any]
def record_live_dry_run_operator_handoff(
    config_path: Path = DEFAULT_CONFIG_PATH,
    db_path: Path = DEFAULT_DB_PATH,
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> dict[str, Any]
def live_dry_run_operator_handoff_log_summary(
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]
def live_dry_run_plan(config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]
def record_live_dry_run_plan(
    config_path: Path = DEFAULT_CONFIG_PATH,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]
def live_dry_run_plan_log_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
class LiveDryRunProvider(Protocol):
    survey: str
    def execute(self, query: Mapping[str, Any]) -> Mapping[str, Any]: ...

class MockLiveDryRunProvider:
    def __init__(self, survey: str) -> None: ...
    def execute(self, query: Mapping[str, Any]) -> Mapping[str, Any]: ...

def live_dry_run_execute(
    config_path: Path = DEFAULT_CONFIG_PATH,
    providers: Mapping[str, LiveDryRunProvider] | None = None,
) -> dict[str, Any]
def record_live_execution_attempt(
    config_path: Path = DEFAULT_CONFIG_PATH,
    db_path: Path = DEFAULT_DB_PATH,
    providers: Mapping[str, LiveDryRunProvider] | None = None,
) -> dict[str, Any]
def live_execution_log_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]
def launchd_plist(config_path: Path = DEFAULT_CONFIG_PATH) -> str
```

Summarize the SQLite background logs, target priorities, follow-up tests,
recommendations, human signoffs, report readiness, and log invariants for
manual or scheduled review. The supported command-line entrypoint is
`Skills/background.py` with subcommands; deprecated one-file wrappers have been
removed. Use `background_schema_status_summary(db_path)` to inspect expected
top-level SQLite tables without creating or migrating the database. Use
`background_schema_migration_preview(db_path)` to preview what additive
migration would create without writing anything. Use
`background_schema_operations_summary(db_path)` to combine schema status,
migration preview, packet-decision command readiness, and the next safe
operator action. Use
`background_operator_next_action_summary(config_path, db_path, input_path)` to
schema-gate the operator workflow and recommend the next conservative local
command while preserving no-network and no-external-submission guardrails. Use
`migrate_background_log_db(db_path)` to run the additive `init_log_db`
migration and report before/after table state without recording signoffs,
packets, reports, network access, or external submission. Use
`automation_readiness_summary(config_path)` to inspect scheduler
and live-mode blockers without performing network actions,
`record_automation_readiness(config_path, db_path)` to persist that snapshot to
SQLite, `live_dry_run_plan(config_path)` to produce an auditable no-network
query plan, `record_live_execution_attempt(config_path, db_path)` to persist a
mock-only execution attempt with no network access and no external submission,
and `launchd_plist(config_path)` to render a macOS scheduler template. Injected
live dry-run providers are accepted only as no-network probes; any provider
result that claims network access or external submission is rejected. Use
`live_policy_contract_summary(config_path)` to validate the live review policy
file and schema contract without network access, and
`live_provider_readiness(config_path)` to inspect provider-specific credential,
policy, rate-limit, and submission-safety blockers. Use
`live_credential_inventory(config_path)` to list credential environment
variables, provider mappings, environment/Keychain presence sources, and
storage guidance without recording secret values. Use
`write_live_credential_inventory_report(config_path, report_path)` to write the
same sanitized inventory to a JSON report for local operator review. Use
`live_dry_run_approval_bundle(config_path)` to inspect the combined scheduler,
policy, provider, and dry-run plan gates before any mock live dry-run execution
attempt, and `record_live_dry_run_approval_bundle(config_path, db_path)` to
persist that review object in SQLite. Use
`live_dry_run_operator_handoff(config_path)` and
`write_live_dry_run_operator_handoff(config_path, report_dir)` to render an
internal Markdown handoff for operator review without network access. Use
`record_live_dry_run_operator_handoff(config_path, db_path, report_dir)` to
write that handoff and persist the review entry in SQLite, and
`live_dry_run_operator_handoff_log_summary(db_path)` to summarize persisted
operator handoffs. Use
`background_blueprint_compliance_summary(db_path, input_path)` to audit the
current SQLite logs and target priority output against the background
automation blueprint. Use
`record_blueprint_compliance_summary(db_path, input_path)` to persist that audit
snapshot and `blueprint_compliance_log_summary(db_path)` to summarize the
append-only compliance log. Use
`background_operations_snapshot(config_path, db_path, input_path)` to aggregate
ledger, outcome, validation, signoff, scheduler, live dry-run, and blueprint
status into one conservative no-network review object, and
`record_background_operations_snapshot(...)` plus
`background_operations_snapshot_log_summary(db_path)` to persist and summarize
those operator snapshots. Use `signoff_packet(run_id, db_path)` and
`latest_unsigned_signoff_packet(db_path)` to assemble internal human-review
packets for unsigned follow-up runs. Use `write_signoff_packet(...)` and
`record_signoff_packet(...)` to write local Markdown packets and persist packet
metadata without recording a signoff decision. Use
`record_signoff_from_packet(...)` when a reviewer is ready to record a decision
from a persisted packet. Packet decisions validate the packet, unsigned
follow-up state, and target/run match before writing a normal human signoff
plus a packet-decision audit row, then record a post-decision operations
snapshot. `signoff_packet_decision_summary(db_path)` summarizes those packet
decision records. Use `signoff_packet_decision_readiness(db_path)` and
`latest_undecided_signoff_packet(db_path)` to inspect persisted packets that
still need packet-linked decisions before asking a reviewer to record one.
These APIs do not perform network access or enable external submission.

Default background log path:

```text
Logs/background.sqlite
```

The background automation is fixture-only and automated-offline by default. It
never submits or contacts external destinations.

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

---

## v0.14.0 New Public APIs

### orbit.py

```python
def close_approach_table(
    elements: OrbitalElements,
    start_jd: float,
    end_jd: float,
    n_steps: int = 10,
) -> list[dict]
```

Compute a close-approach table for the given orbital elements over the
specified JD range.  Each row contains `jd`, `helio_dist_au`, `geo_dist_au`,
`ra_deg`, and `dec_deg`.  Minimum two steps enforced.

### link.py

```python
def estimate_motion_uncertainty(tracklet: Tracklet) -> dict
```

Return a dict with keys `rate_err_arcsec_hr` (rate uncertainty) and
`pa_err_deg` (position-angle uncertainty) derived from the arc length and
motion-rate uncertainty stored in the tracklet.

### score.py

```python
def discovery_report(neo: ScoredNEO) -> dict
```

Generate a discovery-report dict for a `ScoredNEO`.  Contains object_id,
hazard_flag, alert_pathway, moid_au, neo_class, arc_days, n_observations,
neo_candidate_probability, discovery_priority, and estimated_diameter_m.

### classify.py

```python
def explain_classification(tracklet: Tracklet) -> dict
```

Return a dict with keys `dominant_hypothesis`, `confidence`, `posterior` (all
five probabilities), `features` (raw feature values), and
`tier1_feature_importances` (importances if a Tier-1 model is loaded, else
None).

### alert.py

```python
def draft_mpc_submission(neo: ScoredNEO, obs_code: str = "Xnn") -> dict
```

Assemble a draft MPC submission package (cover letter, 80-column report, JSON
format, ready-to-submit flag) without triggering any network actions.

### schemas.py

```python
class ObservationWindow(BaseModel):
    survey: Mission
    ra_deg: float
    dec_deg: float
    radius_deg: float
    start_jd: float
    end_jd: float
    limiting_magnitude: float | None = None
    notes: str = ""
```

Represents a planned or completed sky-survey window.

### fetch.py

```python
def estimate_limiting_magnitude(
    survey: Mission,
    exposure_time_s: float = 30.0,
    airmass: float = 1.0,
) -> float
```

Estimate the 5-sigma limiting magnitude for a given survey and observing
conditions using empirical zero-points.

### preprocess.py

```python
def quality_summary(result: PreprocessResult) -> dict
```

Summarise the quality of a `PreprocessResult`: fraction of sources passing
quality cuts, median PSF quality, median elongation.

### detect.py

```python
def streak_candidates(result: DetectResult) -> list[RawCandidate]
```

Return only the subset of raw candidates flagged as streaks/trails.

### Skills/photometric_calibration.py

Fit a zero-point offset from reference stars and apply to a tracklet.

```python
def fit_zero_point(obs_mags, ref_mags, weights=None) -> ZeroPointFit
def calibrate_observation(obs: dict, zero_point: ZeroPointFit) -> dict
def calibrate_tracklet(tracklet: dict, band: str, match_radius_arcsec=2.0) -> dict
```

### Skills/export_mpc_bulk.py

Batch-export MPC 80-column reports for all qualifying scored NEOs.

```python
def export_bulk(
    neos: list[ScoredNEO],
    out_dir: Path,
    obs_code: str = "Xnn",
    min_priority: float = 0.0,
    allowed_pathways: list[str] | None = None,
) -> dict
```

---

## v0.15.0 New Public APIs

### orbit.py

```python
def compute_orbital_period(elements: OrbitalElements) -> float
```

Return the orbital period in days using Kepler's third law: T = 365.25 × √(a³).
Returns 0.0 for non-positive semi-major axis.

### link.py

```python
def filter_high_motion(
    tracklets: list[Tracklet],
    min_rate_arcsec_hr: float = 10.0,
) -> list[Tracklet]
```

Return tracklets whose motion rate exceeds `min_rate_arcsec_hr`.  Useful for
isolating fast-moving NEO candidates from the bulk of slower main-belt objects.

### score.py

```python
def followup_priority_table(neos: list[ScoredNEO]) -> list[dict]
```

Return a flat list of dicts (one per NEO) sorted by discovery priority,
containing: rank, object_id, hazard_flag, alert_pathway, discovery_priority,
moid_au, neo_class, n_observations, arc_days, motion_rate_arcsec_hr.

### classify.py

```python
def batch_explain(tracklets: list[Tracklet]) -> list[dict]
```

Run `explain_classification` on a list of tracklets and return the results
as a list of dicts.

### alert.py

```python
def alert_summary_table(neos: list[ScoredNEO]) -> list[dict]
```

Return a flat per-NEO alert summary (no submissions triggered).  Each row
contains: object_id, hazard_flag, alert_pathway, moid_au, neo_class, arc_days,
n_observations, ready_to_submit.

### fetch.py

```python
def summarise_fetch_result(result: FetchResult) -> dict
```

Return a summary of a `FetchResult`: n_alerts, n_known_objects, survey,
ra_deg, dec_deg, radius_deg, date_start, date_end, limiting_magnitude.

### preprocess.py

```python
def flag_saturated_sources(result: PreprocessResult, saturation_mag: float = 12.0) -> list[str]
```

Return a list of `obs_id` strings for sources brighter than `saturation_mag`
that are likely saturated and should be masked before linking.

### schemas.py

```python
class CandidateSummary(BaseModel):
    object_id: str
    neo_class: NEOClass
    hazard_flag: HazardFlag
    alert_pathway: AlertPathway
    moid_au: float | None = None
    estimated_diameter_m: float | None = None
    absolute_magnitude_h: float | None = None
    arc_days: float
    n_observations: int
    neo_candidate_probability: Score
    discovery_priority: float = 0.0
```

Lightweight summary of a `ScoredNEO` for display or export.

### Skills

| Script | Purpose |
|---|---|
| `Skills/filter_candidates.py` | Filter scored NEO JSON by hazard flag, pathway, or minimum priority |
| `Skills/summarise_run.py` | Print/JSON summary of a pipeline run from scored NEO JSON |
| `Skills/plot_sky_coverage.py` | RA/Dec scatter plot of tracklet positions colour-coded by hazard flag |

---

## v0.16.0 through v0.74.0 Public API Additions

These releases added conservative helper APIs around live-data retrieval,
preprocessing quality, detection triage, linking, orbit review, classification
explanation, scoring, alert packaging, and calibration. All functions remain
guarded by the project policy that internally computed data must not be used to
claim confirmation or impact probability.

| Version | Module | Public additions |
|---|---|---|
| v0.16.0 | `orbit.py` | `classify_neo_class`, `tisserand_parameter` |
| v0.16.0 | `detect.py` | `filter_by_real_bogus` |
| v0.16.0 | `link.py` | `deduplicate_tracklets` |
| v0.16.0 | `score.py` | `pha_candidates`, `compute_statistics` |
| v0.16.0 | `classify.py` | `posterior_entropy` |
| v0.16.0 | `alert.py` | `format_neocp_report` |
| v0.16.0 | `fetch.py` | `merge_survey_alerts` |
| v0.16.0 | `preprocess.py` | `compute_color_index` |
| v0.16.0 | `schemas.py` | `NEOStatistics` |
| v0.17.0 | `orbit.py` | `batch_predict_ephemeris`, `resonance_check` |
| v0.17.0 | `detect.py` | `compute_streak_metric` |
| v0.17.0 | `link.py` | `split_tracklet` |
| v0.17.0 | `classify.py` | `dominant_hypothesis` |
| v0.17.0 | `score.py` | `close_approach_candidates` |
| v0.17.0 | `alert.py` | `ready_for_submission` |
| v0.17.0 | `fetch.py` | `filter_alerts_by_motion` |
| v0.17.0 | `preprocess.py` | `estimate_source_density` |
| v0.17.0 | `schemas.py` | `TrackletSummary` |
| v0.18.0 | `orbit.py` | `ephemeris_uncertainty` |
| v0.18.0 | `detect.py` | `cluster_detections` |
| v0.18.0 | `link.py` | `compute_arc_statistics` |
| v0.18.0 | `classify.py` | `classify_morphology` |
| v0.18.0 | `score.py` | `absolute_magnitude_from_diameter` |
| v0.18.0 | `alert.py` | `format_discovery_circular` |
| v0.18.0 | `fetch.py` | `build_observation_window` |
| v0.18.0 | `preprocess.py` | `compute_source_snr` |
| v0.18.0 | `schemas.py` | `CloseApproachEvent` |
| v0.18.0 | `calibration.py` | `bootstrap_confidence_interval` |
| v0.19.0 | `orbit.py` | `orbital_energy` |
| v0.19.0 | `detect.py` | `compute_trail_length` |
| v0.19.0 | `link.py` | `assess_link_confidence` |
| v0.19.0 | `classify.py` | `batch_morphology` |
| v0.19.0 | `score.py` | `compute_impact_energy` |
| v0.19.0 | `alert.py` | `format_alert_summary` |
| v0.19.0 | `fetch.py` | `count_known_objects_in_field` |
| v0.19.0 | `preprocess.py` | `detect_bad_pixels` |
| v0.19.0 | `schemas.py` | `SurveyField` |
| v0.19.0 | `calibration.py` | `cross_validate_calibration` |
| v0.20.0 | `orbit.py` | `compute_phase_angle` |
| v0.20.0 | `detect.py` | `compute_psf_fwhm` |
| v0.20.0 | `link.py` | `compute_tracklet_grade` |
| v0.20.0 | `classify.py` | `summarize_classifications` |
| v0.20.0 | `score.py` | `compute_novelty_score` |
| v0.20.0 | `alert.py` | `generate_observation_request` |
| v0.20.0 | `fetch.py` | `fetch_mpc_observations` |
| v0.20.0 | `preprocess.py` | `compute_astrometric_scatter` |
| v0.20.0 | `schemas.py` | `PipelineConfig` |
| v0.20.0 | `calibration.py` | `compute_log_loss` |
| v0.21.0 | `orbit.py` | `compute_heliocentric_distance` |
| v0.21.0 | `detect.py` | `estimate_sky_background` |
| v0.21.0 | `link.py` | `filter_by_arc_length` |
| v0.21.0 | `classify.py` | `calibrate_posterior` |
| v0.21.0 | `score.py` | `compute_threat_score` |
| v0.21.0 | `alert.py` | `generate_mpc_cover_letter` |
| v0.21.0 | `fetch.py` | `fetch_atlas_forced` |
| v0.21.0 | `preprocess.py` | `normalize_photometry` |
| v0.21.0 | `schemas.py` | `ObservationBatch` |
| v0.21.0 | `calibration.py` | `reliability_diagram` |
| v0.22.0 | `orbit.py` | `compute_synodic_period` |
| v0.22.0 | `detect.py` | `compute_detection_efficiency` |
| v0.22.0 | `link.py` | `summarize_arc_statistics` |
| v0.22.0 | `classify.py` | `compute_classification_table` |
| v0.22.0 | `score.py` | `filter_by_alert_pathway` |
| v0.22.0 | `alert.py` | `format_impact_notification` |
| v0.22.0 | `fetch.py` | `fetch_ztf_alerts` |
| v0.22.0 | `preprocess.py` | `compute_image_quality_metrics` |
| v0.22.0 | `schemas.py` | `DetectionSummary` |
| v0.22.0 | `calibration.py` | `calibration_report` |
| v0.23.0 | `orbit.py` | `compute_apparent_magnitude` |
| v0.23.0 | `detect.py` | `count_detections_by_filter` |
| v0.23.0 | `link.py` | `filter_by_nights_observed` |
| v0.23.0 | `classify.py` | `get_posterior_vector` |
| v0.23.0 | `score.py` | `compute_followup_urgency` |
| v0.23.0 | `alert.py` | `count_pending_alerts` |
| v0.23.0 | `fetch.py` | `estimate_survey_depth` |
| v0.23.0 | `preprocess.py` | `compute_photometric_scatter` |
| v0.23.0 | `schemas.py` | `PhotometricSolution` |
| v0.23.0 | `calibration.py` | `compare_calibrators` |
| v0.24.0 | `orbit.py` | `compute_absolute_magnitude` |
| v0.24.0 | `detect.py` | `compute_motion_vector` |
| v0.24.0 | `link.py` | `merge_overlapping_tracklets` |
| v0.24.0 | `classify.py` | `compute_neo_probability` |
| v0.24.0 | `score.py` | `compute_discovery_score` |
| v0.24.0 | `alert.py` | `format_submission_checklist` |
| v0.24.0 | `fetch.py` | `filter_by_survey` |
| v0.24.0 | `preprocess.py` | `estimate_zero_point` |
| v0.24.0 | `schemas.py` | `ObservationStatistics` |
| v0.24.0 | `calibration.py` | `compute_roc_auc` |
| v0.25.0 | `orbit.py` | `compute_perihelion_date` |
| v0.25.0 | `detect.py` | `flag_moving_sources` |
| v0.25.0 | `link.py` | `validate_tracklet` |
| v0.25.0 | `classify.py` | `compute_artifact_probability` |
| v0.25.0 | `score.py` | `compute_observation_priority` |
| v0.25.0 | `alert.py` | `validate_alert_package` |
| v0.25.0 | `fetch.py` | `fetch_panstarrs_catalog` |
| v0.25.0 | `preprocess.py` | `compute_difference_image_snr` |
| v0.25.0 | `schemas.py` | `AlertPackage` |
| v0.25.0 | `calibration.py` | `compute_precision_recall_curve` |
| v0.26.0 | `background.py` | `automation_readiness_summary`, `launchd_plist` |
| v0.26.0 | `schemas.py` | `BackgroundRunMode` supports `automated`; `BackgroundConfig` scheduler/live-readiness fields |
| v0.27.0 | `background.py` | `record_automation_readiness`, `automation_readiness_log_summary` |
| v0.28.0 | `background.py` | `live_dry_run_plan`, `record_live_dry_run_plan`, `live_dry_run_plan_log_summary` |
| v0.29.0 | `background.py` | `live_dry_run_execute`, `record_live_execution_attempt`, `live_execution_log_summary` |
| v0.30.0 | `background.py` | `LiveDryRunProvider`, `MockLiveDryRunProvider`; provider injection for live dry-run execution |
| v0.31.0 | `background.py` | `live_provider_capabilities`, `live_provider_readiness`; provider readiness in automation summaries and dry-run plans |
| v0.32.0 | `background.py` | `live_policy_contract_summary`; live review policy contract status in readiness summaries and dry-run plans |
| v0.33.0 | `Skills/background.py` | `live-policy-contract-summary` CLI command |
| v0.34.0 | `Skills/background.py` | `live-provider-readiness-summary` CLI command |
| v0.35.0 | `background.py` / `Skills/background.py` | `live_dry_run_approval_bundle`; `live-dry-run-approval-bundle` CLI command |
| v0.36.0 | `background.py` / `Skills/background.py` | `record_live_dry_run_approval_bundle`, `live_dry_run_approval_bundle_log_summary`; persisted approval-bundle CLI commands |
| v0.37.0 | `background.py` / `Skills/background.py` | `live_dry_run_operator_handoff`, `write_live_dry_run_operator_handoff`; operator handoff CLI commands |
| v0.38.0 | `background.py` / `Skills/background.py` | `record_live_dry_run_operator_handoff`, `live_dry_run_operator_handoff_log_summary`; persisted operator handoff CLI commands |
| v0.39.0 | `alert.py` / `calibration.py` / `classify.py` / `detect.py` / `fetch.py` / `link.py` / `orbit.py` / `preprocess.py` / `schemas.py` / `score.py` | `estimate_followup_window`, `compute_f1_score`, `compute_confusion_matrix`, `compute_source_extent`, `fetch_css_alerts`, `compute_great_circle_residual`, `compute_eccentric_anomaly`, `compute_cutout_entropy`, `OrbitalElementsSummary`, `compute_size_estimate` |
| v0.40.0 | `alert.py` / `calibration.py` / `classify.py` / `detect.py` / `fetch.py` / `link.py` / `orbit.py` / `preprocess.py` / `schemas.py` / `score.py` | `format_candidate_dossier`, `compute_average_precision`, `compute_calibration_gain`, `estimate_observation_depth`, `fetch_panstarrs_moving_objects`, `compute_position_angle_consistency`, `compute_true_anomaly`, `compute_background_level`, `CandidateReport`, `compute_close_approach_score` |
| v0.41.0 | `alert.py` / `calibration.py` / `classify.py` / `detect.py` / `fetch.py` / `link.py` / `orbit.py` / `preprocess.py` / `schemas.py` / `score.py` | `count_alerts_by_flag`, `compute_calibration_sharpness`, `batch_classify_morphology`, `filter_by_magnitude`, `fetch_recent_mpc_neos`, `score_tracklet_quality`, `compute_mean_motion`, `compute_pixel_histogram`, `SurveyStatistics`, `compute_combined_priority` |
| v0.42.0 | `alert.py` / `calibration.py` / `classify.py` / `detect.py` / `fetch.py` / `link.py` / `orbit.py` / `preprocess.py` / `schemas.py` / `score.py` | `format_bulk_summary`, `compute_brier_skill_score`, `compute_class_entropy_stats`, `compute_streak_density`, `estimate_field_completeness`, `compute_night_span`, `compute_longitude_of_perihelion`, `compute_cutout_contrast`, `EphemerisPoint`, `compute_weighted_priority` |
| v0.43.0 | `alert.py` / `calibration.py` / `classify.py` / `detect.py` / `fetch.py` / `link.py` / `orbit.py` / `preprocess.py` / `schemas.py` / `score.py` | `count_ready_to_submit`, `compute_discrimination_score`, `compute_tier1_score_distribution`, `compute_angular_velocity`, `fetch_known_neo_ephemerides`, `compute_tracklet_velocity_dispersion`, `compute_orbital_inclination_class`, `compute_image_gradient`, `ObservationCluster`, `compute_arc_quality_bonus` |
| v0.44.0 | `alert.py` / `calibration.py` / `classify.py` / `detect.py` / `fetch.py` / `link.py` / `orbit.py` / `preprocess.py` / `schemas.py` / `score.py` | `compute_alert_age_days`, `compute_resolution_score`, `compute_class_entropy_summary`, `compute_detection_gap`, `fetch_neocp_objects`, `compute_inter_night_gaps`, `compute_mean_anomaly_at_jd`, `compute_cutout_symmetry`, `AstrometricResidual`, `compute_weighted_hazard_score` |
| v0.45.0 | `alert.py` / `calibration.py` / `classify.py` / `detect.py` / `fetch.py` / `link.py` / `orbit.py` / `preprocess.py` / `schemas.py` / `score.py` | `format_observation_log`, `compute_expected_positive_rate`, `compute_neo_class_distribution`, `compute_observation_cadence`, `fetch_mpc_orbit_elements`, `filter_by_motion_rate`, `compute_orbital_velocity`, `compute_streak_angle`, `ResidualSummary`, `compute_hazard_grade` |
| v0.46.0 | `alert.py` / `calibration.py` / `classify.py` / `detect.py` / `fetch.py` / `link.py` / `orbit.py` / `preprocess.py` / `schemas.py` / `score.py` | `format_mpc_ades_psv`, `compute_reliability_score`, `compute_posterior_update`, `compute_field_source_count`, `fetch_known_neo_list`, `compute_tracklet_arc_nights`, `compute_perihelion_distance`, `compute_radial_profile`, `ObservationCoverage`, `compute_priority_rank` |
| v0.47.0 | `alert.py` / `calibration.py` / `classify.py` / `detect.py` / `fetch.py` / `link.py` / `orbit.py` / `preprocess.py` / `schemas.py` / `score.py` | `format_discovery_report`, `compute_calibration_drift`, `compute_tier1_confidence`, `compute_brightness_trend`, `fetch_neocp_confirmed`, `compute_mean_consecutive_motion`, `compute_aphelion_distance`, `compute_psf_asymmetry`, `NightSummary`, `compute_survey_completeness` |
| v0.48.0 | `alert.py` / `calibration.py` / `classify.py` / `detect.py` / `fetch.py` / `link.py` / `orbit.py` / `preprocess.py` / `schemas.py` / `score.py` | `format_neocp_submission`, `compute_calibration_uniformity`, `compute_posterior_stability`, `compute_variability_index`, `fetch_mpc_orbit_catalog`, `compute_tracklet_sky_density`, `compute_tisserand_wrt_earth`, `compute_source_compactness`, `TrackletCluster`, `compute_weighted_risk_score` |
| v0.49.0 | `alert.py` / `calibration.py` / `classify.py` / `detect.py` / `fetch.py` / `link.py` / `orbit.py` / `preprocess.py` / `score.py` | `count_observations_by_mission`, `compute_mean_calibration_error`, `compute_class_probability_range`, `compute_angular_separation`, `compute_field_overlap`, `compute_tracklet_completeness`, `compute_orbital_arc_quality`, `compute_cutout_peak_position`, `compute_hazard_summary` |
| v0.50.0 | `alert.py` / `calibration.py` / `classify.py` / `detect.py` / `fetch.py` / `link.py` / `orbit.py` / `preprocess.py` / `schemas.py` / `score.py` | `format_close_approach_bulletin`, `compute_resolution`, `compute_ensemble_agreement`, `compute_streak_orientation`, `fetch_known_phas`, `find_longest_tracklet`, `compute_mean_anomaly_at_epoch`, `compute_local_background`, `CampaignSummary`, `compute_priority_percentile` |
| v0.51.0 | `background.py` / `Skills/background.py` | `background_blueprint_compliance_summary`; `blueprint-compliance-summary` CLI command |
| v0.52.0 | `background.py` / `Skills/background.py` | `record_blueprint_compliance_summary`, `blueprint_compliance_log_summary`; persisted blueprint compliance CLI commands |
| v0.53.0 | `background.py` / `Skills/background.py` | `background_operations_snapshot`, `record_background_operations_snapshot`, `background_operations_snapshot_log_summary`; operations snapshot CLI commands |
| v0.54.0 | `background.py` / `Skills/background.py` | `signoff_packet`, `latest_unsigned_signoff_packet`, `write_signoff_packet`, `record_signoff_packet`, `signoff_packet_log_summary`; signoff packet CLI commands |
| v0.55.0 | `background.py` / `Skills/background.py` | `record_signoff_from_packet`, `signoff_packet_decision_summary`; packet decision CLI commands |
| v0.56.0 | `background.py` / `Skills/background.py` | `signoff_packet_decision_readiness`, `latest_undecided_signoff_packet`; packet decision readiness CLI commands |
| v0.57.0 | `background.py` / `Skills/background.py` | `background_schema_status_summary`, `migrate_background_log_db`; schema status and init-log-db CLI commands |
| v0.58.0 | `background.py` / `Skills/background.py` | `background_schema_migration_preview`; init-log-db-preview CLI command |
| v0.59.0 | `background.py` / `Skills/background.py` | `background_schema_operations_summary`; schema-operations-summary CLI command |
| v0.60.0 | `background.py` / `Skills/background.py` | `background_operator_next_action_summary`; operator-next-action CLI command |
| v0.72.0 | `background.py` / `Skills/background.py` | `internal_follow_up_disposition_summary`; internal-follow-up-disposition CLI command |
| v0.73.0 | `background.py` / `Skills/background.py` | `live_credential_inventory`; live-credential-inventory CLI command |
| v0.74.0 | `background.py` / `Skills/background.py` | env/Keychain credential-source reporting; `write_live_credential_inventory_report`; live-credential-inventory --write-report CLI option |

### Skills and CLI additions in v0.16.0 through v0.74.0

`export_candidate_report.py`, `tag_neo_class.py`, `check_tisserand.py`,
`export_followup_requests.py`, `ephemeris_check.py`,
`flag_comet_candidates.py`, `compute_orbital_energy.py`,
`assess_survey_coverage.py`, `grade_tracklets.py`,
`query_mpc_observations.py`, `compute_threat_scores.py`,
`fetch_atlas_data.py`, `plot_calibration.py`, `export_survey_summary.py`,
`compute_apparent_magnitudes.py`, `triage_candidates.py`,
`compute_discovery_scores.py`, `format_submission_checklists.py`,
`validate_pipeline_run.py`, `export_atlas_lightcurve.py`,
`analyze_field_detections.py`, `compute_eccentric_anomaly.py`,
`compute_true_anomaly.py`, `export_candidate_dossiers.py`,
`compute_combined_priority.py`, `fetch_recent_neos.py`,
`compute_weighted_priority.py`, `estimate_field_completeness.py`,
`compute_orbital_inclination_class.py`, `compute_tier1_score_distribution.py`,
`compute_mean_anomaly.py`, `compute_weighted_hazard_scores.py`,
`compute_hazard_grades.py`, `compute_orbital_velocity.py`,
`compute_priority_ranks.py`, `export_ades_report.py`,
`compute_aphelion_distances.py`, `generate_night_summary.py`,
`compute_risk_scores.py`, `compute_variability_indices.py`,
`compute_field_overlap.py`, `compute_hazard_summary.py`,
`fetch_known_phas.py`, `find_longest_tracklet.py`, plus
`Skills/background.py automation-readiness`,
`Skills/background.py record-automation-readiness`,
`Skills/background.py automation-readiness-log-summary`, and
`Skills/background.py live-policy-contract-summary`,
`Skills/background.py live-provider-readiness-summary`,
`Skills/background.py live-credential-inventory`,
`Skills/background.py live-dry-run-approval-bundle`,
`Skills/background.py record-live-dry-run-approval-bundle`,
`Skills/background.py live-dry-run-approval-bundle-log-summary`,
`Skills/background.py live-dry-run-operator-handoff`,
`Skills/background.py write-live-dry-run-operator-handoff`,
`Skills/background.py record-live-dry-run-operator-handoff`,
`Skills/background.py live-dry-run-operator-handoff-log-summary`,
`Skills/background.py live-dry-run-plan`,
`Skills/background.py record-live-dry-run-plan`,
`Skills/background.py live-dry-run-plan-log-summary`,
`Skills/background.py live-dry-run-execute`,
`Skills/background.py live-execution-log-summary`,
`Skills/background.py blueprint-compliance-summary`,
`Skills/background.py record-blueprint-compliance-summary`,
`Skills/background.py blueprint-compliance-log-summary`,
`Skills/background.py operations-snapshot`,
`Skills/background.py record-operations-snapshot`,
`Skills/background.py operations-snapshot-log-summary`,
`Skills/background.py signoff-packet`,
`Skills/background.py latest-unsigned-signoff-packet`,
`Skills/background.py write-signoff-packet`,
`Skills/background.py record-signoff-packet`,
`Skills/background.py signoff-packet-log-summary`,
`Skills/background.py record-signoff-from-packet`,
`Skills/background.py signoff-packet-decision-summary`,
`Skills/background.py signoff-packet-decision-readiness`,
`Skills/background.py latest-undecided-signoff-packet`,
`Skills/background.py internal-follow-up-disposition`,
`Skills/background.py schema-status-summary`,
`Skills/background.py init-log-db-preview`,
`Skills/background.py schema-operations-summary`,
`Skills/background.py operator-next-action`,
`Skills/background.py init-log-db`, and
`Skills/background.py launchd-plist`.
