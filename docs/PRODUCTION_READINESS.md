# PRODUCTION_READINESS.md — NEO Pipeline Production Gap Register

**Current version**: v0.87.0  
**Last updated**: 2026-06-10
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
- 3475 offline tests pass; 2 live checks deselected; `ruff` clean; `mypy` clean
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
to train Tier 1 and Tier 2, but no real survey field has completed the full
pipeline and the Tier 3 production model is not trained.

---

## Tier 1 Gaps — Must Be Closed Before Production Operation

These gaps prevent the pipeline from being safely or usefully operated on real sky data. They are ordered by priority; the **highest-priority gap is listed first**.

### T1-A: Incomplete Trained ML Model Set (HIGHEST PRIORITY)

**What is missing**: The three-tier ML classifier is not yet complete.
- Tier 1 (XGBoost): **WEIGHTS TRAINED AND COMMITTED.** `models/tier1_xgb.json`; validation accuracy 99.95%, macro AUC 1.000.
- Tier 2 (CNN): **WEIGHTS TRAINED AND COMMITTED.** `models/tier2_cnn.pt`; trained on 10,000 real ZTF Avro alerts (8,000 train / 2,000 validation); best validation loss 0.258 and validation accuracy 91.3% at 20 epochs. Needs calibration evaluation before alert-gate use.
- Tier 3 (Transformer): `train_tier3_transformer.py` exists but no token CSV from real MPC tracklet sequences has been built. No `models/tier3_transformer.pt` file exists.  

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
- **Still needed**: A five-class real sequence dataset, Tier 3 Transformer
  training, and the complete production calibration KPI evaluation.

**What is needed to close it**:
1. [DONE] Download 10,000 labeled ZTF Avro alerts via `Skills/download_ztf_training_alerts.py`.
2. [DONE] MPC labels: `data/training_labels.csv` with 1000 labels.
3. [DONE] `Skills/build_cutout_dataset.py` — 10,000 `.npz` cutout triplets built.
4. [DONE] `Skills/train_tier2_cnn.py` — `models/tier2_cnn.pt` saved; val_acc=91.3%.
5. [DONE] Commit `models/tier2_cnn.pt` to repo (`.gitignore` updated to allow `models/*.pt`).
6. [DONE] Use the bounded, resumable
   `Skills/query_mpc_observations.py --labels-csv ...` collector to acquire
   versioned MPC histories with source hashes, query logs, and safety flags.
7. [APPROVED + OPERATOR RERUN] Execute the corrected 50-per-class pilot using provisional
   early-arc NEOs, numbered late-arc known NEOs, numbered MBAs, confirmed MPC
   comets, and ALeRCE high-confidence bogus ZTF histories through
   `Skills/run_tier3_pilot.py`.
8. [DONE] Validate the raw-data contract, create designation-grouped
   train/calibration/test splits, and build the flat token CSVs.
9. [HUMAN] Run the long Tier 3 training command under `caffeinate -i` to
   produce `models/tier3_transformer.pt` and a held-out JSON training report.
10. [DONE] Tier 1 XGBoost trained — val_acc=99.95%, macro AUC=1.000;
    `models/tier1_xgb.json` saved and committed at 13946ea.
11. [CODE] Evaluate with `Skills/evaluate_calibration.py` and apply the
    production calibration KPI gate defined under T1-D. Promotion is automatic
    only when every required KPI passes.

**Blocking outside step**: The label-policy decision is complete. Step 7 now
requires the human operator to run the approved read-only network pilot on the
Mac and return its JSON evidence. Step 9 requires an operator-run training job
on the available compute hardware.
Calibration promotion itself has no human-review dependency; it is controlled
by the quantitative T1-D gate.

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

**What is missing**: The full pipeline (`Fetch → Preprocess → Detect → Link → Classify → Score → Alert`) has never run on real photometric data from ZTF, ATLAS, or Pan-STARRS. All injection-recovery and smoke tests use synthetic observations built from `SimpleNamespace` objects.

**Why it is Tier 1**: Synthetic data cannot expose real failure modes — coordinate edge cases, survey-specific format quirks, real noise distributions, real artifact morphologies, or real rate-limiting behavior. The pipeline's real-world correctness is unknown until it processes real data.

**What is needed to close it**:
1. [DEPENDS ON T1-B] Complete the automated live-review policy approval; the
   credentials and manual provider connection tests are already complete.
2. [CODE] Run `Skills/run_pipeline.py` on a small real ZTF field (e.g., 1-degree cone, single night) in dry-run mode.
3. [CODE + HUMAN] Manually inspect pipeline output against MPC known objects in that field; verify ≥90% known-object recovery rate.
4. [CODE] Run `Skills/check_mpc_known.py` on pipeline output to audit cross-match completeness.
5. [HUMAN] Human expert reviews candidate output for any false positives that passed all gates.

**Blocking outside step**: The automated live-review policy must be approved
first. Step 5 requires human expert review of candidate false positives; this
is separate from calibration promotion.

---

### T1-D: No Production Ensemble Calibration

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
5. [CODE] Emit a machine-readable calibration report containing dataset
   provenance, model hashes, calibrator method, all KPI values, thresholds, and
   a single `promotion_gate_passed` boolean.
6. [FAIL CLOSED] If any KPI is missing or fails, keep alert gates unarmed,
   apply Platt or isotonic recalibration as appropriate, and rerun the complete
   gate. No metric may be waived manually.

**Blocking outside step**: T1-A must be resolved first and a sufficiently sized
held-out real labeled dataset must exist. There is no human calibration-review
or sign-off requirement.

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
| Approved five-class pilot data acquisition | Human operator (network/data access; policy approved 2026-06-10) | T1-A Tier 3 |
| GPU or CPU training run for Tier 3 Transformer | Human operator (compute resource) | T1-A |
| Expert review of ML architecture | NEO survey astronomer | T2-C |
| Live review policy sign-off | Human reviewer | T1-B |

---

## Production Readiness Checklist

Before the pipeline makes its first MPC submission, all of the following must be TRUE:

- [~] T1-A resolved: Tier 2 CNN trained ✓ (val_acc=91.3%); Tier 1 XGBoost trained ✓ (val_acc=99.95%); Tier 3 Transformer weights still needed
- [ ] T1-A resolved: Tier 3 Transformer trained on real multi-night sequences
- [~] T1-B resolved: IRSA and ATLAS credentials configured ✓; live connection test passed ✓; automated live dry-run policy not yet signed off (pending human reviewer signature)
- [ ] T1-C resolved: Full pipeline run completed on ≥1 real ZTF field; ≥90% known-object recovery verified
- [ ] T1-D resolved: Machine-readable calibration report passes every required
      KPI on held-out real labeled data and records
      `promotion_gate_passed=true`
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
