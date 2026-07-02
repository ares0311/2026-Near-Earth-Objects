# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## v0.90.14 — Record first live Phase 0 probe results (2026-07-02)

### Added
- `docs/evidence/phase0/2026-07-02-first-live-probe-console.md`: durable
  record of the operator's first live `Skills/verify_ztf_dr24_sources.py`
  run. IRSA ZTF image metadata confirmed reachable without credentials
  (HTTP 200). JPL SBDB and MPC get-obs are reachable but rejected the
  brief's example request (HTTP 400 / 501 respectively) — root cause not
  yet diagnosed, awaiting response bodies. Fink schema/swagger failed with
  a TLS handshake error (`SSLEOFError`), not a 4xx — inconclusive, not yet
  attributable to "no public access."

### Changed
- `CLAUDE.md`: handoff updated with the live probe results and the explicit
  next step (get the full response bodies before adjusting any brief-cited
  URL or writing ingestion code against it).

## v0.90.13 — Phase 0 source-verification tool for ZTF DR24 pipeline (2026-07-02)

### Added
- `Skills/verify_ztf_dr24_sources.py`: GET-only probe of the exact endpoints
  cited in `docs/neo_discovery_agent_brief.md` (Fink schema/swagger, JPL
  SBDB NEO query, MPC get-obs, IRSA ZTF image metadata). Checkpoint/resume
  and retry-with-backoff per standing directives. Writes
  `docs/evidence/phase0/data_sources_verified.md` and `auth_requirements.md`
  from real observed HTTP responses — no invented URLs or schemas.
- Dry-run logic verified locally with mocked HTTP responses (report
  generation, checkpoint/resume, and probe-list wiring all confirmed
  correct); this coding-agent sandbox's network proxy blocks these external
  domains at the policy level, so the actual live probes require the
  operator's Mac.

## v0.90.12 — MAJOR PIVOT: ZTF DR24 historical replay supersedes WISE/DECam/TESS (2026-07-02)

### Changed (operator decision)
- `docs/MISSION.md`: rewritten. `docs/neo_discovery_agent_brief.md` now
  supersedes the 2026-07-01 reconciliation that kept WISE/DECam/TESS
  primary. ZTF DR24 archival historical replay (time-aware known-object
  exclusion, Fink-FAT-style tracklet linking, LightGBM/XGBoost candidate
  ranker, retrospective validation) is now the primary discovery path.
  WISE/DECam/TESS code and Gate P1–P5 evidence are preserved as a
  secondary/paused path, not deleted.
- `CLAUDE.md`, `AGENTS.md`: DECISION-001 marked superseded; global-survey
  source list and handoff notes updated; new handoff blocks record the
  pivot and an explicit self-correction that closing the WISE/DECam/TESS
  gate register does not establish readiness for the new pipeline.
- `docs/PRODUCTION_READINESS.md`: pivot notice added. The P1–P5 gate
  register describes the now-secondary pipeline; new gates are required for
  ZTF DR24 historical replay before it can be called production-capable.
- `README.md`: pivot notice added to the abstract; architecture description
  clarified as describing the secondary path.

### Unchanged (explicitly)
- Live ZTF alert-stream and live ATLAS discovery remain prohibited — still
  circular, since ZTF ZAPS/ATLAS already process and submit from those
  streams in real time. Only bounded, time-aware *archival* ZTF DR24
  reprocessing is newly permitted.
- No code was changed in this release — this is a strategy/documentation
  pivot. Phase 0 source verification (per the brief) is the next step
  before any ZTF DR24 ingestion code is written.

## v0.90.11 — Correct Gate P4 framing: dormant, not an active operator task (2026-07-02)

### Fixed
- `docs/PRODUCTION_READINESS.md`, `docs/OPERATOR_GO_NO_GO_RUNBOOK.md`,
  `CLAUDE.md`, `AGENTS.md`, `README.md`, `docs/evidence/prod-loop/LOOP_PROGRESS.md`:
  corrected language that described Gate P4 (MPC submission protocol) as an
  active task requiring the operator to contact MPC now. There is no
  candidate yet, so there is nothing to submit and nothing to ask MPC about.
  Gate P4 is dormant and only activates once a real WISE-sourced candidate
  survives adversarial review and operator review. No code changed — this is
  a documentation/framing correction only, flagged by the operator.

## v0.90.10 — Gate P5 operator go/no-go runbook (2026-07-02)

### Added
- `docs/OPERATOR_GO_NO_GO_RUNBOOK.md`: one-page operator flow for the day a
  real candidate appears — review-packet location, the exact
  `Skills/adversarial_review.py` and `Skills/export_ades_report.py` commands
  (verified against the Gate P3 drill), an operator-review checklist, the
  Gate P4 human-gated MPC-authority check, and the permanent
  forbidden-communications list. States explicitly that
  `SURVIVE`/`BORDERLINE` means "candidate may be reviewed for MPC
  submission," never "confirmed NEO."

