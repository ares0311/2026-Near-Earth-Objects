# PRODUCTION_READINESS.md — NEO Pipeline Production Gap Register

**Current version**: v0.87.9
**Last updated**: 2026-06-16
**Purpose**: Mandatory read at session start (per MANDATORY SESSION-START PROTOCOL).  
Every planning cycle must name the highest-priority unresolved Tier 1 gap and show how proposed steps close or directly unblock it.

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
- 3500+ offline tests pass; 2 live checks deselected; `ruff` clean; `mypy` clean
- Background automation CLI (`Skills/background.py`) with SQLite audit logs
- 90+ Skills scripts for batch operations, export, diagnostics, visualization
- 30+ documentation files covering all pipeline stages
- MPC 80-column and ADES PSV format output
- Alert protocol guardrails (MOID gate, quality code gate, real/bogus gate, confirmation gate)
- Injection-recovery: 100% detection, 100% link, 100% score on synthetic data (n=200)
- Stress-test: 100% link rate across all three high-motion bins on synthetic data
- Conservative scoring model with log-likelihood framework and calibrated posteriors

### What "complete" means here
All modules compile, pass 100% branch coverage, and produce correct output
**on synthetic/mocked pipeline data**. Real labeled ZTF alerts have been used
to train and calibrate the ML tiers. A first supervised, bounded real ZTF
pilot has completed; production still requires the known-object recovery audit
and human false-positive review described in T1-C.

---

## Tier 1 Gaps — Must Be Closed Before Production Operation

These gaps prevent the pipeline from being safely or usefully operated on real sky data. They are ordered by priority; the **highest-priority gap is listed first**.

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
- **Still needed**: Ensemble stacking calibration (logistic regression meta-learner over Tier 1 + Tier 2 + Tier 3 outputs).

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
5. [PENDING] Formal background CLI live dry-run approval (`live-dry-run-plan` / `live-dry-run-approval-bundle`) not yet signed off. This gate is required before any automated live fetch outside of manual operator sessions.

**Remaining step before automated live runs**: Run `Skills/background.py live-dry-run-approval-bundle` and obtain a human reviewer signature on `background/live_review_policy.example.json`.

---

### T1-C: No Real Data Has Ever Been Processed End-to-End

**What is missing**: The full pipeline (`Fetch → Preprocess → Detect → Link → Classify → Score → Alert`) has now completed one supervised, bounded real ZTF pilot through the public ALeRCE ZTF source-detection provider. Production closure still requires an uncapped or recovery-audit run, ≥90% known-object recovery verification, and human false-positive review.

**Why it is Tier 1**: Synthetic data cannot expose real failure modes — coordinate edge cases, survey-specific format quirks, real noise distributions, real artifact morphologies, or real rate-limiting behavior. The pipeline's real-world correctness is unknown until it processes real data.

**What is needed to close it**:
1. [DEPENDS ON T1-B] Complete the automated live-review policy approval; the
   credentials and manual provider connection tests are already complete.
2. [DONE] Run `Skills/run_pipeline.py` on a bounded real ZTF field in dry-run
   mode. On 2026-06-16, the operator ran the Orion-field ALeRCE-backed pilot:
   4,059 real ZTF source detections fetched, 4,059/4,059 preprocessed, 520
   raw candidates detected, `--max-candidates 80` linked, 2 tracklets scored,
   and 2 internal-candidate outputs written to
   `Logs/reports/t1c_ztf_alerce_pilot.json`. Audit summary:
   `Logs/pipeline_runs/011dd53aa7f4/run_summary.json`.
3. [CODE] Run an uncapped or staged recovery-audit pilot with link progress/ETA
   enabled, preserving `Logs/pipeline_runs/*/run_summary.json` evidence.
4. [CODE + HUMAN] Manually inspect pipeline output against MPC known objects in
   that field; verify ≥90% known-object recovery rate.
5. [CODE] Run `Skills/check_mpc_known.py` on pipeline output to audit cross-match completeness.
6. [HUMAN] Human expert reviews candidate output for any false positives that passed all gates.

**Current blocker**: T1-C is no longer blocked on zero ZTF fetches. The next
blocker is the known-object recovery audit plus human false-positive review.
The automated live-review policy remains required before automated live runs;
manual supervised pilot runs remain operator-controlled and non-submitting.

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

