# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## v0.30.0

- `background.py`: added `LiveDryRunProvider` and `MockLiveDryRunProvider` for
  injected no-network survey dry-run probes.
- `live_dry_run_execute(config_path, providers)` and
  `record_live_execution_attempt(config_path, db_path, providers)` now accept an
  optional provider map, aggregate per-survey query results, and report missing
  providers.
- Provider results are rejected if they claim network access or external
  submission, preserving the M4 no-submission guardrail.
- 2 new tests (1340 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.30.0.

## v0.29.0

- `background.py`: added `live_dry_run_execute(config_path)`,
  `record_live_execution_attempt(config_path, db_path)`, and
  `live_execution_log_summary(db_path)` for mock-only live dry-run execution
  attempts.
- `init_log_db`: added top-level SQLite table `live_execution_log` for
  auditable dry-run execution attempts.
- `Skills/background.py`: added `live-dry-run-execute` and
  `live-execution-log-summary` subcommands.
- Live dry-run execution remains explicitly mock-only: no network access is
  performed and no external submission can be enabled by this command.
- 2 new tests (1338 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.29.0.

## v0.28.0

- `background.py`: added `live_dry_run_plan(config_path)`,
  `record_live_dry_run_plan(config_path, db_path)`, and
  `live_dry_run_plan_log_summary(db_path)`.
- `background/live_review_policy.example.json` and
  `background/live_review_policy.schema.json`: added a formal live review
  policy contract for M4 dry-run approval.
- `background/config.json`: declares `MAST_API_TOKEN` along with ZTF/ATLAS
  credentials and points to the example review policy.
- `Skills/background.py`: added `live-dry-run-plan`,
  `record-live-dry-run-plan`, and `live-dry-run-plan-log-summary` subcommands.
- `automation_readiness_summary`: now validates live review policy fields and
  reports policy-specific blockers before any network access.
- 1 new test (1336 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.28.0.

## v0.27.0

- `background.py`: added `automation_readiness_log_summary(db_path)` and
  `record_automation_readiness(config_path, db_path)`.
- `init_log_db`: added top-level SQLite table `automation_readiness_log` for
  scheduler/live-readiness snapshots.
- `Skills/background.py`: added `record-automation-readiness` and
  `automation-readiness-log-summary` subcommands.
- `docs/BACKGROUND_SEARCH_AUTOMATION.md` and `docs/API_REFERENCE.md`: documented
  persisted readiness checks and new CLI/API entries.
- 2 new tests (1335 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.27.0.

## v0.26.0

- `schemas.py`: `BackgroundRunMode` now supports `automated`; `BackgroundConfig`
  added scheduler readiness fields, live review policy, and required credential
  environment variable names.
- `background.py`: added `automation_readiness_summary(config_path)` and
  `launchd_plist(config_path)`; live network mode reports explicit blockers
  before any network action.
- `Skills/background.py`: added `automation-readiness` and `launchd-plist`
  subcommands.
- `background/config.json`: default mode is automated offline scheduling with
  live network disabled and required credential names declared.
- `docs/BACKGROUND_SEARCH_AUTOMATION.md`: updated scheduler guidance for
  automated offline runs and macOS launchd template generation.
- `README.md`: refreshed stale abstract from v0.10.0 / 346 tests / 62% link rate
  to v0.26.0 / 1333 tests / n=200 100% synthetic baseline.
- 4 new tests (1333 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.26.0.

## v0.25.0

- Added `compute_perihelion_date`, `flag_moving_sources`, `validate_tracklet`,
  `compute_artifact_probability`, `compute_observation_priority`,
  `validate_alert_package`, `fetch_panstarrs_catalog`,
  `compute_difference_image_snr`, `AlertPackage`, and
  `compute_precision_recall_curve`.
- Added `Skills/validate_pipeline_run.py` and
  `Skills/export_atlas_lightcurve.py`.
- Added `docs/PREPROCESS_GUIDE.md`.
- 87 new tests (1329 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.25.0.

## v0.24.0

- Added `compute_absolute_magnitude`, `compute_motion_vector`,
  `merge_overlapping_tracklets`, `compute_neo_probability`,
  `compute_discovery_score`, `format_submission_checklist`,
  `filter_by_survey`, `estimate_zero_point`, `ObservationStatistics`, and
  `compute_roc_auc`.
- Added `Skills/compute_discovery_scores.py` and
  `Skills/format_submission_checklists.py`.
- Added `docs/FETCH_GUIDE.md`.
- 75 new tests (1242 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.24.0.

## v0.23.0

- Added `compute_apparent_magnitude`, `count_detections_by_filter`,
  `filter_by_nights_observed`, `get_posterior_vector`,
  `compute_followup_urgency`, `count_pending_alerts`, `estimate_survey_depth`,
  `compute_photometric_scatter`, `PhotometricSolution`, and
  `compare_calibrators`.
- Added `Skills/compute_apparent_magnitudes.py` and
  `Skills/triage_candidates.py`.
- Added `docs/LINKING_GUIDE.md`.
- 78 new tests (1167 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.23.0.

## v0.22.0

- Added `compute_synodic_period`, `compute_detection_efficiency`,
  `summarize_arc_statistics`, `compute_classification_table`,
  `filter_by_alert_pathway`, `format_impact_notification`,
  `fetch_ztf_alerts`, `compute_image_quality_metrics`, `DetectionSummary`,
  and `calibration_report`.
- Added `Skills/plot_calibration.py` and `Skills/export_survey_summary.py`.
- Added `docs/DETECTION_GUIDE.md`.
- 71 new tests (1089 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.22.0.

## v0.21.0

- Added `compute_heliocentric_distance`, `estimate_sky_background`,
  `filter_by_arc_length`, `calibrate_posterior`, `compute_threat_score`,
  `generate_mpc_cover_letter`, `fetch_atlas_forced`, `normalize_photometry`,
  `ObservationBatch`, and `reliability_diagram`.
- Added `Skills/compute_threat_scores.py` and `Skills/fetch_atlas_data.py`.
- Added `docs/THREAT_ASSESSMENT.md`.
- 69 new tests (1018 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.21.0.

## v0.20.0

- Added `compute_phase_angle`, `compute_psf_fwhm`, `compute_tracklet_grade`,
  `summarize_classifications`, `compute_novelty_score`,
  `generate_observation_request`, `fetch_mpc_observations`,
  `compute_astrometric_scatter`, `PipelineConfig`, and `compute_log_loss`.
- Added `Skills/grade_tracklets.py` and `Skills/query_mpc_observations.py`.
- Added `docs/QUALITY_METRICS.md`.
- 69 new tests (949 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.20.0.

## v0.19.0

- `orbit.py`: added `orbital_energy(elements)` — specific orbital energy in AU²/yr² using two-body formula E = −4π²/(2a); negative = bound, 0 = parabolic, positive = hyperbolic; returns inf for a ≤ 0; added to `__all__`.
- `detect.py`: added `compute_trail_length(obs)` — trail length in arcsec from difference-image second moments (largest eigenvalue of 2×2 moment ellipse); ZTF pixel scale 1.01 arcsec/px; added to `__all__`.
- `link.py`: added `assess_link_confidence(tracklet)` — confidence score [0, 1] from linear-fit RMS residual; confidence = max(0, 1 − rms / 10 arcsec); returns 0 for <2 observations; added to `__all__`.
- `classify.py`: added `batch_morphology(tracklet)` — aggregate morphology across all observations; returns modal_class, class_counts, streak_fraction; added to `__all__`.
- `score.py`: added `compute_impact_energy(diameter_m, velocity_km_s, density_kg_m3)` — kinetic impact energy in megatons TNT; assumes spherical body; returns 0 for non-positive inputs; added to `__all__`.
- `alert.py`: added `format_alert_summary(neos, max_rows)` — plain-text ranked NEO summary table; columns: rank, object_id, hazard_flag, alert_pathway, moid_au, priority; added to `__all__`.
- `fetch.py`: added `count_known_objects_in_field(ra_deg, dec_deg, radius_deg)` — count MPC known objects in a circular field; returns 0 on network failure; added to `__all__`.
- `preprocess.py`: added `detect_bad_pixels(obs, sigma_threshold)` — identify outlier pixels via MAD-based sigma clipping; returns list of (row, col) tuples; added to `__all__`.
- `schemas.py`: added `SurveyField` — frozen Pydantic model (field_id, ra_deg, dec_deg, radius_deg, limiting_mag, n_sources, jd); added to `__all__`.
- `calibration.py`: added `cross_validate_calibration(probs, labels, n_folds, metric)` — K-fold cross-validation of calibration quality; returns (mean, std); added to `__all__`. Fixed `bootstrap_confidence_interval` to use `len()` check for numpy array empty-guard.
- `Skills/compute_orbital_energy.py`: new — batch orbital energy computation with bound/parabolic/hyperbolic label; CLI with `--json` flag.
- `Skills/assess_survey_coverage.py`: new — survey field coverage report (area, limiting mag, source count, fields per night); CLI with `--json` flag.
- `docs/CLASSIFICATION_GUIDE.md`: new — technical reference for three-tier ML classification, morphology classification, ensemble stacking, calibration, and conservative classification policy.
- 81 new tests (880 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.19.0.

## v0.18.0

- `orbit.py`: added `ephemeris_uncertainty(elements, target_jd)` — sky-plane positional uncertainty (RA, Dec, arcsec) propagated from orbit quality code; scales with propagation time; added to `__all__`.
- `detect.py`: added `cluster_detections(observations, radius_arcsec)` — greedy single-linkage spatial clustering; returns list of Observation tuples; added to `__all__`.
- `link.py`: added `compute_arc_statistics(tracklet)` — summary dict with n_observations, n_nights, arc_days, mean_motion_arcsec_hr, motion_pa_std_deg; added to `__all__`.
- `classify.py`: added `classify_morphology(obs)` — classify source as 'point_source', 'extended', or 'streak' from image second moments; falls back to 'point_source' without cutout; added to `__all__`.
- `score.py`: added `absolute_magnitude_from_diameter(diameter_m, albedo)` — inverse diameter–albedo relation; returns inf for zero/negative inputs; added to `__all__`. Fixed formula: H = -5·log10(D·√p / 1329000).
- `alert.py`: added `format_discovery_circular(neo)` — IAU CBET-style plain-text discovery circular; includes orbital elements, diameter, MOID, observer template; does not transmit; added to `__all__`.
- `fetch.py`: added `build_observation_window(ra_deg, dec_deg, radius_deg, start_jd, end_jd, surveys)` — validated ObservationWindow factory; raises ValueError for invalid JD range, zero radius, or unknown surveys; added to `__all__`.
- `preprocess.py`: added `compute_source_snr(obs)` — peak-to-background SNR from difference-image cutout; returns None if no cutout; added to `__all__`.
- `schemas.py`: added `CloseApproachEvent` — frozen Pydantic model (object_id, jd, geocentric_dist_au, relative_velocity_km_s, warning_time_days); added to `__all__`.
- `calibration.py`: added `bootstrap_confidence_interval(probs, labels, n_bootstrap, metric)` — bootstrap 95% CI for Brier or ECE; returns (lower, upper, mean); seed-reproducible; added to `__all__`.
- `Skills/ephemeris_check.py`: new — predict sky positions for tracklets at a user-specified JD; CLI with `--jd` and `--json` flags.
- `Skills/flag_comet_candidates.py`: new — combined Tisserand + eccentricity comet-candidate flag; CLI with `--threshold`, `--min-ecc`, `--json` flags.
- `docs/ALERT_PROTOCOL.md`: new — detailed technical reference for the alert-pathway decision tree, gate conditions, MPC submission, NEOCP monitoring, and NASA PDCO notification.
- 70 new tests (799 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.18.0.

## v0.17.0

- `orbit.py`: added `batch_predict_ephemeris(elements_list, target_jd)` — predict sky positions for a list of OrbitalElements at one JD; wraps `predict_ephemeris` with per-element error isolation; added to `__all__`.
- `orbit.py`: added `resonance_check(elements, tolerance)` — detect mean-motion resonance with Jupiter; checks T_J/T_asteroid ratio against common p:q pairs; returns resonance label and fractional offset or None; added to `__all__`.  Fixed ratio convention to use mean-motion ratio (T_Jupiter/T_asteroid).
- `detect.py`: added `compute_streak_metric(obs)` — quantify streak severity from difference-image second moments; returns float in [0, 1] (0=round, 1=maximally elongated); handles degenerate zero-eigenvalue case; added to `__all__`.
- `link.py`: added `split_tracklet(tracklet, split_jd)` — split a tracklet at split_jd into two sub-tracklets; raises ValueError if either sub-tracklet would have fewer than 2 observations; added to `__all__`.
- `classify.py`: added `dominant_hypothesis(posterior)` — return (hypothesis_name, probability) for the highest-probability class in a NEOPosterior; returns ("unknown", 0.0) for all-zero posteriors; added to `__all__`.
- `score.py`: added `close_approach_candidates(neos, max_moid_au)` — filter ScoredNEO list to objects with MOID ≤ max_moid_au; objects with moid_au=None excluded; default threshold 0.05 AU; added to `__all__`.
- `alert.py`: added `ready_for_submission(neo)` — boolean gate checking all alert-protocol preconditions (MOID ≤ 0.05 AU, orbit quality ≥ 2, real_bogus ≥ 0.90, not known_object); returns (bool, unmet_conditions list); fixed `orbit_quality_code` → `quality_code` field name; added to `__all__`.
- `fetch.py`: added `filter_alerts_by_motion(alerts, min_rate_arcsec_hr, max_rate_arcsec_hr)` — filter observation tuple by apparent motion rate proxy via ssdistnr; observations without ssdistnr pass through; added to `__all__`.
- `preprocess.py`: added `estimate_source_density(observations, field_radius_deg)` — source count per square degree using great-circle separation from field centroid; returns 0.0 for empty input or zero field area; added to `__all__`.
- `schemas.py`: added `TrackletSummary` — lightweight frozen Pydantic model for tracklet display/export (object_id, arc_days, n_observations, motion_rate, motion_pa, neo_class, discovery_priority); added to `__all__`.
- `Skills/check_tisserand.py`: new — batch-compute Tisserand parameter for tracklets/ScoredNEO dicts; flags T_J < threshold as comet-like; CLI with `--threshold` and `--json` flags.
- `Skills/export_followup_requests.py`: new — generate NEOCP follow-up request files for candidates above priority threshold; uses `format_neocp_report`; CLI with `--min-priority`, `--out-dir`, `--obs-code`, `--summary` flags.
- `docs/ORBIT_FITTING.md`: new — technical reference for orbit fitting subsystem covering Gauss's method, differential correction, orbit quality codes, MOID computation, NEO classification, and Tisserand parameter.
- 146 new tests (729 total, previously 583); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.17.0.

## v0.16.0

- `orbit.py`: added `classify_neo_class(elements)` — derive NEO dynamical class (amor/apollo/aten/ieo/unknown) from orbital elements; added to `__all__`.
- `orbit.py`: added `tisserand_parameter(elements)` — compute Tisserand parameter relative to Jupiter (T_J); returns 0.0 for non-positive a; added to `__all__`.
- `detect.py`: added `filter_by_real_bogus(result, threshold)` — return new DetectResult keeping only candidates with max real/bogus ≥ threshold; candidates without RB score kept conservatively; added to `__all__`.
- `link.py`: added `deduplicate_tracklets(tracklets)` — remove tracklets sharing ≥ 50% obs_ids with a longer-arc tracklet; longer arc wins; added to `__all__`.
- `score.py`: added `pha_candidates(neos)` — filter ScoredNEO list to PHA candidates only; added to `__all__`.
- `score.py`: added `compute_statistics(neos)` — compute aggregate NEOStatistics (counts, mean/max priority, class distribution); added to `__all__`.
- `classify.py`: added `posterior_entropy(posterior)` — Shannon entropy of NEOPosterior in bits; range [0, log2(5)] ≈ [0, 2.322]; added to `__all__`.
- `alert.py`: added `format_neocp_report(neo, obs_code)` — generate plain-text NEOCP follow-up request with guardrail text; does not submit; added to `__all__`.
- `fetch.py`: added `merge_survey_alerts(results)` — merge multiple FetchResults, deduplicate by obs_id, widen JD range, deduplicate surveys; added to `__all__`.
- `preprocess.py`: added `compute_color_index(obs1, obs2)` — magnitude difference between two observations in different bands within 1 hour; added to `__all__`.
- `schemas.py`: added `NEOStatistics` — frozen Pydantic model for aggregate pipeline run statistics; added to `__all__`.
- `Skills/export_candidate_report.py`: new — per-candidate plain-text reports from scored NEO JSON; supports `--split` to write one file per candidate.
- `Skills/tag_neo_class.py`: new — batch-tag NEO class for tracklets or ScoredNEO dicts using `classify_neo_class` from orbit.py.
- `docs/TRAINING_GUIDE.md`: new — step-by-step ML training guide covering Tier 1–3 training, calibration, and injection-recovery validation.
- 660 tests total (77 new); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.16.0.

## v0.15.0

- `orbit.py`: added `compute_orbital_period(elements)` — Kepler's third law; T = 365.25 × √(a³) days; returns 0.0 for non-positive a.
- `link.py`: added `filter_high_motion(tracklets, min_rate_arcsec_hr)` — return tracklets exceeding a motion-rate threshold; default 10 arcsec/hr.
- `score.py`: added `followup_priority_table(neos)` — flat ranked list of dicts with rank, object_id, hazard_flag, pathway, priority, MOID, neo_class, n_obs, arc_days, motion_rate.
- `classify.py`: added `batch_explain(tracklets)` — run `explain_classification` on a list of tracklets; return list of dicts.
- `alert.py`: added `alert_summary_table(neos)` — flat per-NEO alert summary (no submissions triggered); keys include ready_to_submit.
- `fetch.py`: added `summarise_fetch_result(result)` — summary dict with n_alerts, surveys, search_ra/dec/radius, start/end JD, limiting_magnitude.
- `preprocess.py`: added `flag_saturated_sources(result, saturation_mag)` — return obs_ids of sources brighter than saturation_mag.
- `schemas.py`: added `CandidateSummary` — lightweight frozen Pydantic model for display/export.
- `Skills/filter_candidates.py`: new — filter scored NEO JSON by hazard flag, alert pathway, or minimum priority.
- `Skills/summarise_run.py`: new — print or JSON-export a pipeline run summary from scored NEO JSON.
- `Skills/plot_sky_coverage.py`: new — RA/Dec scatter plot of tracklet positions colour-coded by hazard flag (requires matplotlib).
- `docs/API_REFERENCE.md`: updated with all v0.14.0 and v0.15.0 public APIs.
- 583 tests total (55 new); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.15.0.

## v0.14.0

- `orbit.py`: added `close_approach_table(elements, jd_start, jd_end, n_steps)` — tabulate geocentric distance, RA/Dec, and heliocentric distance over a time window at uniform steps; added to `__all__`.
- `link.py`: added `estimate_motion_uncertainty(tracklet)` — propagate formal astrometric uncertainties through the linear motion fit to produce rate and PA error estimates; added to `__all__`.
- `score.py`: added `discovery_report(neo)` — comprehensive nested summary dict for human review and export; added to `__all__`.
- `classify.py`: added `explain_classification(tracklet)` — structured classification breakdown with Tier 1 feature importances, dominant hypothesis, and confidence; added to `__all__`.  Fixed Pydantic v2.11 deprecation in `model_fields` access.
- `alert.py`: added `draft_mpc_submission(neo, obs_code)` — complete MPC submission bundle with cover letter and guardrail text; added to `__all__`.
- `schemas.py`: added `ObservationWindow` — frozen typed model for sky/time search queries; added to `__all__`.
- `fetch.py`: added `estimate_limiting_magnitude(fetch_result)` — 5-sigma depth proxy from the 90th–99th percentile of detected magnitudes; added to `__all__`.
- `preprocess.py`: added `quality_summary(result)` — per-field quality statistics (PSF quality, background RMS, elongation, pass fraction); added to `__all__`.
- `detect.py`: added `streak_candidates(detect_result)` — filter a `DetectResult` for streak/trail detections only; added to `__all__`.
- `background.py`: added `audit_report(db_path)` — consolidated cross-log audit report covering runs, reviews, signoff coverage, and integrity; added to `__all__`.
- `Skills/generate_obs_schedule.py`: generate a prioritized follow-up observation schedule with urgency tiers and recommended exposure times.
- `Skills/photometric_calibration.py`: per-field photometric zero-point fit and magnitude correction via Gaia DR3 reference stars.
- `Skills/export_mpc_bulk.py`: bulk export MPC 80-column observation reports for a list of `ScoredNEO` objects to a directory with manifest.
- `docs/SCORING_MODEL.md`: updated with ranking, discovery report, motion uncertainty, close-approach table, and photometric calibration sections.
- 63 new tests; 528 total; 100% coverage maintained.
- Version bumped to 0.14.0.

## v0.13.0

- `fetch.py`: added `fetch_batch(targets, radius_deg, start_jd, end_jd, ...)` — fetch multiple sky positions in one call; added to `__all__`.
- `preprocess.py`: added `preprocess_batch(fetch_results, apply_astrometry)` — batch preprocessing from a list of `FetchResult` objects; added to `__all__`.
- `detect.py`: added `detect_batch(preprocess_results, ...)` — batch detection from a list of `PreprocessResult` objects; added to `__all__`.
- `link.py`: added `merge_tracklets(a, b)` — merge two tracklets into a longer arc, deduplicating by `obs_id`; added to `__all__`.
- `orbit.py`: added `propagate_orbit(elements, dt_days)` — two-body Keplerian propagation of orbital elements; added to `__all__`.
- `orbit.py`: added `predict_ephemeris(elements, jd)` — approximate geocentric RA/Dec prediction at a target JD; added to `__all__`.
- `orbit.py`: added `_kepler_equation` helper (internal; covered by tests).
- `score.py`: added `rank_candidates(neos)` — sort `ScoredNEO` list by descending discovery priority with PHA tier; added to `__all__`.
- `alert.py`: added `generate_alert_package(neo, obs_code)` — bundle MPC report, MPC JSON, summary, and metadata into a single dict; added to `__all__`.
- `schemas.py`: added `PipelineResult` — immutable top-level container for a complete pipeline run; added to `__all__`.
- `Skills/simulate_survey.py`: generate synthetic ZTF-like survey observations for a sky field.
- `Skills/export_ranked_table.py`: export a ranked `ScoredNEO` table to CSV or HTML.
- `Skills/check_orbit_quality.py`: check orbit quality and fit preliminary orbit for tracklets from a JSON file.
- `tests/conftest.py`: extended with `build_raw_candidate`, `build_scored_neo`, `raw_candidate` fixture, `scored_neo` fixture.
- `docs/PIPELINE_SPEC.md`: updated with all v0.13.0 batch APIs, new orbit utilities, `PipelineResult`, and updated running examples.
- 54 new tests; 465 total; 100% coverage maintained.
- Version bumped to 0.13.0.

## v0.12.0

- `link.py`: added `_is_satellite_trail` filter — rejects candidate pairs with purely E-W or N-S motion at rate ≥ 30 arcsec/hr as probable satellite/debris trails.
- `classify.py`: added `classify_batch(tracklets, ...)` — classifies a list of tracklets in one call, loading models once; added to `__all__`.
- `classify.py`: added `get_tier1_feature_importances(model_path)` — loads XGBoost model and returns normalised gain-based feature importances; returns `None` on load failure; added to `__all__`.
- `orbit.py`: added `arc_quality_report(tracklet)` — returns arc quality dict with `arc_days`, `n_observations`, `n_nights`, `quality_code` (1–4), `arc_warning`, `recommended_action`; added to `__all__`.
- `score.py`: added `score_batch(items, pipeline_run_id)` — scores a list of classified tracklets in one call; added to `__all__`.
- `score.py`: `ScoringMetadata.close_approach_au` now populated with MOID value when orbit quality ≥ 2 (else `None`).
- `schemas.py`: added `close_approach_au: float | None = None` field to `ScoringMetadata`.
- `alert.py`: added `format_mpc_json(neo, obs_code)` — returns MPC JSON submission dict; added to `__all__`.
- `alert.py`: added `batch_process_alerts(neos, dry_run, mpc_obs_code)` — processes list of ScoredNEOs through alert protocol with per-item exception handling; added to `__all__`.
- `Skills/validate_mpc_report.py`: validate MPC 80-column observation reports for line length, date/RA/Dec format, and observatory code; CLI with `--json` flag.
- `Skills/diagnose_pipeline.py`: run each pipeline stage with synthetic data and report pass/fail with elapsed time; CLI with `--json` flag.
- `Skills/compare_baselines.py`: compare two injection-recovery JSON baselines; exits 1 on regression; CLI with `--json` flag.
- `docs/API_REFERENCE.md`: updated with all v0.12.0 public APIs (`classify_batch`, `get_tier1_feature_importances`, `retrain_tier1`, `retrain_stacker`, `format_mpc_json`, `batch_process_alerts`, `monitor_neocp`, `score_batch`, `arc_quality_report`, `close_approach_au`, `force_refresh`, satellite trail filter note).
- 34 new tests; 411 total; 100% coverage maintained.
- Version bumped to 0.12.0.

## v0.11.0

- `link.py`: added `_predict_from_arc` (quadratic polyfit for ≥3 obs, linear fallback for 2); replaces constant-velocity extrapolation when arc has grown.
- `link.py`: fixed chi² error proxy — raised astrometric uncertainty floor from 0.1 arcsec to 0.5 arcsec; injection-recovery link rate 62% → 96%.
- `fetch.py`: added `force_refresh: bool = False` parameter to `fetch`, `fetch_ztf`, `fetch_atlas`; added `ATLAS_TOKEN` environment-variable fallback for ATLAS authentication.
- `alert.py`: added public `monitor_neocp(object_id, max_wait_hr, poll_interval_hr, _sleep_fn)` blocking poll loop; preserved `_monitor_neocp` single-shot for process_alert.
- `classify.py`: added `retrain_tier1(csv_path, model_path)` for XGBoost retraining from labelled CSV; outputs JSON training report.
- `classify.py`: added `retrain_stacker(tier1_outputs, labels, model_path)` for logistic-regression stacker retraining; serialises coefficients to JSON.
- `Skills/run_pipeline.py`: added `--neocp-timeout-hours`, `--neocp-poll-interval`, `--force-refresh`, `--atlas-token` CLI flags.
- `Skills/stress_test_high_motion.py`: 3-bin motion stress test (1–10, 10–30, 30–60 arcsec/hr); asserts ≥60% link in highest-motion bin; saves baseline JSON.
- `Skills/build_cutout_dataset.py`: build `.npz` cutout dataset from ZTF alert JSON; compatible with `train_tier2_cnn.py`.
- `Skills/build_sequence_dataset.py`: build flat CSV sequence dataset from tracklet JSON; compatible with `train_tier3_transformer.py`.
- `Skills/train_tier2_cnn.py`: updated to read `cutout_path` column pointing to `.npz` files.
- `Skills/train_tier3_transformer.py`: updated to read flat `tok_i_j` columns from sequence CSV.
- `Skills/smoke_test.py`: added smoke checks for `monitor_neocp`, `retrain_tier1`, `retrain_stacker`.
- `Skills/check_mpc_known.py`: added `check_neocp(object_ids)` function and `--neocp` CLI flag.
- `data/injection_recovery_n200.json`: n=200 injection-recovery baseline (seed=42).
- `tests/test_fetch.py`: added `@pytest.mark.integration_live` tests for ZTF and ATLAS live endpoints.
- 30 new tests; 376 total; 100% coverage maintained.
- Version bumped to 0.11.0.

## v0.10.0

- Removed deprecated background wrapper scripts in favor of `Skills/background.py`.
- Added versioned background target manifests and `background/config.schema.json`.
- Added signoff readiness, unsigned follow-up, run detail, and target history audit views.
- Preserved manual-first operation with top-level SQLite logs and no external submission side effects.
- Added regression coverage for the unified CLI, manifest loading, wrapper removal, and report readiness.
- Version bumped to 0.10.0.

## v0.9.0

- `link.py`: fixed prediction bug — `_predict_position` now uses `obs_c.jd` instead of integer night key; link rate 2% → 62%.
- `Skills/tune_linker.py`: parametric sweep of `position_tolerance_arcsec` × `chi2_threshold` vs link/score rate.
- Added 4 new tests (prediction-fix regression + arc_below_min_obs + tune_linker smoke); 328 total; 100% coverage.
- Injection-recovery baseline updated: 62% link rate (n=50, seed=42).
- Version bumped to 0.9.0.

## v0.8.0

- `classify.py`: added `_build_ensemble` (sklearn LogisticRegression meta-learner) + `ensemble_predict` public API.
- `Skills/injection_recovery.py`: added `--json PATH` flag to save results as JSON.
- Saved baseline injection-recovery run to `data/injection_recovery_baseline.json`.
- Added 8 new tests; 324 total; 100% coverage maintained.
- Version bumped to 0.8.0.

## v0.7.0

- `fetch.py`: raised coverage 75% → 100% via mocks for `ztfquery`, ATLAS network, `astroquery.mpc`, `jplhorizons`.
- CI coverage gate raised from 95% → 100%; actual coverage 100.00%.
- New Skills: `benchmark_pipeline.py`, `train_tier2_cnn.py`, `train_tier3_transformer.py`.
- New infra: `.github/ISSUE_TEMPLATE/` (bug + feature request templates), `models/` directory.
- Version bumped to 0.7.0.

## v0.6.0

- `torch` installed; CNN (Tier 2) and Transformer (Tier 3) paths fully tested (100% `classify.py` coverage).
- `alert.py`: `process_alert` now accepts `cneos_assessment` parameter for PDCO path testing.
- CI coverage gate raised from 85% → 95%; actual coverage 97.44%.
- Added 40 new tests across orbit, detect, preprocess, calibration, classify, alert modules.
- Version bumped to 0.6.0.

## v0.5.0

- `calibration.py`: Platt and isotonic PAVA calibrators with `.predict()` API.
- Added `Skills/evaluate_calibration.py` for Brier/ECE evaluation.
- Full test coverage for calibration module.
- Version bumped to 0.5.0.

## v0.4.0

- `score.py`: Bayesian log-score model over 5 hypotheses; `HazardAssessment` with `pha_candidate` / `close_approach` / `nominal` / `unknown` flags.
- `alert.py`: MPC 80-column report formatter; mandatory 3-step alert protocol (MPC → NEOCP → NASA PDCO).
- Added `Skills/batch_score.py`, `Skills/export_mpc_report.py`.
- Version bumped to 0.4.0.

## v0.3.0

- `orbit.py`: Gauss's method orbit determination + differential correction; MOID via simplified Öpik method; orbit quality codes 1–4.
- `classify.py`: three-tier ML pipeline (XGBoost tabular + CNN image + Transformer sequence) + stacking ensemble.
- Added `Skills/run_pipeline.py`, `Skills/injection_recovery.py`.
- Version bumped to 0.3.0.

## v0.2.0

- `link.py`: THOR-inspired pair-and-propagate tracklet linker; ≥2 nights / ≥3 obs requirement; chi² orbit consistency gate.
- `detect.py`: real/bogus filtering; moving-source identification; MPC cross-match.
- `preprocess.py`: difference-image validation; cutout normalisation; optional Gaia DR3 astrometric correction.
- Added `Skills/smoke_test.py`, `Skills/visualize_tracklets.py`, `data/sample_tracklets.json`.
- Version bumped to 0.2.0.

## v0.1.0

- Initial project scaffold: `schemas.py` with all Pydantic v2 frozen data models.
- `fetch.py`: ZTF (ztfquery + IRSA TAP fallback), ATLAS forced-photometry, MPC known-object, JPL Horizons ephemeris fetchers with disk cache.
- `pyproject.toml`, `CLAUDE.md`, `AGENTS.md`, `docs/` (PIPELINE_SPEC, SCORING_MODEL, DATA_SOURCES, API_REFERENCE).
- CI (GitHub Actions) with ruff, mypy, pytest on Python 3.11 & 3.12.
- Version 0.1.0.