### Changed
- `docs/PRODUCTION_READINESS.md`: Gate P5 marked CLOSED. Production
  capability gates P1, P2, P3, and P5 are now all closed; only Gate P4 (MPC
  submission protocol) remains open, and it is human-gated.

## v0.90.9 — Gate P3 no-submission package drill (2026-07-02)

### Added
- `Skills/injection_recovery.py`: `--review-packet-out PATH` flag writes full
  `ScoredNEO` packets from injection runs (same format as
  `Skills/run_pipeline.py --review-packet-out`), so a Gate P1 positive-control
  run can directly feed a Gate P3 drill without a live sky run.
- `docs/evidence/prod-loop/2026-07-02-gate-p3-no-submission-drill.md`: records
  a full drill — 5 synthetic WISE packets through `Skills/adversarial_review.py
  --offline` (5/5 REJECT, expected for a packet with no real/bogus score) and
  `Skills/export_ades_report.py` twice (default args, then `--obs-code C51`
  without the confirmation flag), both failing closed with no `.psv` file
  written and no network access at any step.

### Changed
- `docs/PRODUCTION_READINESS.md`: Gate P3 (no-submission package drill)
  marked CLOSED. Gate P4 (MPC submission protocol) is next and is
  human-gated.

## v0.90.8 — Gate P2 survey-native confidence policy (2026-07-02)

### Added
- `docs/SURVEY_NATIVE_CONFIDENCE_POLICY.md`: source-verification matrix for
  WISE/DECam/TESS (WISE live-verified across many runs; DECam/TESS
  code-complete but never live-verified), a table of quantitative confidence
  thresholds already enforced in `detect.py`/`link.py`/`score.py`, the
  no-future-catalog-leakage statement for the current live-discovery
  pipeline, ZTF/Fink/SNAPS reference-only reaffirmation, and the
  pretrained-model-audit requirement for future work.
- `Skills/run_pipeline.py`: prints an operator-visible `[fetch] WARNING` when
  `--surveys DECam` or `--surveys TESS` is selected, since DECam is
  unverified against its live endpoint and TESS returns TIC reference-catalog
  star positions rather than genuine per-epoch FFI detections.

### Changed
- `docs/PRODUCTION_READINESS.md`: Gate P2 (survey-native confidence policy)
  marked CLOSED.

## v0.90.7 — Fold discovery-agent brief into production workflow (2026-07-02)

### Changed
- `docs/neo_discovery_agent_brief.md` is now part of the authoritative project
  workflow. `docs/MISSION.md` reconciles the brief with the active
  WISE/DECam/TESS production discovery path.
- `CLAUDE.md` and `AGENTS.md` now require agents to read the discovery-agent
  brief at session start.
- Gate P2 in `docs/PRODUCTION_READINESS.md` now requires source-verification,
  no-future-catalog-leakage, historical-replay, and pretrained-model audit
  practices from the brief.

### Safety
- ZTF/Fink/SNAPS are treated as methodology, benchmark, and ranker-validation
  references unless a future documented decision proves a non-duplicative
  discovery-submission path.
- No external submission path was enabled.
- No impact-probability claims or confirmed-object claims were introduced.

## v0.90.6 — Gate P1 WISE discovery-source positive control (2026-07-02)

### Added
- `Skills/injection_recovery.py`: `--survey WISE` mode injects a source-native
  NEOWISE-visit-cadence synthetic tracklet (single-epoch W1 exposures, no
  native real/bogus score, ~1 arcsec astrometric jitter, 0.08 mag photometric
  noise) through the real `detect.py` discovery-archive singleton path,
  `link.py`, `classify.py`, and `score.py`. Verified 100% detection/link/score
  recovery (n=50, seed=42); baseline committed at
  `data/injection_recovery_wise_baseline.json`.
- `.github/workflows/e2e.yml`: new `wise-injection` job runs the WISE
  positive control on every push/PR and fails closed if recovery drops to 0.

### Changed
- `docs/PRODUCTION_READINESS.md`: Gate P1 (discovery-source positive control)
  marked CLOSED with evidence at
  `docs/evidence/prod-loop/2026-07-02-gate-p1-wise-injection-recovery.md`.
  Gate P2 (survey-native confidence policy) remains open.

## v0.90.5 — WISE parent-field probe selector (2026-06-30)

### Added
- `Skills/select_survey_fields.py --wise-archive-probes` now adds
  directive-compliant WISE/NEOWISE scale-plan probe commands to ranked field
  selections.
- The generated probe commands use `caffeinate -i`, Python 3.14 through
  `uv run`, bounded native numerical threads, dry-run pipeline execution, and
  `--link-scale-plan-out` so new parent fields are measured before full D1
  diagnostics.
- Offline tests now cover WISE probe command generation, metadata preservation,
  JSON CLI output, and required archive-window validation.

### Safety
- No external submission path was enabled.
- No impact-probability claims or confirmed-object claims were introduced.

## v0.90.4 — D1 motion-floor alignment (2026-06-30)

### Changed
- `detect.py`, `link.py`, and `Skills/audit_real_run.py` now use the same
  `0.05 arcsec/hr` lower motion floor as adversarial review and
  `docs/MISSION.md`.