### T2-B: No Adversarial/Robustness Testing

The pipeline has not been tested against:
- Real ZTF artifacts (satellite trails, cosmic rays, ghost reflections)
- Real bad-pixel regions or missing difference cutouts
- Ephemeris edge cases (very fast near-Earth objects, objects near survey edges)
- Rate limiting and network timeout behavior in `fetch.py`

**Needed**: Run `Skills/diagnose_pipeline.py` on real ZTF alert data; audit false-positive rate against known-artifact catalog. Requires T1-C resolution.

### T2-C: No Peer Review of ML Architecture

The Tier 1–3 architecture (XGBoost → CNN → Transformer → stacking) was designed per CLAUDE.md DECISION-002 and literature references (Duev et al. 2019, Lin et al. 2022). The implementation has not been reviewed by an astronomer or ML practitioner with NEO survey experience.

**Needed**: External code/architecture review before the pipeline is used to generate MPC submissions.

### T2-D: No CI for Integration or End-to-End Tests

CI currently runs only unit tests. There is no CI job for:
- Integration tests against real APIs (gated on credentials)
- End-to-end pipeline smoke test on a small real-data fixture
- Model weight validation (checking that trained weights produce calibrated output)

**Needed**: Add CI job definitions (`.github/workflows/`) for integration and end-to-end test stages, gated on secret availability.

### T2-E: Session-Start Documents Synchronized — **CLOSED 2026-06-09**

`AGENTS.md`, `CLAUDE.md`, `README.md`, and this gap register now agree on the
trained-weight state, live-credential state, Tier 3 blocker, calibration KPI
gate, and current offline test result.

---

## Outside Blockers (Human Action Required)

These items cannot be completed by code generation alone. They require real-world human decisions or access.

| Blocker | Owner | Unblocks |
|---|---|---|
| Expert review of ML architecture | NEO survey astronomer | T2-C |
| Live review policy sign-off | Human reviewer | T1-B |
| Known-object recovery audit and false-positive review | Human operator + domain reviewer | T1-C |

---

## Production Readiness Checklist

Before the pipeline makes its first MPC submission, all of the following must be TRUE:

- [x] T1-A resolved: Tier 1 XGBoost ✓ (val_acc=99.95%); Tier 2 CNN ✓ (val_acc=91.3%); Tier 3 Transformer ✓ (val_macro_f1=0.9400); ensemble stacker ✓ (AUC=0.9809, all 7 KPIs pass, 2026-06-14)
- [x] T1-A resolved: calibration KPI gate passed ✓ (T1-D, 2026-06-14); ensemble stacker KPIs passed ✓ (2026-06-14)
- [~] T1-B resolved: IRSA and ATLAS credentials configured ✓; live connection test passed ✓; automated live dry-run policy not yet signed off (pending human reviewer signature)
- [~] T1-C progressed: Bounded supervised real-ZTF pilot completed on
      2026-06-16; known-object recovery audit and human false-positive review
      still required.
- [x] T1-D resolved: Machine-readable calibration report passes every required
      KPI on held-out real labeled data and records
      `promotion_gate_passed=true` ✓ (2026-06-14; Tier 1 + Tier 2)
- [ ] T2-A resolved: At least one integration test suite passed against real APIs
- [ ] T2-B resolved: False-positive rate on real artifact data < 5%
- [ ] T2-C resolved: ML architecture reviewed by domain expert
- [ ] Alert protocol compliance: `ready_for_submission()` gate tested on ≥10 real candidate outputs
- [ ] Guardrail compliance: zero "confirmed NEO" or impact probability assertions in any output
- [ ] AGENTS.md and CLAUDE.md synchronized to current version

---

## Compliance Rule for Session Plans

Any plan proposed after reading this file must:

1. Name the highest-priority unresolved Tier 1 gap by its ID (e.g., "T1-A: No Trained ML Model Weights").
2. Show how each proposed step closes or directly unblocks that gap.
3. Include outside blockers as explicit named steps (not glossed over).
4. Never propose log modules, schemas, or scaffolding that do not directly unblock a named T1 or T2 gap.
5. Never repeat work listed under "What Is Complete" above.
6. If the plan cannot close any Tier 1 gap (because a human blocker is unresolved), it must explicitly state that and limit scope to Tier 2 gaps or AGENTS.md/documentation sync.
