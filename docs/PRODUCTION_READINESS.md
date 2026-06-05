# PRODUCTION_READINESS.md — NEO Pipeline Production Gap Register

**Current version**: v0.87.0  
**Last updated**: 2026-06-05  
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
- 3467 unit tests; all pass; `ruff` clean; `mypy` clean
- Background automation CLI (`Skills/background.py`) with SQLite audit logs
- 90+ Skills scripts for batch operations, export, diagnostics, visualization
- 30+ documentation files covering all pipeline stages
- MPC 80-column and ADES PSV format output
- Alert protocol guardrails (MOID gate, quality code gate, real/bogus gate, confirmation gate)
- Injection-recovery: 100% detection, 100% link, 100% score on synthetic data (n=200)
- Stress-test: 100% link rate across all three high-motion bins on synthetic data
- Conservative scoring model with log-likelihood framework and calibrated posteriors

### What "complete" means here
All modules compile, pass 100% branch coverage, and produce correct output **on synthetic/mocked data**. No real NEO has ever been processed. No real survey data has been ingested. No trained model weights exist.

---

## Tier 1 Gaps — Must Be Closed Before Production Operation

These gaps prevent the pipeline from being safely or usefully operated on real sky data. They are ordered by priority; the **highest-priority gap is listed first**.

### T1-A: No Trained ML Model Weights (HIGHEST PRIORITY)

**What is missing**: The three-tier ML classifier has no trained weights.  
- Tier 1 (XGBoost): `classify.py` initializes untrained models. `CandidateFeatures` are populated but the XGBoost decision function returns random/prior scores until trained on real labeled data.  
- Tier 2 (CNN): `train_tier2_cnn.py` exists but no `.npz` cutout dataset has been built from real ZTF alerts. No `models/tier2_cnn.pt` file exists.  
- Tier 3 (Transformer): `train_tier3_transformer.py` exists but no token CSV from real MPC tracklet sequences has been built. No `models/tier3_transformer.pt` file exists.  

**Why it is Tier 1**: Without trained weights, every candidate scores at prior probability (~5% NEO). The pipeline cannot distinguish real NEOs from artifacts on live data. All downstream hazard flags and alert pathways are meaningless without this.

**What is needed to close it**:
1. [HUMAN BLOCKER] Obtain ~100,000 labeled ZTF alerts (real/bogus) from Duev et al. (2019) dataset or IRSA broker. Requires IRSA account and ~GB-level download.
2. [HUMAN BLOCKER] Obtain MPC confirmed NEO catalog as positive labels (`Skills/generate_training_labels.py` is ready but needs network access).
3. [CODE] Run `Skills/build_cutout_dataset.py` on downloaded ZTF alert JSON to produce `.npz` + CSV index.
4. [CODE] Run `Skills/train_tier2_cnn.py` on the `.npz` dataset to produce `models/tier2_cnn.pt`.
5. [CODE] Run `Skills/build_sequence_dataset.py` on MPC tracklet data to produce flat token CSV.
6. [CODE] Run `Skills/train_tier3_transformer.py` on the token CSV to produce `models/tier3_transformer.pt`.
7. [CODE] Retrain Tier 1 XGBoost stacker on combined real/bogus + MPC NEO labels.
8. [CODE + HUMAN] Evaluate with `Skills/evaluate_calibration.py`; require Brier score < 0.10 and ECE < 0.05 before approval.

**Blocking outside step**: Steps 1–2 require human action (credentials, download). Steps 3–8 can proceed once the data exists.

---

### T1-B: No Real Survey Credentials Configured

**What is missing**: No IRSA account, no ATLAS API token, no live fetch has ever succeeded.  
- `fetch_ztf_alerts()` is mocked in all tests. The live code path has never been executed against real data.  
- `fetch_atlas_forced()` requires an `ATLAS_TOKEN` environment variable that has never been provided.  
- `fetch_panstarrs_catalog()` requires a MAST/astroquery account.  

**Why it is Tier 1**: Without credentials, the pipeline cannot ingest any real survey data, making T1-A impossible and making any live run impossible.

**What is needed to close it**:
1. [HUMAN BLOCKER] Create free IRSA account at irsa.ipac.caltech.edu; generate API token.
2. [HUMAN BLOCKER] Register at fallingstar-data.com for an ATLAS forced-photometry token.
3. [CODE] Configure credentials in `background/config.json` (credential names already declared; no secrets in repository).
4. [CODE] Run `Skills/background.py live-dry-run-plan` and `live-dry-run-approval-bundle` to validate readiness before any live fetch.
5. [CODE + HUMAN] Approve live review policy (`background/live_review_policy.example.json`) with a reviewer signature.

**Blocking outside step**: Steps 1–2 require human action (external registration).