- `src/background.py` now lazy-loads heavy classify/orbit/score stages so
  metadata-only background CLI commands do not time out during cold subprocess
  startup.
- D1 handoff docs now explicitly say the Taurus v0.90.3 subfields are exhausted
  and should not be rerun.

### Safety
- No external submission path was enabled.
- No impact-probability claims or confirmed-object claims were introduced.

## v0.90.3 — D1 review-packet and scale-plan guardrails (2026-06-29)

### Added
- `Skills/run_pipeline.py --link-scale-plan-out` now ranks recommended
  diagnostic subfields by local cross-night seed-pair support and records
  `support_metrics` showing whether each subfield can support at least three
  observations across at least two nights.
- `Skills/run_pipeline.py --review-packet-out` now prints the number of full
  `ScoredNEO` packets written and explicitly tells the operator to skip
  adversarial review when the packet file is empty.

### Changed
- D1 WISE diagnostic guidance now distinguishes empty packet artifacts from
  reviewable adversarial-review inputs, preventing another failed review step on
  a no-tracklet run.
- Version metadata now records `0.90.3` in `pyproject.toml`, `src.__version__`,
  `uv.lock`, and the roadmap documents.

### Safety
- No external submission path was enabled.
- No impact-probability claims or confirmed-object claims were introduced.

## v0.90.2 — WISE diagnostic subfields and test-hang cleanup (2026-06-29)

### Added
- Link scale plans now include a budget-derived diagnostic radius, recommended
  subfield parameters, and explicit warnings that diagnostic subfields are not
  complete-field tiling evidence.

### Changed
- `Skills/tune_linker.py` now uses a deterministic synthetic posterior for
  linker sweeps, avoiding unnecessary Tier 3 Transformer/PyTorch initialization
  in lightweight smoke tests.
- `uv.lock` now records the local package version as `0.90.2`, matching
  `pyproject.toml`, `src.__version__`, and the roadmap documents.

### Safety
- No external submission path was enabled.
- No impact-probability claims or confirmed-object claims were introduced.

## v0.90.1 — WISE submission authority and scale-plan hardening (2026-06-29)

### Added
- WISE/NEOWISE ADES export now defaults to ADES `A22`, applies MPC station
  code `C51` only behind explicit recorded MPC confirmation, and adds ADES
  note `Z` for archival survey astrometry reported by this non-survey pipeline.
- `Skills/run_pipeline.py --link-scale-plan-out` writes diagnostic JSON with
  top night-pair and sky-cell contributors when the link seed-pair budget fails
  closed.

### Changed
- Expected link seed-budget stops now exit cleanly with audit/output artifacts
  instead of printing an unhandled traceback.
- D1 WISE production-loop handoff now records the `11786731` seed-pair
  full-window scale-plan result and directs the next run toward smaller
  WISE diagnostics selected from the dominant night pairs.

### Safety
- No external submission path was enabled.
- No impact-probability claims or confirmed-object claims were introduced.

## v0.90.0 — Discovery archive live-readiness hardening (2026-06-28)

### Added
- Discovery archive fetch layer for WISE/NEOWISE, DECam/NOIRLab, and TESS FFIs,
  with ZTF and ATLAS kept as training-data sources rather than discovery streams.
- WISE/NEOWISE async TAP polling compatibility for pyvo versions that expose
  `_update()` instead of public `update()`, while preserving live heartbeat
  output.
- Linker provenance diagnostics for zero-tracklet production runs: nights,
  observations, seed-pair totals, rate-window seeds, satellite rejects,
  min-observation/min-night rejects, and chi-square rejects.
- Durable live evidence for the WISE Taurus diagnostics, including the
  one-night failure mode and full-year/narrow-radius night-count probes.

### Changed
- `Skills/run_pipeline.py` defaults to the WISE discovery path and remains
  fail-closed for MPC submission unless a real observatory-code strategy and
  explicit approval are present.
- WISE ADQL now prefilters the broad NEOWISE point-source archive using IRSA
  association columns (`sso_flg`, `allwise_cntr`, `n_allwise`, `source_id`) to
  keep known solar-system associations and AllWISE-unmatched rows.
- Discovery archive rows from WISE/DECam/TESS are preserved as singleton
  candidates for multi-night linking instead of being discarded by same-night
  pair requirements.
- README, package metadata, and readiness docs now align on `v0.90.0`.

### Safety
- No external submission path was enabled.
- No impact-probability claims or confirmed-object claims were introduced.

## v0.89.3 — Adversarial review + discovery paper pathway (2026-06-26)

### Added
- `Skills/adversarial_review.py`: adversarial challenge battery that tries to REJECT
  scored NEO candidates before any operator review or external submission. Runs 11
  offline challenges (orbit quality, arc length, multi-night, real/bogus gate,
  known-object posterior, artifact posterior, NEO dominance, MBA confusion, motion
  rate plausibility, MOID-arc consistency, motion consistency) plus 2 optional live
  challenges (MPC field scan, ATLAS cross-survey confirmation). Verdicts: SURVIVE /
  BORDERLINE / REJECT. Exit codes 0/1/2 for automation. `--offline` and `--json` flags.
