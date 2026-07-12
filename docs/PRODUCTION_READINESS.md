# PRODUCTION_READINESS.md — NEO Pipeline Production Gap Register

**Current version**: v0.90.75
**Last updated**: 2026-07-10 (header/sync line only — the P1-P5 gate register
body below is unchanged historical evidence from 2026-07-02; current gate
status for the active ZTF DR24 path lives in
`docs/ZTF_DR24_PRODUCTION_GATES.md`, which is kept current every session)
**Purpose**: Mandatory read at session start (per MANDATORY SESSION-START PROTOCOL).  
Every planning cycle must name the highest-priority unresolved production-capability gate and show how proposed steps close or directly unblock it.

**Also mandatory at session start**: `docs/near_earth_objects_research_brief.md` — canonical primer on ranked space assets (WISE/NEOWISE #2, NEO Surveyor #1, Gaia #3), frontier AI methods (THOR, HelioLinC3D), submission best practices, and key literature. Required to keep agents aligned on the discovery-paper data strategy (step 5 of CLAUDE.md §MANDATORY SESSION-START PROTOCOL).

**PIVOT NOTICE (2026-07-02, operator decision)**: `docs/neo_discovery_agent_brief.md`
now supersedes WISE/DECam/TESS as the primary discovery strategy. See
`docs/MISSION.md §Operator Decision (2026-07-02)` for the full record. **The
gate register below (P1–P5) describes the now-secondary WISE/DECam/TESS
pipeline.** Those gates remain CLOSED as an accurate historical record of
verified work, but closing them does **not** establish production readiness
for the new primary pipeline (ZTF DR24 historical replay). Phase 0
source-verification evidence is now recorded in `docs/evidence/phase0/`:
JPL SBDB, MPC get-obs, and IRSA ZTF image metadata are live-verified; Fink
schema access is externally blocked at TLS handshake; pretrained model use is
deferred. The ZTF DR24 production gates are now defined in
`docs/ZTF_DR24_PRODUCTION_GATES.md`. Gates Z1, Z2, Z4, Z5, Z6, and Z7 are
closed with real evidence. Gate Z3 is the only remaining open ZTF DR24
production gate, and its candidate-pair search is intentionally paused after
four low-yield attempts unless the operator explicitly restarts that path.
Future work should favor evidence, data-selection, storage, ranking, and
validation hardening over another candidate-pair run.

**Phase 0 status (2026-07-02)**: 3 of 4 cited sources live-verified working
via `Skills/verify_ztf_dr24_sources.py` — IRSA ZTF image metadata (200, no
auth), JPL SBDB NEO query (200, `sb-group=neo` not the brief's `neo=Y`), MPC
get-obs (200, requires a JSON request body, not query-string params). Fink
API is an external TLS-handshake blocker confirmed via two independent TLS
stacks (Python `ssl` and the operator's native LibreSSL) failing identically
from a real network — not fixable from this codebase. See
`docs/evidence/phase0/2026-07-02-root-cause-findings.md` and
`2026-07-02-second-live-probe-console.md` for full detail. The generated Phase
0 artifacts are committed under `docs/evidence/phase0/`, including
`data_sources_verified.md`, `auth_requirements.md`,
`phase0_probe_results.json`, `schema_snapshot/README.md`,
`sample_ingest_report.md`, and `pretrained_model_audit.md`. Later evidence
closed Gate Z1, Gate Z2, and the macOS model-load deadlock investigation. The
remaining production work is paused Gate Z3 or an explicitly approved
replacement path, plus the Astrometrics policy controls below.

**Astrometrics policy overlay (2026-07-08)**:
`docs/astrometrics_coding_agents_master_guide.md` and
`docs/astrometrics_data_selection_policy.md` add production controls that
outrank older "trained model exists" wording. Before promoting any model or
launching a materially larger production batch, the project must add:

- Dataset manifests with validation tests and manifest IDs cited by training,
  scoring, evaluation, and live-search runs.
- A candidate ledger that can regenerate every candidate packet from source
  dataset ID, generator params, model versions, scores, review state, and
  command provenance. Initial SQLite schema and CLI landed in v0.90.61; the
  next closure step is wiring production runs to cite manifest IDs and ingest
  candidate packets automatically.
- A frozen CNN benchmark (`benchmark_cnn_v1`) with locked preprocessing, seeds,
  split definitions, metrics, and a model card. Initial benchmark wrapper,
  config, and model card landed in v0.90.62; this closes the freeze step only,
  not CNN production promotion.
- Grouped NEO splits by night, sky region, survey/instrument, and object ID;
  random splits are diagnostic only. Initial grouped leakage controls landed
  in v0.90.63; stacker production-candidate adoption landed in v0.90.68.
  v0.90.69 extends the same fail-closed `--grouped-split-report`/
  `--production-candidate` gate (backed by a shared
  `grouped_splits.load_grouped_split_gate`) to the three remaining training
  Skills: `train_tier1_xgboost.py`, `train_tier2_cnn.py` (which also gained
  `--dry-run`), and `train_tier3_transformer.py`. All four model-builder
  Skills now share the same gate. Promotion-report wiring for real,
  model-specific evidence packets remains open.
- A5 canonical regression eval runner landed in v0.90.64. v0.90.70 adds
  `data_selection/canonical_evals/production_suite_v1.json`, a frozen
  policy-grade suite covering all four case types (`known_neo_recovery`,
  `false_link`, `injection_recovery`, `review_packet`) with every case's
  `observed_path` citing real, already-committed evidence (the n=200
  injection-recovery baseline, the Gate Z4 ranking-baseline purity report,
  the Gate Z6 retrospective-validation report, and a real Gate Z3
  known-NEO-recovery attempt that did not confirm a match). This closes A5
  for model-builder-independent regression protection; per-model canonical
  suites tied to a specific promoted model remain part of A7.
- A6 synthetic-harness recovery curves landed in v0.90.65, covering
  magnitude, motion rate, observation count, and night count. v0.90.71 adds
  image-level curves: `Skills/injection_recovery.py --image-level` synthesizes
  a real difference-image cutout per injection (Gaussian PSF + Gaussian
  background noise + trail elongation) and derives real_bogus from its
  analytic peak SNR (calibrated so mag/seeing/background/trail sweeps
  actually cross detect.py's 0.65 threshold, not a flat 0%/100%), closing the
  seeing/background/trail-length gap. A real n=200, seed=42 baseline is
  committed at `data/injection_recovery_image_level_n200.json`
  (detection/link/score rate 7.5%, real per-bin curves for all three new
  dimensions).
- **2026-07-12 (operator decision): `tier2_cnn_v3` REJECTED for
  promotion.** Operator decision, recorded verbatim: "Reject - Retune."
  Real, model-specific adversarial evidence
  (`Skills/evaluate_cnn_false_discovery.py`, new script) found
  `tier2_cnn_v3` shows 100% (200/200) false-discovery on a synthetic
  sub-pixel-artifact shape-discrimination test, versus 15.5% (31/200) for
  the currently frozen `benchmark_cnn_v1` — confirmed both in the full
  ensemble and in the isolated Tier 2 CNN output, so not an ensemble
  artifact. `benchmark_cnn_v1` remains the production model. Partial
  root-cause check (bounded streaming comparison of both models' real
  bogus training examples' PSF FWHM distributions) ruled out "v3's
  training data lacks narrow-artifact diversity" — both sets have nearly
  identical proportions (17.3% vs 16.3%) of spike-like bogus examples; the
  true cause remains open. Proposed retune: hard-negative training
  augmentation with synthetic spike examples, producing a new
  `tier2_cnn_v4` candidate. **Implemented same day**:
  `Skills/train_tier2_cnn.py --n-hard-negatives` (opt-in, off by default)
  mixes N synthetic `stellar_artifact` hard negatives — reusing
  `Skills/evaluate_cnn_false_discovery.py`'s artifact math with a
  configurable sigma range rather than one fixed value — into the training
  split only. 32 new tests, full suite 1892/2 passed/deselected, verified
  genuinely wired via a bounded in-sandbox smoke test. The real MPS retrain
  producing `tier2_cnn_v4` and the `evaluate_cnn_false_discovery.py`
  acceptance-test re-run are still NOT YET DONE — see
  `docs/evidence/a7/2026-07-12-hard-negative-augmentation-implemented.md`
  for the exact pending command. This closure also
  resolved the two prior open A7 evidence-quality gaps
  (`canonical_eval_report`, `false_discovery_report` never having
  exercised any CNN's live inference) with real, model-specific evidence
  — `canonical_eval_report` safely substituted (5/5 cases pass for both
  models); `false_discovery_report`'s automated gate deliberately left
  citing Gate Z4's real-data evidence rather than silently reinterpreting
  its 5% threshold against this much harder adversarial test. Full trail:
  `docs/evidence/a7/2026-07-12-real-cnn-injection-recovery.md`,
  `docs/evidence/a7/2026-07-12-cnn-adversarial-false-discovery.md`,
  `docs/evidence/a7/2026-07-12-model-rejected-retune-required.md`.
- **v0.90.85 (2026-07-11, doc-sync)**: Four commits landed after v0.90.81
  without a readiness-doc sync; recorded here. `mpc_training_labels_v1` and
  `tier3_transformer_pilot_v1` dataset manifests close the last two A1 gaps
  — every trained model's real training data now has a manifest (Tier 1
  XGBoost's `data/training_labels.csv`, verified 500 NEO + 500 MBA rows by
  direct inspection; Tier 3 Transformer's real `data/sequences/tier3_pilot_v2/`
  data, verified against `tier3_training_report.json`'s class counts — the
  manifest also documents that the top-level `data/sequences/mpc_pilot.json`
  is the failed first pilot attempt, not real data, to prevent future
  confusion). `Skills/run_pipeline.py --candidate-ledger-db` now defaults to
  `data_selection/candidate_ledger.sqlite` instead of `None`, closing an A2
  gap where a run without the flag silently produced candidates with zero
  ledger provenance — a direct violation of
  `docs/astrometrics_coding_agents_master_guide.md`'s non-negotiable rule 9.
  A `--source-dataset-id="not-recorded"` placeholder-provenance footgun was
  found and fixed in the same change. `docs/evidence/promotion/tier2_cnn_v3_operator_review_packet.md`
  is a new real, readable review packet (training result, all 8 A7 checks
  with real values, calibration KPI table, the one policy judgment call
  needing operator buy-in, known limitations, attestation checklist) —
  this is the actual justification behind the `operator_signoff_missing`
  blocker, not just a bare CLI command. **Net status unchanged**:
  `operator_signoff_missing` remains the sole blocker in the A1-A7 roadmap;
  it is now backed by real evidence a human can actually review. Re-verified
  this session: `ruff check .` clean, `mypy src` clean.
- **v0.90.81 (2026-07-11)**: `Skills/build_promotion_report.py` run for real
  against `tier2_cnn_v3`. **8/8 evidence checks pass** (dataset_manifest,
  grouped_split_report, canonical_eval_report, injection_recovery_report,
  calibration_report, false_discovery_report, pretrained_audit,
  benchmark_model_card). `promotion_allowed: false` with exactly one
  blocker: `operator_signoff_missing`. This is now the sole remaining
  blocker in the entire A1-A7 roadmap that real work this session could
  close -- every other check is real and passing. Report:
  `docs/evidence/promotion/tier2_cnn_v3_promotion_report.json`. Evidence:
  `docs/evidence/a7/2026-07-11-ninth-attempt-promotion-report-eight-of-eight-checks-pass.md`.
- **v0.90.80 (2026-07-10)**: `calibration_report_missing` is **CLOSED**
  with real evidence. Operator re-ran the retrain + calibrate command with
  the v0.90.79 MPS fix merged: both completed in 17m53s total, `Device: mps`
  confirmed, 20/20 epochs, best `val_loss=0.1155` `val_acc=0.965` saved to
  `models/tier2_cnn_v3.pt`. Real Tier 2 CNN calibration KPIs on the 18-night,
  90,000-alert batch: Brier=0.0211, ECE=0.0229 (Isotonic: 0.0192/0.0054),
  Log-loss=0.0760, ROC AUC=0.9954, CV ECE mean=0.0056 (std=0.0010),
  Bootstrap Brier/ECE CI upper=0.0192/0.0056 -- all 7 T1-D KPIs PASS,
  `promotion_gate_passed: true`. Both A7 blockers requiring a real retrain
  (`grouped_split_report_missing`, `calibration_report_missing`) are now
  closed. **`operator_signoff_missing` is the sole remaining A7 blocker**
  (inherently human-gated). Next coding step: a promotion report for
  `tier2_cnn_v3` citing this session's real grouped-split and calibration
  reports. Evidence:
  `docs/evidence/a7/2026-07-10-eighth-attempt-real-retrain-and-calibration-pass.md`.
- **v0.90.79 (2026-07-10)**: Operator's real retrain run (real MPS device)
  hit a genuine upstream PyTorch MPS bug: `AdaptiveAvgPool2d(4)` on a 15×15
  feature map fails on MPS because 15 is not evenly divisible by 4
  (<https://github.com/pytorch/pytorch/issues/96056>), not a bug in this
  project. Fixed in `src/classify.py`'s `ConvBranch.forward()` by routing
  only that op through CPU on MPS. A first fix attempt changed
  `state_dict()` key names and broke loading the frozen `benchmark_cnn_v1`
  checkpoint -- caught via `Skills/validate_model_weights.py` before
  committing; corrected version preserves state_dict keys exactly and
  `Skills/validate_model_weights.py` reports `ALL PASSED`. 2 new regression
  tests; full suite 1845 passed / 2 deselected, ruff/mypy clean. No model
  checkpoint was produced by the failed run, so `calibration_report_missing`
  remains open pending a re-run with this fix. Evidence:
  `docs/evidence/a7/2026-07-10-seventh-attempt-mps-adaptive-pool-bug-and-fix.md`.
- **v0.90.78 (2026-07-10)**: `Skills/train_tier2_cnn.py` gained real device
  selection (MPS when available, explicit CPU-fallback reporting) and a
  configurable `--num-workers` DataLoader flag, fixing a real gap versus
  `docs/SYSTEM_PROFILE.md`'s mandatory device-selection rule (the script
  previously never selected a device at all). Fixing `--num-workers` also
  required moving `CutoutDataset` to module level so DataLoader workers can
  pickle it. This session's sandbox verified it cannot exercise either
  speedup path (MPS and multiprocess workers are both blocked by sandbox
  filesystem/framework restrictions, not by the code) -- one real CPU-only
  epoch on the 90,000-alert v3 batch took ~9.5 minutes, so the actual
  20-epoch retrain is handed off to an unsandboxed terminal per `CLAUDE.md`'s
  Current State rather than spending 3+ hours of degraded sandboxed compute.
  Full suite 1843 passed / 2 deselected, ruff/mypy clean. Evidence:
  `docs/evidence/a7/2026-07-10-sixth-attempt-device-selection-and-sandbox-training-limits.md`.
- **v0.90.77 (2026-07-10)**: `grouped_split_report_missing` is **CLOSED**
  with real evidence. A follow-up real 18-night (90,000-alert) scale test of
  the v0.90.76 night-aware split showed leakage getting *worse* with more
  data (15/18 nights leaking vs 2/3 at 3 nights; object-conflict-resolution
  rows 2,653 -> 10,382) -- decisive evidence that simultaneous `object_id` +
  `night_key` + `sky_cell` purity is structurally unachievable for this
  survey's real data: 10.4% of real objects (7,645/73,560) are detected on
  more than one distinct night (worsens, not improves, with more nights),
  and ZTF's routine field-revisit cadence reobserves most sky cells across
  any time-block split. Operator-approved policy change: `object_id` remains
  the sole hard gate in `src/grouped_splits.py`; `night_key`/`sky_cell`
  moved to a new monitored-not-gating category, still computed and reported
  (`monitored_leakage`, `monitored_leak_rates`) for transparency. Re-running
  the (now sufficient) plain object-random split on the real 18-night batch
  produces the first genuinely passing report:
  `Logs/reports/tier2_cnn_v3_grouped_split_report.json`, `passed=true`,
  disclosed monitored leak rates `night_key=100%`, `sky_cell=91.3%`. Five
  dated evidence files in `docs/evidence/a7/` document the full real-data
  trail. Full suite 1843 passed / 2 deselected, ruff/mypy clean throughout.
  Remaining A7 blockers: `calibration_report_missing` (needs an actual
  model retrain on this data, gated on a GPU/MPS feasibility check -- this
  sandboxed session found `torch.backends.mps.is_available()` False despite
  the real machine's Apple M4 Max GPU) and `operator_signoff_missing`
  (inherently human-gated).
- **v0.90.76 (2026-07-10)**: The v0.90.74 handoff was run for real end to
  end. Result: `grouped_split_report_missing` is still open, but for a new,
  more precise reason than before. First, a real acquisition bug was found
  and fixed (`compute_per_night_target()` in
  `Skills/download_ztf_training_alerts.py`) -- a single night's tarball
  (40,000+ alerts) could satisfy the whole `--limit` before the loop ever
  reached night 2/3, so `--nights 3` silently produced single-night data
  regardless of `--limit`. Fixed and verified: a re-run now genuinely spans
  3 distinct nights. Second, once real multi-night data existed, a deeper
  gap surfaced: `train_tier2_cnn.py --emit-split-csv` groups only by
  `object_id`, but `Skills/validate_grouped_splits.py` independently
  requires `object_id` AND `night_key` AND `sky_cell` purity. With only 3
  real nights present, satisfying `night_key` purity requires assigning
  whole calendar nights to whole splits -- a coarser, statistically weaker
  split (each split determined by a single night) than the current
  object-random split. This is a genuine data-acquisition-scale /
  split-design tradeoff needing operator direction, not a code bug.
  Evidence: `docs/evidence/a7/2026-07-10-first-attempt-single-night-leakage.md`
  and
  `docs/evidence/a7/2026-07-10-second-attempt-object-id-split-still-leaks-night-and-sky.md`.
- A7 fail-closed model promotion reports landed in v0.90.66. v0.90.74 closes
  the acquisition-side root cause behind the `grouped_split_report_missing`
  blocker: `Skills/download_ztf_training_alerts.py` now captures each real
  alert's `object_id` (ZTF broker's persistent per-sky-position identifier),
  `candid`, `jd`, `ra`, `dec`, `fid`, `field`, and the real archive night
  string -- fields verified present in a real downloaded packet per
  `docs/evidence/phase0/2026-07-02-gate-z3-uw-alert-archive-candidate.md`,
  not guessed. `Skills/build_cutout_dataset.py` propagates them into
  `index.csv`. `Skills/train_tier2_cnn.py` replaces its prior
  `random_split()` (no leakage guarantee) with a genuine grouped split by
  `object_id` across train/validation/test, gains `--emit-split-csv` to
  write a `Skills/validate_grouped_splits.py`-compatible audit file matching
  the exact split a training run will use, and warns loudly (not silently)
  when a legacy row lacks `object_id`. This is a **code fix, not a data
  fix** -- the existing frozen `benchmark_cnn_v1` and its committed
  `data/ztf_labeled_alerts.json` are untouched; a fresh operator-run
  download + retrain is required to actually close the blocker with real
  evidence (see the operator handoff in `CLAUDE.md`'s Current State). 26 new
  tests cover the field capture, CSV propagation, grouped-split assignment
  (same object never split across train/val/test), and the CLI's fail-closed
  behavior on legacy (no-provenance) CSVs.
- A7 fail-closed model promotion reports landed in v0.90.66. v0.90.73 adds
  four real, committed dataset manifests under `data_selection/dataset_manifests/`
  (`ztf_labeled_alerts_tier2_cnn_v1`, `gate_z4_ranking_baseline_v1`,
  `gate_z6_retrospective_validation_v1`,
  `a6_injection_recovery_image_level_n200_v1`), each populated from computed
  facts (checksums) or already-documented project history (source URLs,
  gate-closure dates, real result counts), never guessed. Citing the training
  manifest closes the `dataset_manifest_missing` blocker for real: re-running
  `Skills/build_promotion_report.py` for `benchmark_cnn_v1` now shows 6/8
  evidence checks passing with only **three** real named blockers left
  (`grouped_split_report_missing`, `calibration_report_missing`,
  `operator_signoff_missing`), down from four. v0.90.72 first ran the builder
  for real against `benchmark_cnn_v1`:
  `Skills/extract_promotion_evidence.py` derives an injection-recovery report
  and a false-discovery report from already-committed real evidence (A6's
  image-level baseline and Gate Z4's ranking-baseline review-burden counts —
  0/200 false positives, `false_discovery_rate=0.0`) without inventing any
  new data, and `Skills/run_canonical_evals.py --out` persists the A5 suite's
  real 4/4-case, 16/16-check pass. Feeding all of this into
  `Skills/build_promotion_report.py` produces a real, committed report at
  `docs/evidence/promotion/benchmark_cnn_v1_promotion_report.json`:
  `promotion_allowed=false` with exactly four real, named blockers
  (`dataset_manifest_missing`, `grouped_split_report_missing`,
  `calibration_report_missing`, `operator_signoff_missing`) — the correct,
  honest current state, not a placeholder. **Root-cause finding**: the
  committed Tier 2 CNN training source, `data/ztf_labeled_alerts.json`
  (10,000 real ZTF alerts, gitignored/local), stores only
  `label`/`rb`/`drb`/cutout images per alert — it never captured per-alert
  RA/Dec/JD/field metadata. This is *why* A4's "policy-grade real split
  reports" and A1's "manifest coverage" remain open specifically for the CNN's
  training set: the grouping fields a real grouped split needs
  (`night_key`, `sky_cell`, `source_key`) cannot be reconstructed from data
  that was never saved, and must not be fabricated. Closing this requires
  either re-deriving the original alert metadata from its ZTF source (if
  still resolvable) or retraining with a data path that captures it going
  forward — both are real acquisition/retraining decisions, not a coding
  gap. Actual production promotion still requires those two real evidence
  packets plus a real calibration-report re-run (T1-D's KPI gate was passed
  2026-06-14 but only exists locally/gitignored on the operator's Mac) and
  operator signoff.
- Initial A1/A2 pipeline wiring landed in v0.90.67: `Skills/run_pipeline.py`
  accepts `--source-dataset-id` for run summaries and optional
  `--candidate-ledger-db` ingestion into the SQLite candidate ledger. Full
  production adoption still requires policy-grade manifests for each real
  dataset role and routine operator use of those flags.
- Canonical sample-level regression evals covering known NEO detections, false
  link examples, injected moving-source controls, and review-packet examples.
- Injection-recovery curves over magnitude, velocity, trail length,
  seeing/background, and missed frames before model promotion.

The current Tier 2 CNN is now frozen as `benchmark_cnn_v1` and remains
available as a feature source, but it is not production-promoted under the new
policy until grouped split reports, canonical evals, injection-recovery curves,
and the promotion report close.

---

## What Is Complete

The following work is done and must NOT be repeated:

### Pipeline modules (all 10, 100% test coverage)
| Module | Tests | Coverage |
|---|---|---|
| `schemas.py` | test_schemas.py | 100% |
| `fetch.py` | test_fetch.py | 100% (all external calls mocked) |
| `preprocess.py` | test_preprocess.py | 100% |
| `detect.py` | test_detect.py | 100% |
| `link.py` | test_link.py | 100% |
| `classify.py` | test_classify.py | 100% |
| `orbit.py` | test_orbit.py | 100% |
| `score.py` | test_score.py | 100% |
| `alert.py` | test_alert.py | 100% |
| `calibration.py` | test_calibration.py | 100% |

### Infrastructure
- 1531+ offline tests pass (after dead-code removal in v0.89.3); 2 live checks deselected; `ruff` clean; `mypy` clean
- Background automation CLI (`Skills/background.py`) with SQLite audit logs
- 90+ Skills scripts for batch operations, export, diagnostics, visualization
- 30+ documentation files covering all pipeline stages
- Repository artifact policy: `git add .` is supported by ignore rules that
  keep raw `Logs/**` local, allowlist only production model artifacts, and
  require durable run evidence to be promoted into `docs/evidence/` or
  `data/evidence/`.
- MPC 80-column and ADES PSV format output
- Alert protocol guardrails (MOID gate, quality code gate, real/bogus gate, confirmation gate)
- Injection-recovery: 100% detection, 100% link, 100% score on synthetic data (n=200)
- Stress-test: 100% link rate across all three high-motion bins on synthetic data
- Conservative scoring model with log-likelihood framework and calibrated posteriors

### What "complete" means here
All modules compile, pass 100% branch coverage, and produce correct output
**on synthetic/mocked pipeline data**. Real labeled ZTF alerts have been used
to train and calibrate the ML tiers (ZTF = training source only; NOT discovery
source). The fetch.py discovery layer targeting unreviewed archives
(WISE/NEOWISE, DECam/NOIRLab, TESS FFIs) is now complete (PR #119,
2026-06-27). T1-C known-object recovery audit and operator false-positive
review are CLOSED.

### Production Definition (operator-approved 2026-07-01)

For this project, **production** means the pipeline has demonstrated the
capability to find, score, reject, review, and package candidate moving objects
from unreviewed archival discovery data with defensible, industry-standard
confidence controls. Production does **not** require that the project has
already found a genuinely new NEO; a real discovery is expected to be rare.

Production readiness requires:

1. A discovery-source positive control or equivalent injection/recovery proof
   showing that the WISE/NEOWISE, DECam, or TESS discovery path can produce full
   `ScoredNEO` review packets when a valid moving-object signal is present.
2. Quantitative, survey-native confidence gates for discovery data, including
   astrometric residuals, multi-exposure/multi-night motion consistency, static
   source rejection, known-object and satellite checks, artifact rejection, and
   orbit-quality constraints. ZTF-style real/bogus evidence may support the
   ensemble but must not be the only confidence basis for WISE/DECam/TESS
   discovery candidates.
3. A no-submission end-to-end drill that takes a positive-control packet
   through adversarial review, operator review, and MPC-compatible report
   generation while verifying that external submission remains fail-closed.
4. A documented MPC submission protocol for the relevant archive source,
   including source attribution, station/observatory-code handling, ADES fields,
   operator approval, and no-impact-claim guardrails.

Finding an actual new candidate that survives these controls starts the
Discovery Event Gates below; it is not itself a prerequisite for declaring the
software production-capable.

---

## Tier 1 Gaps — Historical Engineering Gates

These gaps prevented the pipeline from being safely or usefully operated on real
sky data. They are retained as historical evidence because they define the
engineering foundation under the current production-capability gates.

### T1-A: Incomplete Trained ML Model Set (HIGHEST PRIORITY)

**What is missing**: The three-tier ML classifier is not yet complete.
- Tier 1 (XGBoost): **WEIGHTS TRAINED AND COMMITTED.** `models/tier1_xgb.json`; validation accuracy 99.95%, macro AUC 1.000.
- Tier 2 (CNN): **WEIGHTS TRAINED AND COMMITTED.** `models/tier2_cnn.pt`; trained on 10,000 real ZTF Avro alerts (8,000 train / 2,000 validation); best validation loss 0.258 and validation accuracy 91.3% at 20 epochs. Needs calibration evaluation before alert-gate use.
- Tier 3 (Transformer): **WEIGHTS TRAINED (pilot).** `models/tier3_transformer.pt`; best epoch 17/30, val_macro_f1=0.9400, val_loss=0.2492; trained on the 50-per-class five-class pilot dataset (train+calibration+test splits). Calibration KPI evaluation (T1-D) and ensemble stacking still needed before production.

**Why it is Tier 1**: Without the real multi-night sequence dataset and trained
Tier 3 weights, the intended production ensemble is incomplete. Downstream
calibration and alert-gate qualification cannot be completed.

**Progress as of 2026-06-10**:
- `data/ztf_labeled_alerts.json`: 10,000 real ZTF Avro alerts downloaded from public archive (ztf.uw.edu); cutouts decompressed from gzip-FITS to raw float32. ✓
- `data/cutouts/`: 10,000 `.npz` cutout triplets (science, reference, difference) + `index.csv`. ✓
- `data/training_labels.csv`: 1000 MPC labels (500 neo_candidate + 500 main_belt_asteroid). ✓
- `models/tier2_cnn.pt`: CNN trained — val_loss=0.258, val_acc=91.3%, 20 epochs; 8,588 real / 1,412 bogus; inverse-frequency class weights. ✓ Committed.
- `models/tier1_xgb.json`: XGBoost trained — val_acc=99.95%, macro AUC=1.000, 11,100 examples (8,880 train / 2,220 val); class-weighted; 300 estimators, max_depth=5. ✓ Committed to repo at commit 13946ea.
- Five-class label policy and 50-sequence-per-class pilot approved by Jerome W.
  Lindsey III on 2026-06-10. The approval covers label sources and pilot
  execution only; it is not model or production approval. ✓
- Policy-aware MPC windows, public ALeRCE artifact acquisition, five-class
  validation, source hashing, and designation-grouped split generation are
  implemented and offline-tested. ✓
- The first operator pilot attempt produced a 200-row manifest and an MPC
  checkpoint. Audit found 28 duplicate comet rows, only 172 unique selected
  objects, and 103 zero-result MPC queries recorded as insufficient
  observations because provider failures were suppressed. The evidence is
  retained locally; a corrected fail-closed rerun is required.
- The operator transcript also showed that a shell command chain could continue
  into split preparation after acquisition failure, and that the shared checkout
  changed branches during the long run. The replacement is one atomic runner
  with commit pinning, an active-run marker, reserve candidate pools, resumable
  checkpoints, and top-level SQLite stage outcomes.
- v0.87.2 (2026-06-11): Three further pilot-robustness fixes merged — parallel
  circuit-breaker bias adjustment (threshold now `max_errors + workers - 1`),
  `None`-table guard in `fetch_mpc_observations`, and query-level exception
  classification (non-infrastructure errors no longer feed the circuit breaker).
- v0.87.3 (2026-06-12): Extended packed designation unpacking for asteroids
  ≥100000 (e.g. `A0004` → `100004`) fixed in `_unpack_designation()` in
  `Skills/generate_training_labels.py` (PR #85). This was the root cause of all
  400 pilot candidates returning zero MPC observations on the prior run. All
  three MPCORB packed formats now handled: leading-zero numeric, 7-char
  provisional, and base-62 extended numeric.
- v0.87.4 (2026-06-13): `MPC.get_observations()` epoch column returns
  `astropy.Quantity(value, unit='d')` in newer astroquery. Fixed in
  `fetch_mpc_observations()` with `.value`/`.jd` dispatch (PR #86).
- v0.87.5 (2026-06-13): astroquery 0.4.11+ assigns units to ALL four numeric
  columns (epoch→d, RA→deg, DEC→deg, mag→mag). PR #86 fixed `epoch` only;
  RA, DEC, and mag still raised `TypeError` per-row, silently discarded,
  causing all 400 fourth-pilot candidates to return `insufficient_observations`.
  Added `_mpc_to_float()` helper applied to all four columns (PR #87).
- Fifth pilot run (post-v0.87.5, 2026-06-13): **SUCCEEDED.** MPC acquisition
  collected 50 sequences per class (known_object, main_belt_asteroid,
  neo_candidate, other_solar_system) in 3m49s; ALeRCE collected 50
  stellar_artifact sequences (329 observations, 150 queried). Splits built:
  train.csv, calibration.csv, test.csv.
- Tier 3 Transformer training (2026-06-13): **DONE.** Best epoch 17/30,
  val_macro_f1=0.9400, val_loss=0.2492. Weights saved to
  `models/tier3_transformer.pt`; held-out report at
  `data/sequences/pilot/tier3_training_report.json`.
- **T1-D calibration KPI gate PASSED (2026-06-14)**:
  - Tier 1 XGBoost (Isotonic): Brier=0.0000, ECE=0.0000, ROC AUC=1.0000 — all 7 KPIs PASS.
  - Tier 2 CNN (Isotonic): Brier=0.0462, ECE=0.0132, ROC AUC=0.9593 — all 7 KPIs PASS.
  - `promotion_gate_passed=true`; report at `Logs/reports/calibration_report.json` (local only, gitignored).
- Ensemble stacking calibration is complete and passed the quantitative KPI gate.

**What is needed to close it**:
1. [DONE] Download 10,000 labeled ZTF Avro alerts via `Skills/download_ztf_training_alerts.py`.
2. [DONE] MPC labels: `data/training_labels.csv` with 1000 labels.
3. [DONE] `Skills/build_cutout_dataset.py` — 10,000 `.npz` cutout triplets built.
4. [DONE] `Skills/train_tier2_cnn.py` — `models/tier2_cnn.pt` saved; val_acc=91.3%.
5. [DONE] Commit `models/tier2_cnn.pt` to repo (`.gitignore` updated to allow `models/*.pt`).
6. [DONE] Use the bounded, resumable
   `Skills/query_mpc_observations.py --labels-csv ...` collector to acquire
   versioned MPC histories with source hashes, query logs, and safety flags.
7. [DONE] Execute the corrected 50-per-class pilot using provisional
   early-arc NEOs, numbered late-arc known NEOs, numbered MBAs, confirmed MPC
   comets, and ALeRCE high-confidence bogus ZTF histories through
   `Skills/run_tier3_pilot.py`. Fifth run (post-v0.87.5) succeeded: 50
   sequences per class, splits built.
8. [DONE] Validate the raw-data contract, create designation-grouped
   train/calibration/test splits, and build the flat token CSVs.
9. [DONE] Run the long Tier 3 training command under `caffeinate -i` —
   `models/tier3_transformer.pt` saved; best epoch 17/30, val_macro_f1=0.9400.
10. [DONE] Tier 1 XGBoost trained — val_acc=99.95%, macro AUC=1.000;
    `models/tier1_xgb.json` saved and committed at 13946ea.
11. [DONE] Evaluate with `Skills/evaluate_calibration.py` — both Tier 1 XGBoost
    and Tier 2 CNN passed all 7 T1-D KPIs on 2026-06-14; `promotion_gate_passed=true`.
12. [DONE] Train ensemble stacking meta-learner
    (logistic regression over Tier 1 + Tier 2 outputs) via
    `Skills/train_ensemble_stacker.py`. Saves `models/stacker_coef.json`.
    `classify.ensemble_predict` extended to support 5/10/15-feature stackers;
    `_load_ensemble_stacker` added to reconstruct from JSON. 100% coverage.
    Operator ran 2026-06-14: all 7 T1-D KPIs PASS on 394 ZTF-origin val
    samples. AUC=0.9809, Brier=0.0211, ECE=0.0000, Log-loss=0.0761,
    CV ECE mean=0.0247, Bootstrap Brier CI upper=0.0330,
    Bootstrap ECE CI upper=0.0225. `promotion_gate_passed=true`.

**Status**: All three tiers trained. T1-D calibration KPI gate passed for
Tier 1 XGBoost, Tier 2 CNN, and ensemble stacker (all 2026-06-14).
`models/stacker_coef.json` produced by operator; all 7 KPIs pass;
`promotion_gate_passed=true`. **T1-A is CLOSED.**

---

### T1-B: No Real Survey Credentials Configured — **CLOSED 2026-06-05**

**Status**: RESOLVED. Live connection test confirmed ATLAS OK and ZTF OK on 2026-06-05.  
Credentials are stored in macOS Keychain under `neo-detection:ATLAS_TOKEN`, `neo-detection:ZTF_IRSA_USERNAME`, `neo-detection:ZTF_IRSA_PASSWORD`. The bridge script `source Skills/verify_live_credentials.sh` loads them into the active shell session without exposing values to the agent or any log file.

**What was done**:
1. [DONE] IRSA account and API token obtained.
2. [DONE] ATLAS forced-photometry token obtained.
3. [DONE] Credentials stored in macOS Keychain; loaded via `source Skills/verify_live_credentials.sh`.
4. [DONE] Live connection test (`Skills/_live_connection_test.py`) passed: `{"atlas": {"status": "OK"}, "ztf": {"status": "OK"}}`.
5. [DONE] Formal bounded live dry-run policy signed by Jerome W. Lindsey III in
   `background/live_review_policy.example.json`. `background/config.json` now
   enables bounded live dry-run attempts, while readiness remains fail-closed on
   credential/provider blockers and never permits external submission or impact
   probability claims.
6. [DONE] T1-C recovery query envelope expanded by Jerome W. Lindsey III on
   2026-06-19 to permit up to 40 ATLAS forced-photometry sample queries for
   recovery evidence only. No external submission or impact-probability claims
   are authorized.

**Remaining step before automated live runs**: Validate provider credential
readiness through the background CLI and keep every run inside the signed
bounded policy. This approval does not authorize MPC submission, NEOCP
follow-up escalation, NASA notification, or public hazard claims.

---

### T1-C: Real-Data Recovery And Operator Review Evidence

**Status**: **CLOSED 2026-06-20.** Known-object recovery ≥90% verified on ATLAS data; operator review by Jerome W. Lindsey III found no blocking findings. This gap is resolved.

**What was missing**: The full pipeline (`Fetch → Preprocess → Detect → Link → Classify → Score → Alert`) needed one recovery-audit run with ≥90% known-object recovery verification and operator false-positive review.

**Why it is Tier 1**: Synthetic data cannot expose real failure modes — coordinate edge cases, survey-specific format quirks, real noise distributions, real artifact morphologies, or real rate-limiting behavior. The pipeline's real-world correctness is unknown until it processes real data.

**Closure trail**: the recovery-methodology journey (ALeRCE Orion pilot,
ZTF/ATLAS fallback diagnostics, prequalification-rule development, and the
final Option A screening + audit runs that closed the gate on 2026-06-20)
is archived verbatim in `docs/HANDOFF_HISTORY.md` under "PRODUCTION_READINESS.md
historical narrative — T1-C". Not required reading; the status line above
is sufficient for any future plan. **T1-C is CLOSED** — no further action
needed; do not repeat any recovery-audit run listed there.


---

### T1-D: No Production Ensemble Calibration — **CLOSED 2026-06-14**

**What is missing**: The stacking meta-learner (logistic regression) and Platt/isotonic calibration in `calibration.py` have been trained on no real data. The calibration curves have not been validated on a held-out real-data test set. `compute_ece()`, `compute_brier_score()`, and `reliability_diagram()` all work on synthetic probabilities in tests; they have never been run on real model outputs.

**Why it is Tier 1**: Uncalibrated probabilities mean the alert pathway gate conditions (e.g., `real_bogus_score ≥ 0.90`) are meaningless. A model that outputs 0.90 for 50% of its candidates is not calibrated; the gate will either pass too many artifacts or suppress genuine NEOs.

**What is needed to close it**:
1. [DEPENDS ON T1-A] Trained model weights must exist first (T1-A).
2. [DATA] Use a held-out real labeled evaluation set that was not used for
   model fitting or calibrator fitting. Require at least 1,000 examples,
   including at least 200 positive and 200 negative examples.
3. [CODE] Run `Skills/evaluate_calibration.py` and
   `Skills/plot_calibration.py`. The reliability diagram is retained as an
   auditable evidence artifact; it is not a human approval step.
4. [KPI] Require every production calibration KPI below to pass:
   - Brier score < 0.10.
   - ECE < 0.05 using 10 equal-width bins.
   - Log loss < 0.50.
   - ROC AUC > 0.95.
   - Five-fold cross-validation mean ECE < 0.05 with standard deviation ≤ 0.02.
   - Bootstrap 95% upper confidence bound < 0.12 for Brier score and < 0.07 for ECE.
5. [DONE] Machine-readable calibration report emitted to `Logs/reports/calibration_report.json`
   (local only, gitignored). `promotion_gate_passed=true`.
6. [DONE] All KPIs passed; alert gates may be armed for Tier 1 and Tier 2.

**Outcome (2026-06-14)**:
- Tier 1 XGBoost (Isotonic calibration): Brier=0.0000, ECE=0.0000, Log-loss=0.0004,
  ROC AUC=1.0000, CV ECE mean=0.0000, CV ECE std=0.0000,
  Bootstrap Brier CI upper=0.0000, Bootstrap ECE CI upper=0.0000. All 7 KPIs PASS.
- Tier 2 CNN (Isotonic calibration): Brier=0.0462, ECE=0.0132, Log-loss=0.2398,
  ROC AUC=0.9593, CV ECE mean=0.0212, CV ECE std=0.0076,
  Bootstrap Brier CI upper=0.0494, Bootstrap ECE CI upper=0.0185. All 7 KPIs PASS.
- `promotion_gate_passed=true`; report at `Logs/reports/calibration_report.json`.
- **Remaining**: Tier 3 Transformer and ensemble stacker calibration evaluation
  (to be done after ensemble stacking is trained).

---

## Tier 2 Gaps — Important Before Sustained Operation

These gaps do not prevent a first supervised live run but must be resolved before the pipeline operates unsupervised or submits reports to MPC.

### T2-A: No Integration Tests Have Passed Against Real APIs

All tests marked `@pytest.mark.integration_live` are excluded from CI. The live code paths for `fetch_ztf_alerts`, `fetch_atlas_forced`, and `fetch_mpc_observations` have never been called against real network endpoints. Actual API response schemas, rate limits, and error modes are untested.

**Needed**: Run integration tests in a sandboxed environment with real credentials. Requires T1-B resolution.

**T2-A CLOSED (2026-06-21)**: Both `integration_live` tests passed on operator Mac (Python 3.14.3):
- `test_fetch_ztf_live_small_region` — PASSED (ZTF IRSA live cone-search)
- `test_fetch_atlas_live_small_region` — PASSED (ATLAS FPS forced photometry, Orion field JD 2460700.5)

Two bugs fixed during closure: (1) `fetch_atlas` used `json=` instead of `data=` (form-encoded) for POST to ATLAS /queue/; (2) test fixture used JD 2460000 (= Feb 2023, 1213 days ago) which exceeds ATLAS's ~1000-day archive retention — fixed to use JD 2460700.5.

Full evidence: `docs/evidence/t2a/2026-06-21-integration-live-results.md`

### T2-B: No Adversarial/Robustness Testing

The pipeline has not been tested against:
- Real ZTF artifacts (satellite trails, cosmic rays, ghost reflections)
- Real bad-pixel regions or missing difference cutouts
- Ephemeris edge cases (very fast near-Earth objects, objects near survey edges)
- Rate limiting and network timeout behavior in `fetch.py`

**Needed**: Run `Skills/diagnose_pipeline.py` on real ZTF alert data; audit false-positive rate against known-artifact catalog. Requires T1-C resolution.

**Progress (2026-06-21)**: `tests/test_adversarial.py` added with 10 synthetic adversarial test cases covering all four scenario categories (satellite trail rejection, missing/corrupted cutouts, extreme motion, network timeout simulation, survey edge coordinates, duplicate obs IDs, missing orbital elements, alert guardrail on short arc). These run in CI without credentials. Real-data false-positive audit against a known-artifact catalog remains a future operator-run step.

### T2-C: No External Expert Review Of ML Architecture

The Tier 1–3 architecture (XGBoost → CNN → Transformer → stacking) was designed per CLAUDE.md DECISION-002 and literature references (Duev et al. 2019, Lin et al. 2022). The implementation has not been reviewed by an astronomer or ML practitioner with NEO survey experience.

**Discovery-paper constraint**: No external domain expert review was required
per operator decision 2026-06-21. MPC/NEOCP/Scout is the expert review system.
External MPC submission is gated by `ready_for_submission()` quality gates,
adversarial review (`Skills/adversarial_review.py`), and operator review —
not in-house expert validation.

**Progress (2026-06-20)**: Architecture evidence packet created at
`docs/evidence/t2c/2026-06-20-citizen-science-architecture-evidence-packet.md`.
Records all five architecture decisions, calibration KPI results for all three
tiers and the ensemble stacker, known limitations (data, orbital coverage,
pipeline coverage), and no-submission guardrails.
This packet does not authorize any external submission.

**T2-C CLOSED (2026-06-21)**: Section 6 operator review completed by Jerome W.
Lindsey III. All five attestation checkboxes signed. No external submission
authorized. Expert validation gap explicitly acknowledged.

### T2-D: No CI for Integration or End-to-End Tests

CI currently runs only unit tests. There is no CI job for:
- Integration tests against real APIs (gated on credentials)
- End-to-end pipeline smoke test on a small real-data fixture
- Model weight validation (checking that trained weights produce calibrated output)

**Needed**: Add CI job definitions (`.github/workflows/`) for integration and end-to-end test stages, gated on secret availability.

**Progress (2026-06-21)**: `.github/workflows/e2e.yml` has four synthetic-data
jobs — `smoke` (module happy-path), `diagnose` (stage-by-stage pipeline run),
`injection` (n=20 injection-recovery with regression check vs committed baseline),
and `model-weights` (loads all four committed model files and asserts valid
calibrated output on synthetic fixtures via `Skills/validate_model_weights.py`).
Integration tests against real APIs covered by `.github/workflows/integration.yml`.

### T2-E: Session-Start Documents Synchronized — **CLOSED 2026-06-09**

`AGENTS.md`, `CLAUDE.md`, `README.md`, and this gap register now agree on the
trained-weight state, live-credential state, Tier 3 blocker, calibration KPI
gate, and current offline test result.

---

## Outside Blockers (Human Action Required)

These items cannot be completed by code generation alone. They require real-world human decisions or access.

| Blocker | Owner | Unblocks |
|---|---|---|
| Archival WISE/NEOWISE MPC submission authority | Jerome W. Lindsey III + MPC | Live WISE/NEOWISE MPC submission |
| Live review policy sign-off | CLOSED 2026-06-18 by Jerome W. Lindsey III | T1-B |
| Known-object recovery audit and false-positive review | CLOSED 2026-06-20 by Jerome W. Lindsey III | T1-C |

---

## Production Readiness Checklist

The historical T1/T2 engineering readiness checklist below is complete. The
open production-capability gates that follow this checklist define whether the
software is ready to search for and package candidates under the operator's
2026-07-01 production definition.

- [x] T1-A resolved: Tier 1 XGBoost ✓ (val_acc=99.95%); Tier 2 CNN ✓ (val_acc=91.3%); Tier 3 Transformer ✓ (val_macro_f1=0.9400); ensemble stacker ✓ (AUC=0.9809, all 7 KPIs pass, 2026-06-14)
- [x] T1-A resolved: calibration KPI gate passed ✓ (T1-D, 2026-06-14); ensemble stacker KPIs passed ✓ (2026-06-14)
- [x] T1-B resolved: IRSA and ATLAS credentials configured ✓; live connection test passed ✓; bounded live dry-run policy signed ✓; execution remains credential/provider gated and non-submitting
- [x] T1-C resolved: ATLAS known-object recovery KPI passed ✓ (5/5 objects, 100%, 2026-06-20);
      operator review completed ✓ (Jerome W. Lindsey III, no blocking findings, 2026-06-20);
      full evidence: `docs/evidence/t1c/2026-06-20-option-a-screening-prequalification.md`
- [x] T1-D resolved: Machine-readable calibration report passes every required
      KPI on held-out real labeled data and records
      `promotion_gate_passed=true` ✓ (2026-06-14; Tier 1 + Tier 2)
- [x] T2-A resolved: both integration_live tests PASSED on operator Mac ✓ (2026-06-21);
      ZTF IRSA + ATLAS FPS live calls confirmed working; credentials kept off GitHub by policy
- [x] T2-B resolved: 10 synthetic adversarial tests in CI ✓; diagnose_pipeline.py all 10 stages
      PASS on operator Mac ✓ (2026-06-21); real-data artifact audit is a future milestone
- [x] T2-C resolved: architecture evidence packet signed ✓ (Jerome W. Lindsey III, 2026-06-21);
      all five attestation items checked; no external submission authorized;
      discovery-paper framing adopted 2026-06-26
- [x] T2-D resolved: e2e.yml has smoke/diagnose/injection/model-weights jobs ✓ (2026-06-21);
      Skills/validate_model_weights.py validates all four committed model files
- [x] Alert protocol compliance: `ready_for_submission()` gate validated on 14 diverse synthetic
      NEOs via `Skills/validate_alert_protocol.py` ✓ (wired into e2e.yml alert-protocol CI job, 2026-06-21)
- [x] Guardrail compliance: static scan of all pipeline source confirms zero "confirmed NEO"
      or impact probability assertions ✓ (2026-06-21; all occurrences are negations or
      guardrail enforcement — see `src/background.py:3568` forbidden_phrases check)
- [x] AGENTS.md and CLAUDE.md synchronized to current version ✓ (2026-06-26,
      v0.89.3; re-synced 2026-07-04 at v0.90.57 after a ~30-version drift —
      AGENTS.md's "Current State" now carries a condensed delta paragraph
      pointing to CLAUDE.md's full handoff and `docs/ZTF_DR24_PRODUCTION_GATES.md`)
- [x] Console output compliance: every `Skills/run_pipeline.py` stage print includes
      `elapsed {M}m{S:02d}s`; fetch ETA computed from time-per-survey; per-tracklet
      ETA computed from time-per-tracklet ✓ (2026-06-26, PR #116; satisfies CLAUDE.md
      standing rule: "elapsed-only heartbeats are not acceptable as a substitute for ETA")
- [x] Adversarial review skill: `Skills/adversarial_review.py` implemented with 11 offline
      challenges + 2 live challenges (MPC field scan, ATLAS cross-survey); 50+ tests in
      `tests/test_adversarial_review_skill.py`; all offline tests pass in CI; live challenges
      degrade gracefully to SKIP on network failure ✓ (2026-06-26, PR #116)

---

## Production Capability Gates (post-T1/T2; currently OPEN)

These gates define production readiness under the operator-approved definition
above. They intentionally do **not** require that the project has already found
a new NEO.

### Gate P1: Discovery-source positive control
- [x] Demonstrate that at least one unreviewed-archive discovery path
      (WISE/NEOWISE, DECam, or TESS) can produce a full `ScoredNEO` review
      packet when a valid moving-object signal is present. Acceptable evidence:
      known-object recovery through the discovery path, or a documented
      injection/recovery harness using source-specific cadence, noise,
      astrometry, photometry, and artifact assumptions.
- [x] The positive-control packet must satisfy the structural requirements for
      review: at least 3 detections, at least 2 nights when the source supports
      multi-night linking, orbit-quality code sufficient for the claimed use,
      full provenance, and no external submission.
- Current status: **CLOSED (2026-07-02)**. `Skills/injection_recovery.py --survey WISE`
      injects a source-native NEOWISE-visit-cadence synthetic tracklet (single-epoch
      W1 exposures, no native real/bogus score, ~1 arcsec astrometric jitter,
      0.08 mag photometric noise) through the real `detect.py` discovery-archive
      singleton path, `link.py`, `classify.py`, and `score.py`. Verified 100%
      detection/link/score rate (n=50, seed=42); committed baseline
      `data/injection_recovery_wise_baseline.json`; new CI job `wise-injection`
      in `.github/workflows/e2e.yml` asserts non-zero recovery on every push/PR.
      Evidence: `docs/evidence/prod-loop/2026-07-02-gate-p1-wise-injection-recovery.md`.
      The prior WISE/NEOWISE live diagnostics (most recently the v0.90.5
      support-positive subfield at RA `209.5`, Dec `-14.9`, radius `0.0303`,
      `0` tracklets after `58596` seed pairs) remain valid evidence that fetch,
      preprocessing, seed-pair budgeting, fail-closed review routing, and report
      writing all work correctly against real archive data — they simply did not
      contain a real NEO in that field/window, which is expected and does not
      block P1 once the positive-control harness proves the path itself works.

### Gate P2: Survey-native confidence policy
- [x] Document quantitative confidence thresholds for WISE/NEOWISE, DECam, and
      TESS discovery candidates. The policy must cover astrometric residuals,
      timing provenance, signal-to-noise or photometric quality, static-source
      rejection, satellite/artifact rejection, known-object checks, motion-rate
      plausibility, and orbit/link residuals.
- [x] The policy must explain how existing ML outputs map onto each discovery
      source. In particular, a missing or non-native ZTF real/bogus score must
      fail closed or be replaced by a source-appropriate evidence term; it must
      not silently pass as production confidence.
- [x] Apply `docs/neo_discovery_agent_brief.md` as the authoritative workflow
      brief for Gate P2. The policy must include a source-verification matrix
      for each production discovery source, record any auth/schema/rate-limit
      findings before ingestion code depends on them, and state how historical
      replay will avoid future-catalog leakage.
- [x] Treat ZTF DR24, Fink/Fink-FAT, and SNAPS as authoritative methodology,
      benchmarking, and candidate-ranker references from the brief, not as an
      automatic MPC discovery-submission stream. Any future ZTF/Fink discovery
      claim must first prove that it is not duplicating already processed survey
      submissions and must be documented as a new production decision.
- [x] Before any pretrained model contributes to production scoring, create the
      audit artifact required by the brief (`pretrained_model_audit.md` or a
      versioned equivalent under `docs/evidence/`), including exact model ID,
      source URL, license, download size, preprocessing, cache path, use mode,
      and decision (`use`, `defer`, or `reject`).
- Current status: **CLOSED (2026-07-02)**. `docs/SURVEY_NATIVE_CONFIDENCE_POLICY.md`
      documents the source-verification matrix (WISE live-verified across
      multiple runs; DECam and TESS code-complete but never live-verified),
      confirms `score.py:_determine_alert_pathway` already fails closed on the
      missing WISE/DECam/TESS real/bogus score (routes to `internal_candidate`
      unconditionally), records the no-future-catalog-leakage statement for the
      current live-discovery pipeline, reaffirms ZTF/Fink/SNAPS as
      reference-only per `docs/MISSION.md`, and records the pretrained-model
      audit requirement as not-yet-applicable (no third-party pretrained model
      is used in production scoring today). `Skills/run_pipeline.py` now prints
      an operator-visible warning when `--surveys DECam` or `--surveys TESS` is
      selected. Two items remain explicitly open for future work: a WISE
      sentinel-magnitude (`mag=99.0`) rejection filter, and DECam/TESS live
      endpoint verification.

### Gate P3: No-submission package drill
- [x] Run an end-to-end dry drill from a P1 positive-control packet through
      `Skills/adversarial_review.py`, operator review packet generation, and
      MPC-compatible export (`Skills/export_ades_report.py` preferred).
- [x] Verify the drill records no external submission, no impact-probability
      claim, and fail-closed behavior unless the operator has intentionally set
      every live-submission approval control.
- Current status: **CLOSED (2026-07-02)**. `Skills/injection_recovery.py` gained
      `--review-packet-out` to produce full `ScoredNEO` packets from the Gate P1
      WISE positive control. The drill piped a 5-candidate packet through
      `Skills/adversarial_review.py --offline` (5/5 `REJECT`, expected for a
      synthetic packet lacking a real/bogus score and short-arc orbit fit),
      then attempted `Skills/export_ades_report.py` twice: once with default
      arguments (failed closed — WISE requires station code C51), and once
      with `--obs-code C51` but no confirmation flag (failed closed
      independently — requires `--mpc-confirmed-wise-c51-submission`). No
      `.psv` file was written in either case; no network call occurred at any
      step (verified by code inspection — `export_ades_report.py` only
      imports the pure-string `format_mpc_ades_psv`). Evidence:
      `docs/evidence/prod-loop/2026-07-02-gate-p3-no-submission-drill.md`.

### Gate P4: MPC submission protocol
- [ ] Resolve and document the submission pathway for archival WISE/NEOWISE
      remeasurements before any WISE/NEOWISE live MPC submission. Required
      details: source attribution, station/observatory-code handling, ADES note
      usage, submitter/program metadata, and written MPC confirmation if `C51`
      is used for a third-party archival remeasurement.
- [ ] Keep `alert.py` and `Skills/export_ades_report.py` fail-closed until the
      protocol is recorded in `docs/MPC_SUBMISSION_POLICY.md` and the operator
      explicitly approves live submission.
- Current status: **open, dormant — no candidate exists yet, so there is
      nothing to contact MPC about**. This is not an active operator task.
      No real candidate has survived adversarial review, so there is no
      observation batch to attribute a station code to and no reason to
      initiate MPC correspondence today. This gate becomes relevant only if
      and when a real WISE-sourced candidate survives adversarial review and
      operator review (see `docs/OPERATOR_GO_NO_GO_RUNBOOK.md` Step 5) — at
      that point, and only then, the operator would contact MPC per
      `docs/MPC_SUBMISSION_POLICY.md §TODO for Future Agents — Archival WISE
      Submission Authority`. The code-level fail-closed guards
      (`alert.py`, `Skills/export_ades_report.py`) already exist and were
      verified in the Gate P3 drill, so this gate requires no further code
      work either — it simply cannot be marked CLOSED until a real
      submission-ready candidate exists to test the full pathway against.

### Gate P5: Operator go/no-go runbook
- [x] Maintain a one-page operator flow for the day a real candidate appears:
      review packet location, adversarial-review command, operator-review
      checklist, ADES export command, MPC submission authority check, and
      forbidden communications.
- [x] The flow must state that `SURVIVE` or `BORDERLINE` means "candidate may
      be reviewed for MPC submission," not "confirmed NEO" or any impact-risk
      assertion.
- Current status: **CLOSED (2026-07-02)**. `docs/OPERATOR_GO_NO_GO_RUNBOOK.md`
      is the one-page flow: review packet location, the exact
      `Skills/adversarial_review.py` and `Skills/export_ades_report.py`
      commands (verified against the Gate P3 drill), an operator-review
      checklist, the Gate P4 human-gated MPC-authority check, and the
      permanent forbidden-communications list. States explicitly that
      `SURVIVE`/`BORDERLINE` means "candidate may be reviewed for MPC
      submission," never "confirmed NEO" or an impact-risk claim.

---

## Discovery Event Gates (after production capability; event-driven)

These gates begin only after production capability is established and a real
candidate appears. They are sequential — each blocks the next — but they are not
required merely to declare the software production-capable.

### Gate D1: Real candidate survival (pipeline + adversarial review)
- [ ] At least one `ScoredNEO` passes `ready_for_submission()` gate from pipeline
- [ ] That candidate survives `Skills/adversarial_review.py` with verdict = SURVIVE
      (no FAILs; ≤1 WARNING across all 13 challenges)
- **fetch.py discovery layer is COMPLETE** (PR #119, 2026-06-27). Do NOT use
  `--surveys ZTF` or `--surveys ATLAS` for discovery — those streams are already
  processed by ZTF ZAPS and the ATLAS pipeline.
- Operator workflow template (from merged `main`; replace placeholders only
  with values emitted by selector output or documented field-window rationale):
  ```bash
  git pull origin main

  # Bound native numerical libraries to prevent oversubscription on the local Mac.
  export OMP_NUM_THREADS=1
  export OPENBLAS_NUM_THREADS=1
  export VECLIB_MAXIMUM_THREADS=1
  export NUMEXPR_MAX_THREADS=1
  export PYTHONPATH=src

  # Default remains dry-run unless explicitly approved elsewhere; this command
  # targets unreviewed WISE/NEOWISE archive data and writes review packets.
  caffeinate -i uv run --python 3.14 python Skills/run_pipeline.py \
      --ra <RA> --dec <Dec> --radius 3.5 \
      --start-jd <start> --end-jd <end> \
      --surveys WISE \
      --review-packet-out Logs/reports/<slug>_review_packets.json \
      --output Logs/reports/<slug>_candidates.json

  # Run adversarial review only if run_pipeline.py reports a non-zero full
  # ScoredNEO review-packet count.
  PYTHONPATH=src uv run --python 3.14 python Skills/adversarial_review.py \
      Logs/reports/<slug>_review_packets.json --offline --json
  ```
  Keep alert actions in dry-run mode during discovery sweeps. Real archive
  fetching does not require `--no-dry-run`; actual MPC submission remains
  fail-closed until `docs/MPC_SUBMISSION_POLICY.md §TODO for Future Agents —
  Archival WISE Submission Authority` is resolved and `alert.py` is configured
  with a confirmed observatory/source code plus `NEO_MPC_SUBMISSION_APPROVED=1`.


**Status (per the PIVOT NOTICE at the top of this file): still OPEN, and
not currently being worked.** A full sequence of WISE/NEOWISE Taurus and
non-Taurus field diagnostics (2026-06-27 through 2026-06-30, PRs #127-#136
plus the v0.90.2-v0.90.6 probe/scale-plan tooling) confirmed the
fetch/detect/link pipeline mechanics work correctly against real WISE
archive data, but every tracklet formed across every field tried was
near-stationary and artifact-dominated — rejected by adversarial review on
motion-rate and artifact-posterior grounds. **No candidate has ever passed
this gate via the WISE path.** Per DECISION-001 (`CLAUDE.md`) and the
2026-07-02 operator pivot, WISE/DECam/TESS is now secondary/paused; the
active discovery path is ZTF DR24 archival historical replay, tracked
separately via Gates Z1-Z7 in `docs/ZTF_DR24_PRODUCTION_GATES.md`. Do not
resume this WISE field-sweep work without explicit operator direction. The
full diagnostic-by-diagnostic trail (every field tried, every rejection
cause, every evidence file) is archived verbatim in
`docs/HANDOFF_HISTORY.md` under "PRODUCTION_READINESS.md historical
narrative — Gate D1".


### Gate D2: Operator Review
- [ ] Jerome W. Lindsey III reviews SURVIVE/BORDERLINE candidates
- [ ] Jerome approves at least one candidate for MPC submission
- Blocked by: Gate D1

### Gate D3: MPC Observatory Code (HUMAN DECISION REQUIRED)
- [ ] Jerome contacts MPC to establish how a data-analysis pipeline (not an observing
      telescope) can submit observation reports; or adopts a data-mining observatory
      code strategy
- See `docs/MPC_SUBMISSION_POLICY.md §TODO for Future Agents — Archival WISE Submission Authority` for full problem statement
- Blocked by: human administrative decision; no code can unblock this

### Gate D4: MPC Submission
- [ ] ADES PSV report generated via `Skills/export_ades_report.py`
- [ ] Submitted to MPC with verified observatory code
- Blocked by: Gates D2 and D3

### Gate D5: Provisional Designation
- [ ] MPC assigns a provisional designation (digest2 > 65 → object posted to NEOCP)
- Blocked by: Gate D4; MPC processes this automatically (~minutes after submission)

### Gate D6: Independent Confirmation
- [ ] Global follow-up observatories confirm independently via NEOCP
- [ ] NEOCP monitoring period complete (hours to days)
- Blocked by: Gate D5

### Gate D7: Discovery Paper
- [ ] MPEC publication by MPC (or equivalent) names the object
- [ ] Paper written documenting discovery with MPC designation as proof
- Blocked by: Gate D6

---

## Compliance Rule for Session Plans

Any plan proposed after reading this file must:

1. Name the highest-priority unresolved production-capability gate by its ID
   (for example, "P1: Discovery-source positive control" or
   "P2: Survey-native confidence policy").
2. Show how each proposed step closes or directly unblocks that gate.
3. Include outside blockers as explicit named steps (not glossed over).
4. Never propose log modules, schemas, or scaffolding that do not directly
   unblock a named production-capability gate or a still-authoritative T1/T2
   regression.
5. Never repeat work listed under "What Is Complete" above.
6. If the plan cannot close a production-capability gate because a human
   blocker is unresolved, it must explicitly state that and limit scope to
   directly related evidence, policy, or documentation sync.
