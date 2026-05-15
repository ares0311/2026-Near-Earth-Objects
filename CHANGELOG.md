# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

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