- `tests/test_adversarial_review_skill.py`: 50+ test cases covering every offline
  challenge PASS/WARNING/FAIL branch, live challenges via monkeypatch, aggregate verdict
  logic, and CLI entry point.
- `docs/MPC_SUBMISSION_POLICY.md §Two-Stage Review Process`: documents the new discovery
  paper pathway — Pipeline → Adversarial Review → Operator Review → MPC → paper.

### Changed
- `CLAUDE.md`: handoff state updated to reflect discovery paper goal (operator-confirmed
  2026-06-26 by Jerome W. Lindsey III), two-stage review workflow, and adversarial review
  implementation status.
- `docs/MPC_SUBMISSION_POLICY.md §Submission Gates`: added note that pipeline gates are
  necessary but not sufficient — adversarial review and operator review are also required.
- `docs/evidence/prod-loop/LOOP_PROGRESS.md`: goal updated from citizen-science reporting
  to defensible discovery paper; outstanding work items H–K added.

---

## v0.89.2 — Console output elapsed+ETA compliance + adversarial test fixes (2026-06-26)

### Fixed
- `Skills/run_pipeline.py`: every stage print now includes `elapsed {M}m{S:02d}s`.
  The fetch stage was previously a single silent blocking call for the full
  duration of network I/O (observed: 5+ minutes with no output). Restructured to
  loop over surveys one-by-one, emitting `(N/M) Starting <survey>` before each
  call and `(N/M) <survey>: X alerts  elapsed Xm Xs  ETA Xm Xs` after, where ETA
  is computed from actual time-per-survey (the measurable quantity required by
  CLAUDE.md). Per-tracklet `[classify]` prints also include ETA from real
  time-per-tracklet. All other stage prints (`[preprocess]`, `[detect]`, `[link]`,
  `[orbit]`, `[score]`, `[alert]`) include elapsed time. Satisfies the CLAUDE.md
  system directive: "elapsed-only heartbeats are not acceptable as a substitute
  for ETA."