---

### T1-C: No Real Data Has Ever Been Processed End-to-End

**What is missing**: The full pipeline (`Fetch → Preprocess → Detect → Link → Classify → Score → Alert`) has never run on real photometric data from ZTF, ATLAS, or Pan-STARRS. All injection-recovery and smoke tests use synthetic observations built from `SimpleNamespace` objects.

**Why it is Tier 1**: Synthetic data cannot expose real failure modes — coordinate edge cases, survey-specific format quirks, real noise distributions, real artifact morphologies, or real rate-limiting behavior. The pipeline's real-world correctness is unknown until it processes real data.

**What is needed to close it**:
1. [DEPENDS ON T1-B] Obtain live credentials (T1-B must be resolved first).
2. [CODE] Run `Skills/run_pipeline.py` on a small real ZTF field (e.g., 1-degree cone, single night) in dry-run mode.
3. [CODE + HUMAN] Manually inspect pipeline output against MPC known objects in that field; verify ≥90% known-object recovery rate.
4. [CODE] Run `Skills/check_mpc_known.py` on pipeline output to audit cross-match completeness.
5. [HUMAN] Human expert reviews candidate output for any false positives that passed all gates.

**Blocking outside step**: T1-B must be resolved first. Step 5 requires human expert review.

---

### T1-D: No Production Ensemble Calibration

**What is missing**: The stacking meta-learner (logistic regression) and Platt/isotonic calibration in `calibration.py` have been trained on no real data. The calibration curves have not been validated on a held-out real-data test set. `compute_ece()`, `compute_brier_score()`, and `reliability_diagram()` all work on synthetic probabilities in tests; they have never been run on real model outputs.

**Why it is Tier 1**: Uncalibrated probabilities mean the alert pathway gate conditions (e.g., `real_bogus_score ≥ 0.90`) are meaningless. A model that outputs 0.90 for 50% of its candidates is not calibrated; the gate will either pass too many artifacts or suppress genuine NEOs.

**What is needed to close it**:
1. [DEPENDS ON T1-A] Trained model weights must exist first (T1-A).
2. [CODE] Run `Skills/evaluate_calibration.py` on held-out labeled data.
3. [CODE] Run `Skills/plot_calibration.py` to generate reliability diagrams.
4. [HUMAN] Human expert must review reliability diagrams and approve calibration quality before live alert gates are armed.
5. [CODE] If calibration fails (ECE > 0.05), apply isotonic regression recalibration and re-evaluate.

**Blocking outside step**: T1-A must be resolved first. Step 4 requires human expert review and sign-off.

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

### T2-E: AGENTS.md Is Outdated

`AGENTS.md` currently shows `Current State (v0.76.0)` and does not list any Skills, Docs, or Key Changes added in v0.77.0–v0.87.0. This means the mandatory session-start read of `AGENTS.md` provides a stale picture of the codebase.

**Needed**: Update `AGENTS.md` to v0.87.0 to match `CLAUDE.md`. This is a documentation-sync task that directly supports the mandatory session-start protocol and does not require new code.

---

## Outside Blockers (Human Action Required)

These items cannot be completed by code generation alone. They require real-world human decisions or access.

| Blocker | Owner | Unblocks |
|---|---|---|
| IRSA account + API token | Human operator | T1-B, T1-C, T2-A |
| ATLAS forced-photometry token | Human operator | T1-B, T1-C, T2-A |
| ZTF real/bogus labeled dataset (~100K alerts) | Human operator (download from IRSA) | T1-A |
| MPC confirmed NEO + MBA catalog download | Human operator (network access) | T1-A |
| GPU or CPU training run for Tier 2 CNN | Human operator (compute resource) | T1-A |
| GPU or CPU training run for Tier 3 Transformer | Human operator (compute resource) | T1-A |
| Expert review of calibration reliability diagram | Astronomer / ML reviewer | T1-D |
| Expert review of ML architecture | NEO survey astronomer | T2-C |
| Live review policy sign-off | Human reviewer | T1-B |

---

## Production Readiness Checklist

Before the pipeline makes its first MPC submission, all of the following must be TRUE:

- [ ] T1-A resolved: Tier 1 XGBoost, Tier 2 CNN, and Tier 3 Transformer weights trained on ≥10,000 real labeled examples each
- [ ] T1-A resolved: Brier score < 0.10 and ECE < 0.05 on held-out real-data test set
- [ ] T1-B resolved: IRSA and ATLAS credentials configured; live dry-run approved by human reviewer
- [ ] T1-C resolved: Full pipeline run completed on ≥1 real ZTF field; ≥90% known-object recovery verified
- [ ] T1-D resolved: Calibration reliability diagrams reviewed and approved by human expert
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