- `tests/test_adversarial.py` (5 failing tests, PR #115):
  - `test_missing_cutout_detection`: `compute_streak_metric` now returns `None`
    (not `0.0`) for observations with no difference cutout.
  - `test_very_fast_neo_links`: Added fourth observation on night 3 so the linker
    has a propagation target beyond the seed pair's two nights.
  - `test_missing_orbital_elements_graceful`: Extended `OrbitQualityCode` from
    `Literal[1,2,3,4]` to `Literal[0,1,2,3,4]` in `schemas.py`.
  - `test_short_arc_blocks_submission`: Added `sys.path` fix so `conftest` is
    importable when running with `PYTHONPATH=src`.
  - `test_run_pipeline_resumes_from_checkpoint` (`test_pipeline.py`): Added
    `ready_for_submission` patch to prevent `MagicMock < int` TypeError.
- `src/detect.py`: `compute_streak_metric` return type changed to `float | None`;
  `filter_by_streak_score` updated to handle `None` streak scores.
- `docs/CONSOLE_OUTPUT_SPEC.md`: updated to document per-stage elapsed format,
  per-survey fetch loop format, and per-tracklet ETA.

### Added
- `tests/test_adversarial.py`: 10 synthetic adversarial test cases (satellite
  trail rejection, missing/corrupted cutouts, extreme motion rates, network
  timeout simulation, survey edge coordinates, duplicate obs IDs, degenerate
  orbital elements, short-arc submission block).
- `docs/evidence/prod-loop/LOOP_PROGRESS.md`: persistent session progress
  tracker for the production loop.

### Changed
- 3600+ tests passing; 100% coverage on Python 3.14; ruff + mypy clean.
- Version bumped to 0.89.2.

---

## v0.89.1 — ZTF ndet cap fix + CI green (2026-06-22)

### Fixed
- `src/fetch.py` (`_fetch_ztf_alerce_api` Mode 1): added `ndet_max=3` and
  `order_mode="ASC"` so the ALeRCE query surfaces single-detection transient
  OIDs (moving objects) instead of persistent background sources (ndet=500+).
- Root cause: moving objects appear as ndet=1 OIDs per night because they move
  ~700 arcsec/night vs the ~1 arcsec OID association radius; the previous
  `ndet_max=None` returned only persistent stationary sources, which the linker
  correctly rejected (0 arcsec/hr rate).
- `max_objects` increased 50 → 200 for broader field coverage.
- 2 regression tests added to prevent re-introduction of `ndet_max=None` bug.

### Changed
- Version bumped to 0.89.1.

---

## v0.89.0 — Python 3.14.6 coverage fixes + T2-C evidence packet (2026-06-20)

### Fixed
- 10 statement-coverage misses exposed by Python 3.14.6's finer-grained tracking
  of `or`/`and` operands and ternary branches (CI was failing with 99.99% coverage):
  - `fetch.py`: `_parse_alerce_detection` non-dict and KeyError paths;
    `_fetch_ztf_irsa_api` RequestException and JSON decode error paths;
    `fetch_atlas` queue-response-missing-url path;
    `fetch_atlas_forced` progress callback, finishtimestamp-no-result, and sleep paths.
  - `alert.py`: `_compute_urgency` high-MOID AND branch.
  - `background.py`: `_kpi_entry` "fail" ternary branch;
    `automation_readiness_summary` LIVE_NETWORK_DISABLED path.
- `.python-version` pinned to `"3.14"` so local `uv sync` works with cpython-3.14.0rc2.

### Added
- `docs/evidence/t2c/2026-06-20-citizen-science-architecture-evidence-packet.md`:
  T2-C evidence packet with ML architecture decisions, calibration KPI results,
  known limitations, and no-submission guardrails. Operator review checklist included.

### Changed
- 3706 tests passing; 100% coverage on Python 3.14.6; ruff + mypy clean.
- Version bumped to 0.89.0.

## [Unreleased]

- Replaced the obsolete human calibration-review requirement with a
  quantitative, fail-closed production promotion gate covering held-out sample
  size, Brier score, ECE, log loss, ROC AUC, cross-validation stability, and
  bootstrap confidence bounds.
- Synchronized the production roadmap with the current repository state:
  credentials, Tier 1 XGBoost, Tier 2 CNN, and the 10,000-alert ZTF dataset are
  complete; real Tier 3 multi-night sequence data remains pending.
- Added bounded, rate-limited, retryable, resumable MPC observation-history
  acquisition for Tier 3, with atomic checkpoints, manifest hashing, provider
  provenance, query outcomes, and explicit no-submission/no-secret safety flags.
- Corrected MPC observation parsing for current Astroquery `epoch` and `DEC`
  columns while retaining compatibility with older fixtures.
- Recorded Jerome W. Lindsey III's 2026-06-10 approval of the five-class Tier 3
  label policy and bounded 50-sequence-per-class pilot.
- Added policy-aware early/late MPC sequence windows, dynamically filtered
  numbered MBA labels, confirmed MPC comet labels, and public ALeRCE
  high-confidence bogus-object histories.
- Upgraded Tier 3 preparation to fail closed on missing provenance, unsafe
  acquisition flags, class imbalance, malformed observations, or designation
  leakage; preparation now emits grouped train/calibration/test splits and a
  machine-readable evidence report.
- Added the optional `training` dependency group for the ALeRCE client and
  refreshed the lockfile.
- 3456 offline tests pass; 2 live checks deselected; ruff and mypy clean.

## v0.87.0 — Option B Cleanup + Production Readiness (2026-06-05)

### Removed
- 68 single-function wrapper Skills scripts added during the v0.77–v0.87 API accumulation cycle. None closed a T1 or T2 production gap. Full list: all `Skills/compute_*.py`, `Skills/estimate_*.py`, `Skills/find_*.py`, `Skills/format_*.py`, `Skills/generate_night_summary.py`, `Skills/group_observations_by_night.py`, `Skills/summarize_alert_pathways.py`, `Skills/filter_priority_candidates.py`, `Skills/get_latest_observation.py`, `Skills/get_faintest_observation.py`, `Skills/count_by_hypothesis.py`, `Skills/estimate_confirmation_times.py`.
- 30 duplicate or near-duplicate documentation files added during the same cycle. Full list: `SCORING_MODEL_V2.md`, `ORBIT_DYNAMICS.md`, `CALIBRATION_METRICS.md`, `DETECTION_STATISTICS.md`, `HAZARD_SCORING.md`, `ORBITAL_MECHANICS.md`, `SCORING_REFERENCE.md`, `CLASSIFICATION_FEATURES.md`, `DATA_PIPELINE_OVERVIEW.md`, `ASTROMETRY_GUIDE.md`, `BATCH_PROCESSING_GUIDE.md`, `CANDIDATE_CLUSTERING.md`, `CANDIDATE_GROUPING_GUIDE.md`, `CLASSIFICATION_TIERS_GUIDE.md`, `DETECTION_FEATURES_GUIDE.md`, `FEATURE_ENGINEERING.md`, `MOTION_ANALYSIS_GUIDE.md`, `OBSERVATION_QUALITY.md`, `OBSERVATION_STATISTICS_GUIDE.md`, `ORBIT_ELEMENTS_REFERENCE.md`, `PHOTOMETRY_GUIDE.md`, `PIPELINE_INTERNALS.md`, `SCORING_PIPELINE_GUIDE.md`, `BATCH_STATISTICS_GUIDE.md`, `ORBIT_VELOCITY_GUIDE.md`, `COMPOSITE_SCORING_GUIDE.md`, `PIPELINE_QUALITY_GUIDE.md`, `SURVEY_STATISTICS_GUIDE.md`, `CLASSIFICATION_METRICS_GUIDE.md`, `FILTERING_AND_DISTRIBUTION_GUIDE.md`.
- 8 test classes in `tests/test_pipeline.py` that tested deleted Skills scripts.

### Added
- `docs/PRODUCTION_READINESS.md` — mandatory session-start read. Defines all T1/T2 production gaps, outside human blockers, production readiness checklist, and compliance rules preventing further API accumulation.

### Changed
- AGENTS.md, README.md, CHANGELOG.md updated to v0.87.0. Test count corrected to 3432.
- CLAUDE.md System Directives updated with production-first gate.
- 3432 tests passing; 100% coverage maintained; ruff + mypy clean.

## v0.77.0–v0.86.0 — API accumulation cycle (2026-06-04 to 2026-06-05)

These ten versions each added 10 new public helper APIs across all 10 pipeline modules (batch statistics, orbital dynamics, survey statistics, classification metrics, calibration helpers), 2 new Skills wrapper scripts, and 1 new doc per version. None of the changes in this cycle closed a T1 or T2 production gap. The wrapper scripts and duplicate docs were removed in the Option B cleanup above.

## v0.76.0

## v0.60.0

- `background.py`: added
  `background_operator_next_action_summary(config_path, db_path, input_path)`
  to schema-gate the operator workflow and recommend the next conservative
  local command.
- `Skills/background.py`: added `operator-next-action` for machine-readable
  next-command triage.
- The operator summary blocks on incomplete SQLite schemas before consulting
  operations snapshots, includes packet-decision readiness for current schemas,
  and preserves no-network/no-external-submission guardrails.
- 3 new tests (2123 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.60.0.

## v0.59.0

- `background.py`: added `background_schema_operations_summary(db_path)` to
  combine schema status, migration preview, packet-decision command readiness,
  and the next safe operator action.
- `Skills/background.py`: added `schema-operations-summary` for read-only
  schema operations triage.
- The operations summary reports whether packet-decision commands are ready and
  recommends `init-log-db` only when the current SQLite schema is incomplete.
- 4 new tests (2120 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.59.0.

## v0.58.0

- `background.py`: added `background_schema_migration_preview(db_path)` to
  preview additive SQLite log migration effects without creating or changing a
  database.
- `Skills/background.py`: added `init-log-db-preview` for no-write operator
  review before running `init-log-db`.
- Migration preview reports missing tables, would-create tables, current schema
  state, the init command, and guardrail flags while preserving no-network,
  no-external-submission, no-signoff, no-packet, and no-report-write behavior.
- 4 new tests (2116 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.58.0.

## v0.57.0

- `background.py`: added `background_schema_status_summary(db_path)` for
  read-only inspection of expected top-level SQLite log tables.
- `background.py`: added `migrate_background_log_db(db_path)` to run the
  additive `init_log_db` migration and report before/after schema state.
- `Skills/background.py`: added `schema-status-summary` and `init-log-db`
  subcommands.
- Schema inspection and migration reports explicitly preserve the no-network,
  no-external-submission, no-signoff, no-packet, and no-report-write
  guardrails.
- 4 new tests (2112 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.57.0.

## v0.56.0

- `background.py`: added `signoff_packet_decision_readiness(db_path)` and
  `latest_undecided_signoff_packet(db_path)` for no-network review of
  persisted packets that still need packet-linked decisions.
- `Skills/background.py`: added `signoff-packet-decision-readiness` and
  `latest-undecided-signoff-packet` subcommands.
- Packet-decision readiness now reports ready, blocked, signed, and already
  decided packet states without recording a signoff, writing a packet, or
  enabling live/external action.
- 5 new tests (2108 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.56.0.

## v0.55.0

- `background.py`: added `record_signoff_from_packet(...)` and
  `signoff_packet_decision_summary(db_path)` to record reviewer decisions from
  persisted internal signoff packets.
- `Skills/background.py`: added `record-signoff-from-packet` and
  `signoff-packet-decision-summary` subcommands.
- `init_log_db`: added top-level SQLite table `signoff_packet_decision_log` for
  packet-linked reviewer decisions and the resulting operations snapshot IDs.
- Packet-based decisions validate the packet, unsigned follow-up state, and
  target/run match before writing a normal human signoff plus decision audit
  row. Each packet decision also records a post-decision operations snapshot
  while keeping network access and external submission disabled.
- 5 new tests (2103 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.55.0.

## v0.54.0

- `background.py`: added `signoff_packet(run_id, db_path)`,
  `latest_unsigned_signoff_packet(db_path)`, `write_signoff_packet(...)`,
  `record_signoff_packet(...)`, and `signoff_packet_log_summary(db_path)` for
  internal human-review packets that do not record signoff decisions.
- `Skills/background.py`: added `signoff-packet`,
  `latest-unsigned-signoff-packet`, `write-signoff-packet`,
  `record-signoff-packet`, and `signoff-packet-log-summary` subcommands.
- `init_log_db`: added top-level SQLite table `signoff_packet_log` for
  persisted signoff packet metadata.
- 5 new tests (2098 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.54.0.

## v0.53.0

- `background.py`: added
  `background_operations_snapshot(config_path, db_path, input_path)`,
  `record_background_operations_snapshot(...)`, and
  `background_operations_snapshot_log_summary(db_path)` to aggregate and persist
  conservative operator-facing background status snapshots.
- `Skills/background.py`: added `operations-snapshot`,
  `record-operations-snapshot`, and `operations-snapshot-log-summary`
  subcommands.
- `validation_summary`: now exposes `total_follow_up` directly for aggregate
  operation-state consumers.
- 4 new tests (2093 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.53.0.

## v0.52.0

- `background.py`: added
  `record_blueprint_compliance_summary(db_path, input_path)` and
  `blueprint_compliance_log_summary(db_path)` to persist background blueprint
  compliance snapshots in top-level SQLite logs.
- `Skills/background.py`: added `record-blueprint-compliance-summary` and
  `blueprint-compliance-log-summary` subcommands.
- 3 new tests (2089 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.52.0.

## v0.51.0

- `background.py`: added
  `background_blueprint_compliance_summary(db_path, input_path)` to audit the
  background automation implementation against
  `BACKGROUND_SEARCH_AUTOMATION_BLUEPRINT.md`.
- `Skills/background.py`: added `blueprint-compliance-summary` subcommand.
- Follow-up report drafts now explicitly include uncertainty language alongside
  negative evidence and limitations.
- 3 new tests (2086 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.51.0.

## v0.50.0

- Added 10 public APIs across alert, calibration, classify, detect, fetch, link,
  orbit, preprocess, schemas, and score modules, including close-approach
  bulletins, calibration resolution, ensemble agreement, known PHA fetches,
  longest-tracklet selection, campaign summaries, and priority percentiles.
- Added `Skills/fetch_known_phas.py`, `Skills/find_longest_tracklet.py`, and
  `docs/SCHEMA_REFERENCE.md`.
- 2083 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.50.0.

## v0.49.0

- Added 10 public APIs for mission observation counts, mean calibration error,
  class probability ranges, angular separation, field overlap, tracklet
  completeness, orbital arc quality, cutout peak positions, and hazard
  summaries.
- Added `Skills/compute_field_overlap.py`,
  `Skills/compute_hazard_summary.py`, and `docs/ALERT_PATHWAY_GUIDE.md`.
- Version bumped to 0.49.0.

## v0.48.0

- Added 10 public APIs for NEOCP submission formatting, calibration uniformity,
  posterior stability, variability indices, MPC orbit catalogs, tracklet sky
  density, Earth Tisserand parameter, source compactness, tracklet clusters,
  and weighted risk scoring.
- Added `Skills/compute_risk_scores.py`,
  `Skills/compute_variability_indices.py`, and
  `docs/DATA_PIPELINE_OVERVIEW.md`.
- 1998 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.48.0.

## v0.47.0

- Added 10 public APIs for discovery reports, calibration drift, Tier 1
  confidence, brightness trends, NEOCP confirmations, consecutive motion,
  aphelion distance, PSF asymmetry, night summaries, and survey completeness.
- Added `Skills/compute_aphelion_distances.py`,
  `Skills/generate_night_summary.py`, and `docs/CLASSIFICATION_FEATURES.md`.
- 1948 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.47.0.

## v0.46.0

- Added 10 public APIs for ADES PSV export, reliability scoring, posterior
  updates, field source counts, known NEO lists, tracklet arc nights,
  perihelion distance, radial profiles, observation coverage, and priority
  ranks.
- Added `Skills/compute_priority_ranks.py`, `Skills/export_ades_report.py`,
  and `docs/SCORING_REFERENCE.md`.
- Version bumped to 0.46.0.

## v0.45.0

- Added 10 public APIs for observation logs, expected positive rate, NEO class
  distribution, cadence, MPC orbit elements, motion-rate filtering, orbital
  velocity, streak angle, residual summaries, and hazard grades.
- Added `Skills/compute_hazard_grades.py`,
  `Skills/compute_orbital_velocity.py`, and `docs/ORBITAL_MECHANICS.md`.
- Version bumped to 0.45.0.

## v0.44.0

- Added 10 public APIs for alert age, resolution score, class entropy summary,
  detection gaps, NEOCP object retrieval, inter-night gaps, mean anomaly at JD,
  cutout symmetry, astrometric residuals, and weighted hazard scoring.
- Added `Skills/compute_mean_anomaly.py`,
  `Skills/compute_weighted_hazard_scores.py`, and `docs/HAZARD_SCORING.md`.
- 1797 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.44.0.

## v0.43.0

- Added 10 public APIs for ready-to-submit counts, discrimination score, Tier 1
  score distribution, angular velocity, known NEO ephemerides, velocity
  dispersion, inclination class, image gradients, observation clusters, and
  arc-quality bonuses.
- Added `Skills/compute_orbital_inclination_class.py`,
  `Skills/compute_tier1_score_distribution.py`, and
  `docs/DETECTION_STATISTICS.md`.
- 1746 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.43.0.

## v0.42.0

- Added 10 public APIs for bulk summaries, Brier skill score, class entropy
  stats, streak density, field completeness, night span, longitude of
  perihelion, cutout contrast, ephemeris points, and weighted priority.
- Added `Skills/compute_weighted_priority.py`,
  `Skills/estimate_field_completeness.py`, and `docs/CALIBRATION_METRICS.md`.
- Version bumped to 0.42.0.

## v0.41.0

- Added 10 public APIs for alert-flag counts, calibration sharpness, batch
  morphology, magnitude filtering, recent MPC NEO retrieval, tracklet quality,
  mean motion, pixel histograms, survey statistics, and combined priority.
- Added `Skills/compute_combined_priority.py`, `Skills/fetch_recent_neos.py`,
  and `docs/ORBIT_DYNAMICS.md`.
- 1621 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.41.0.

## v0.40.0

- Added 10 public APIs for true anomaly, observation depth, position-angle
  consistency, calibration gain, close-approach scoring, candidate dossiers,
  Pan-STARRS moving objects, background level, candidate reports, and average
  precision.
- Added `Skills/compute_true_anomaly.py`,
  `Skills/export_candidate_dossiers.py`, and `docs/SCORING_MODEL_V2.md`.
- 1550 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.40.0.

## v0.39.0

- Added 10 public APIs for eccentric anomaly, source extent, great-circle
  residuals, confusion matrices, size estimates, follow-up windows, CSS
  alerts, cutout entropy, orbital summaries, and F1 score.
- Added `Skills/compute_eccentric_anomaly.py`,
  `Skills/analyze_field_detections.py`, and `docs/CALIBRATION_GUIDE.md`.
- 1439 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.39.0.

## v0.38.0

- `background.py`: added
  `record_live_dry_run_operator_handoff(config_path, db_path, report_dir)` and
  `live_dry_run_operator_handoff_log_summary(db_path)` to write operator
  handoffs and persist them in top-level SQLite logs.
- `Skills/background.py`: added `record-live-dry-run-operator-handoff` and
  `live-dry-run-operator-handoff-log-summary` subcommands.
- 3 new tests (1361 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.38.0.

## v0.37.0

- `background.py`: added `live_dry_run_operator_handoff(config_path)` and
  `write_live_dry_run_operator_handoff(config_path, report_dir)` to render a
  conservative no-network Markdown handoff for operator review.
- `Skills/background.py`: added `live-dry-run-operator-handoff` and
  `write-live-dry-run-operator-handoff` subcommands.
- 4 new tests (1358 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.37.0.

## v0.36.0

- `background.py`: added `record_live_dry_run_approval_bundle(config_path, db_path)`
  and `live_dry_run_approval_bundle_log_summary(db_path)` to persist no-network
  approval-bundle reviews in top-level SQLite logs.
- `Skills/background.py`: added `record-live-dry-run-approval-bundle` and
  `live-dry-run-approval-bundle-log-summary` subcommands.
- 3 new tests (1354 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.36.0.

## v0.35.0

- `background.py`: added `live_dry_run_approval_bundle(config_path)` to
  aggregate scheduler readiness, policy contract validation, provider
  readiness, dry-run planning, and blocker status into one no-network review
  object.
- `Skills/background.py`: added `live-dry-run-approval-bundle` for operator
  review before any mock live dry-run execution attempt.
- 3 new tests (1351 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.35.0.

## v0.34.0

- `Skills/background.py`: added `live-provider-readiness-summary` to expose
  no-network provider readiness from the unified CLI.
- CLI coverage now checks default blocked provider output and approved
  temporary-config readiness with credentials.
- 1 new test (1348 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.34.0.

## v0.33.0

- `Skills/background.py`: added `live-policy-contract-summary` to expose
  no-network live review policy contract validation from the unified CLI.
- CLI coverage now checks both a valid default policy contract and an unsafe
  policy that allows external submission.
- 1 new test (1347 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.33.0.

## v0.32.0

- `background.py`: added `live_policy_contract_summary(config_path)` for
  no-network validation of the live review policy file and schema contract.
- `automation_readiness_summary` and `live_dry_run_plan`: now include live
  review policy contract status and report
  `LIVE_REVIEW_POLICY_CONTRACT_INVALID` for structural policy failures.
- The intentionally unapproved example policy remains contract-valid, while
  unsafe policies that allow external submission or omit required files are
  blocked before any live action.
- 3 new tests (1346 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.32.0.

## v0.31.0

- `background.py`: added `live_provider_capabilities()` and
  `live_provider_readiness(config_path)` for no-network provider-specific M4
  readiness checks.
- `automation_readiness_summary` and `live_dry_run_plan`: now include
  provider-by-provider credential, policy, rate-limit, and submission-safety
  readiness details.
- Live mode now reports `LIVE_PROVIDER_NOT_READY` when any provider has missing
  credentials, policy approval gaps, unsupported live queries, submission
  capability, or insufficient rate-limit policy.
- 3 new tests (1343 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.31.0.

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
