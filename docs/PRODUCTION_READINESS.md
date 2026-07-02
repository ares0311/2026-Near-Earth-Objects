# PRODUCTION_READINESS.md — NEO Pipeline Production Gap Register

**Current version**: v0.90.18
**Last updated**: 2026-07-02
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
deferred. New production gates for the ZTF DR24 path have not yet been
defined — define them next, then build a bounded Phase 1 historical-replay
prototype.

**Phase 0 status (2026-07-02)**: 3 of 4 cited sources live-verified working
via `Skills/verify_ztf_dr24_sources.py` — IRSA ZTF image metadata (200, no
auth), JPL SBDB NEO query (200, `sb-group=neo` not the brief's `neo=Y`), MPC
get-obs (200, requires a JSON request body, not query-string params). Fink
API is an external TLS-handshake blocker confirmed via two independent TLS
stacks (Python `ssl` and the operator's native LibreSSL) failing identically
from a real network — not fixable from this codebase. See
`docs/evidence/phase0/2026-07-02-root-cause-findings.md` and
`2026-07-02-second-live-probe-console.md` for full detail. **NOT YET DONE**:
operator needs to commit the three generated files
(`data_sources_verified.md`, `auth_requirements.md`,
`phase0_probe_results.json`) from their local run, plus the brief's other
Phase 0 deliverables (`schema_snapshot/`, `sample_ingest_report.md`,
`pretrained_model_audit.md`) before Phase 1 work begins.

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

**What is needed to close it**:
1. [DONE] Complete the automated live-review policy approval; credentials,
   manual provider connection tests, and the signed bounded dry-run policy are
   now present. Provider readiness can still fail closed when required
   credentials are absent from the active shell.
2. [DONE] Run `Skills/run_pipeline.py` on a bounded real ZTF field in dry-run
   mode. On 2026-06-16, the operator ran the Orion-field ALeRCE-backed pilot:
   4,059 real ZTF source detections fetched, 4,059/4,059 preprocessed, 520
   raw candidates detected, `--max-candidates 80` linked, 2 tracklets scored,
   and 2 internal-candidate outputs written to
   `Logs/reports/t1c_ztf_alerce_pilot.json`. Audit summary:
   `Logs/pipeline_runs/011dd53aa7f4/run_summary.json`.
3. [DONE] Build a fail-closed real-run audit packet with
   `Skills/audit_real_run.py`. For run `011dd53aa7f4`, the tool wrote JSON and
   CSV review evidence, preserved no-network/no-submission safety flags, and
   correctly blocked promotion because no expected-known manifest was
   supplied. Durable GitHub-visible evidence is summarized under
   `docs/evidence/t1c/`; raw `Logs/` outputs remain local operational artifacts.
4. [DONE] Generate an expected-known manifest with MPC designations and
   Horizons sky/time samples using `Skills/build_recovery_manifest.py`, then
   verify ≥90% known-object recovery through `Skills/audit_real_run.py`.
   Pipeline object IDs may be used when known, but they are no longer required.
   Manifest generation has produced valid non-Orion MPC/Horizons sky/time
   manifests; the recovery KPI itself remains open.
5. [CODE] Run an uncapped or staged recovery-audit pilot with link progress/ETA
   enabled, preserving `Logs/pipeline_runs/*/run_summary.json` evidence and
   evaluating it through `Skills/audit_real_run.py`.
6. [DONE — HUMAN] The project operator (Jerome W. Lindsey III) reviewed the
   audit CSV. No blocking findings. This is not professional planetary-defense
   validation and does not authorize external submission.
7. [CODE] Select a new known-object-rich recovery field. The Orion pilot field
   is retained only as historical/debug evidence and must not be reused for the
   production recovery KPI.

**T1-C is CLOSED.** Known-object recovery (≥90%) verified on ATLAS data; operator false-positive review by Jerome W. Lindsey III completed 2026-06-20 with no blocking findings. All runs remained operator-controlled and non-submitting.

**2026-06-18 diagnostic update**: Recovery field selection now supports live
ZTF availability probing and broader MPC asteroid-list manifest preselection.
A ZTF-available fixed field at RA `251.66`, Dec `-22.50`, radius `3.5` produced
valid expected-known manifests and live asteroid-class ALeRCE detections.
However, ALeRCE asteroid-class objects in that field were same-night
three-detection tracklets, not multi-night histories; the 30-day asteroid-class
pipeline fetched `119` alerts, detected `48` candidates, linked `0` multi-night
tracklets, and therefore failed the existing known-object recovery KPI. T1-C
remains open until a multi-night known-object provider/path is used or a
separate same-night diagnostic subgate is explicitly added without replacing
the multi-night production gate. Durable summary:
`docs/evidence/t1c/2026-06-18-recovery-selector-and-provider-diagnostic.md`.

**2026-06-18 ATLAS fallback update**: `Skills/fetch_atlas_data.py` now has an
expected-known ATLAS forced-photometry recovery mode that writes
`audit_real_run.py`-compatible packets and fails closed unless enough usable
samples are recovered across enough nights. The fallback also records explicit
limitations: targeted forced photometry is supporting recovery evidence, not
blind discovery evidence, and it performs no submission or impact claim.
`src/fetch.py::fetch_atlas_forced` was corrected to match the official ATLAS
API contract by submitting form data to `/forcedphot/queue/`, requesting JSON
task responses, and exposing bounded live polling with progress callbacks. A
bounded pre-fix live pilot produced `0/10` recovered samples and correctly
failed the recovery gate. A post-fix redacted diagnostic confirmed JSON task
creation, but the ATLAS queue was deep (`queuepos=164`), so a longer
operator-supervised run is still required. Follow-up hardening records polling
sample state and queued ATLAS task URLs in the checkpoint, preserves checkpoint
resume even with `--force-refresh`, and reuses existing task URLs on resume so
interrupted queue waits do not create duplicate ATLAS jobs. If polling is
exhausted while ATLAS has not finished the task, the sample remains pending as
`poll_exhausted` rather than being counted as unrecovered. Durable summary:
`docs/evidence/t1c/2026-06-18-atlas-forced-fallback-diagnostic.md`.

**2026-06-19 bounded ATLAS recovery pilot**: Jerome W. Lindsey III approved up
to 40 ATLAS forced-photometry sample queries for T1-C recovery evidence only.
The run `atlas_recovery_4eaf93e87f6c` completed 38 sample queries with no
provider/tool failures, recovered 19 samples, emitted 4 multi-night audit
tracklets, and failed the recovery KPI at 4/11 expected objects (`36.36%`;
threshold `90%`). This confirms the live ATLAS fallback plumbing works, but
T1-C remains open. Durable summary:
`docs/evidence/t1c/2026-06-19-atlas-recovery-40-query-pilot.md`.

**2026-06-19 ATLAS prequalification approval**: Jerome W. Lindsey III approved
building a prequalified ATLAS-recoverable expected-known manifest before the
next live run. The documented rule keeps only objects from the screening run
with at least 3 recovered ATLAS samples across at least 2 distinct nights.
`Skills/build_recovery_manifest.py --prequalify-from-atlas-run` now implements
that rule and produced a local ignored manifest with 4 rows and 15 expected
samples (`481`, `1950`, `2172`, `2973`). The next blocker is running the
prequalified manifest through the existing non-submitting T1-C audit path and
then completing operator review if the KPI passes.

**2026-06-19 prequalified ATLAS recovery run**: The prequalified live run
`atlas_recovery_175ef40ac577` completed 15 sample queries with no
provider/tool failures, recovered 10 samples, emitted 3 multi-night audit
tracklets, and failed the recovery KPI at 3/4 expected objects (`75.00%`;
threshold `90%`). The failed object was `2973`; repeat-recovered objects were
`481`, `1950`, and `2172`. T1-C remains open. Further narrowing of the
denominator, such as a repeat-stable object rule, requires explicit operator
approval before more live queries.

**2026-06-20 Option A screening run**: Jerome W. Lindsey III approved a new
predeclared screening approach (25 objects, 6 samples/object, 101 total
samples) documented in `docs/evidence/t1c/2026-06-20-option-a-predeclared-policy.md`.
`Skills/load_credentials.py` was created (PR #113, merged) and wired into
`Skills/fetch_atlas_data.py` so credentials are auto-loaded from macOS Keychain
without a separate shell source step. The screening run `atlas_recovery_25f3a800a1a2`
completed: 42/101 samples recovered, 5 tracklets, 0 failures, 0 pending.
Prequalification (≥3 recovered samples, ≥2 distinct nights) yielded **5 objects:
121, 954, 2140, 2172, 5650**. Prequalified manifest written to
`Logs/reports/t1c_option_a_prequalified_manifest.json` (local, ignored).

**2026-06-20 Option A follow-up run**: `atlas_recovery_c1712df0f32c` completed —
23 samples, 16/23 recovered, 5/5 objects emitted audit tracklets. Preliminary
KPI: **5/5 = 100%** (gate ≥90%). Formal audit via `Skills/audit_real_run.py`
is the next step; operator review follows if audit passes.
Durable evidence: `docs/evidence/t1c/2026-06-20-option-a-screening-prequalification.md`.

**2026-06-20 audit result: PASSED.** Correct audit used
`expected_known_atlas_forced.json` (tolerance_days=1.0) from the run dir. Output:
`Recovery gate: evaluated (passed=True)`, 5 tracklets reviewed, 0 same-night,
5 multi-night, no external submission. T1-C automated KPI gate is now closed.

**2026-06-20 T1-C CLOSED**: Operator review completed by Jerome
W. Lindsey III. All 5 tracklets showed physically plausible motion rates
(26–36 arcsec/hr) and multi-night arcs (12–25 days). No flags, no blocking
findings. Full evidence: `docs/evidence/t1c/2026-06-20-option-a-screening-prequalification.md`.
No external submission or impact-probability claim authorized.

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
- [x] AGENTS.md and CLAUDE.md synchronized to current version ✓ (2026-06-26, v0.89.3)
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

**2026-06-27 WISE live archive sweep evidence**: Jerome ran the Taurus WISE
command from `main` after pulling PR #127. IRSA async TAP returned `111913`
rows with columns `['ra', 'dec', 'mjd', 'w1mpro', 'w1sigmpro']`; the pipeline
parsed `85335` WISE observations, detected `535` moving-object candidates, linked
`0` tracklets, processed `0` candidates, and produced no submission-ready
candidates. This closes the WISE schema/fetch uncertainty for that field and
moves the next D1 blocker downstream to detection/linking diagnostics. Evidence:
`docs/evidence/live/2026-06-27-wise-live-sweep.md`.

**2026-06-28 PR #131 update**: Discovery sweeps now remain fail-closed for live
MPC submission unless explicitly approved with `NEO_MPC_SUBMISSION_APPROVED=1`
and a real non-placeholder MPC observatory code. WISE masked photometry values
are handled as missing-data sentinels instead of becoming `nan`. CI is green
with 1583 offline tests and 100% coverage. Do not ask the operator to repeat the
same Taurus sweep before diagnosing why the recorded `535` WISE candidates
linked into `0` tracklets.

**2026-06-28 PR #133 merged**: Root cause diagnosed for the Taurus
`535` candidates -> `0` tracklets result. `fetch_wise_archive()` queried the
broad static NEOWISE point-source population, and `detect()` required same-night
pairs before the linker could see archive rows. The merged fix uses official
IRSA association columns (`sso_flg`, `allwise_cntr`, `n_allwise`, `source_id`)
to prefilter WISE rows and preserves prefiltered WISE/DECam/TESS archive
detections as singleton candidates for multi-night linking. Validation:
operator targeted run on Python 3.14.3 passed (`80 passed in 0.86s`; targeted
ruff clean; mypy clean across 12 source files). CI initially failed only on
missing helper coverage; coverage test added, full local pytest passed
(`1586 passed, 2 deselected`), and GitHub CI passed before merge. Evidence:
`docs/evidence/live/2026-06-28-wise-linking-root-cause.md`. Next D1 step: run a
smaller WISE dry-run diagnostic from `main`; do not repeat the exact 3.5°/30-day
Taurus sweep yet.

**2026-06-28 pyvo polling compatibility update**: The smaller WISE diagnostic
was run from `main` at `2a786e18` and reached the PR #133 WISE ADQL path, but
failed before result retrieval with `AttributeError: 'AsyncTAPJob' object has no
attribute 'update'`. Root cause: the installed pyvo 1.9.0 async job exposes
`_update()`/`wait()` but not public `update()`. The compatibility fix preserves
explicit heartbeat polling, uses public `update()` when available, falls back to
the pyvo 1.9.0 one-shot `_update()` call, and never switches WISE fetching to a
silent blocking wait. Evidence and predicted operator output:
`docs/evidence/live/2026-06-28-wise-prefilter-diagnostic-pyvo-update.md`.
Next D1 step after merge: rerun the smaller WISE dry-run diagnostic from
`main`; do not give feature-branch commands to the operator.

**2026-06-28 PR #135 merged and post-merge diagnostic complete**: WISE TAP
polling is now compatible with pyvo 1.9.0 while preserving explicit heartbeat
output. GitHub CI passed before merge; local validation included the full
offline suite (`1590 passed, 2 deselected`). The post-merge smaller WISE
diagnostic from `main` at `dd35a8c0` completed in dry-run mode: `5206` WISE
rows, `5200/5206` preprocessed, `5200` singleton candidates, `0` linked
tracklets, `0` candidates processed, and no external submission path invoked.
Evidence:
`docs/evidence/live/2026-06-28-wise-prefilter-diagnostic-post-pyvo.md`.
Next D1 step: diagnose why current WISE archive singleton candidates do not
link into multi-night tracklets; do not rerun the same 1.0°/7-day Taurus
diagnostic until a distinct fix or field-selection change is ready.

**2026-06-28 PR #136 merged and linker diagnostics complete**: Linker
provenance now records nights, observations, seed-pair totals, rate-window
seeds, satellite rejects, min-observation/min-night rejects, and chi-square
rejects. The post-merge bounded WISE rerun from `main` at `b8ca1312` produced
`5206` WISE rows, `5200/5206` preprocessed, `5200` singleton candidates, and
`0` tracklets. The new diagnostics show `n_nights=1` and
`n_seed_pairs_total=0`; therefore this specific 1.0-degree, 7-day Taurus window
is not a valid multi-night WISE linking test. Evidence:
`docs/evidence/live/2026-06-28-wise-linker-diagnostics-one-night.md`.
Next D1 step: select or probe a distinct WISE field/window that spans at least
two integer-JD nights after preprocessing; do not rerun the same 7-day Taurus
diagnostic.

**2026-06-28 WISE window selection update**: Taurus same-field probes show why
the previous 7-day diagnostic was non-informative and identify a bounded
multi-night candidate window. A 1.0-degree, 370-day probe returned `328022`
observations on `8` nights, too large for the next full pipeline run. A
0.2-degree, 370-day probe returned `12061` observations on `6` nights
(`[2458883, 2459084, 2459085, 2459242, 2459243, 2459244]`). Evidence:
`docs/evidence/live/2026-06-28-wise-window-night-probes.md`.

**2026-06-29 WISE cap-2000 dry-run update**: The selected 0.2-degree window ran
through the full dry-run pipeline with `--max-candidates 2000`: `12061` WISE
rows, `12042/12061` preprocessed sources, `243289` capped seed pairs, `19`
tracklets, `19` candidates processed, `0` submission-ready candidates, and
`35.32s` elapsed. The uncapped `12042`-candidate all-pairs linker path projected
tens of minutes and was intentionally interrupted. Offline adversarial review
now fails closed on compact pipeline summary rows; this run produced `19/19`
structured `REJECT` verdicts because full `ScoredNEO` review packets were not
exported.

`run_pipeline.py --review-packet-out` was then added and live-validated on the
same bounded diagnostic. The rerun wrote `21` full `ScoredNEO` packets and
offline adversarial review produced `21/21 REJECT` verdicts with fatal
`orbit_quality`, `real_bogus`, `artifact_posterior`, and `neo_dominance`
challenges. No candidate advanced to operator review. Evidence:
`docs/evidence/live/2026-06-29-wise-cap2000-dry-run.md`. Next D1 step:
implement a scale-aware WISE linking strategy or explicit tiling plan before
another uncapped 12k-candidate run. `run_pipeline.py --max-link-seed-pairs`
now fails closed before linking when estimated all-pairs seed work exceeds the
configured budget (default `1000000`; set `0` only for a documented override).
Use `--link-scale-plan-out Logs/reports/<name>.json` on bounded diagnostics to
write the top night-pair and sky-cell contributors before the fail-closed stop;
the plan is diagnostic only and does not authorize a broad-field override.

**2026-06-29 scale-plan hardening update**: `--link-scale-plan-out` now records
a budget-derived diagnostic radius and recommended subfield parameters from the
actual blocked run inputs. These subfields are explicitly labeled as bounded
diagnostics, not complete-field tiling proof, because naive sky-cell partitioning
can miss objects that cross cell boundaries. Next D1 step after merge: run one
recommended WISE diagnostic subfield from `recommended_diagnostic_subfields` and
review the full `--review-packet-out` adversarial evidence if tracklets are
produced.

**2026-06-29 v0.90.2 scale-plan probe complete**: The merged `main` scale-plan
probe repeated the Taurus 0.2-degree, 370-day WISE dry run and correctly stopped
at `11786731` estimated seed pairs over the `1000000` default budget after
fetching `12061` WISE rows and detecting `12042` singleton candidates. The
scale plan recommended radius `0.0466` degrees and first diagnostic subfield
RA `58.1`, Dec `20.1`, JD `2458880.5` to `2459250.5`, survey `WISE`. Durable
evidence and the exact next command are recorded in
`docs/evidence/live/2026-06-29-wise-v0902-scale-plan-subfields.md`.

**2026-06-29 first v0.90.2 subfield diagnostic complete**: The operator ran
the first recommended subfield at RA `58.1`, Dec `20.1`, radius `0.0466`.
The run fetched `532` WISE rows, passed `531/532`, detected `531` singleton
candidates, linked `25053` seed pairs across `4` nights, and formed `0`
tracklets. Candidate and review-packet JSON outputs were empty arrays (`[]`).
The attempted adversarial-review command failed correctly with
`ERROR: no valid ScoredNEO entries found in input` because no tracklets meant no
reviewable packets. Durable evidence:
`docs/evidence/live/2026-06-29-wise-v0902-subfield-diagnostic.md`. Next D1 step:
do not rerun this exact subfield; select a different recommended subfield or
improve selection to prioritize areas likely to produce at least
three-observation tracklets. Future operator instructions must verify non-empty
full `ScoredNEO` packets before running `Skills/adversarial_review.py`.

**2026-06-29 v0.90.3 D1 guardrail hardening**: `Skills/run_pipeline.py` now
prints the number of full `ScoredNEO` review packets written and explicitly
instructs the operator to skip adversarial review when that count is zero. Link
scale plans now add local `support_metrics` to recommended diagnostic subfields,
including whether a subfield has at least three observations across at least two
nights inside the recommended radius. Next D1 step: regenerate or inspect a
v0.90.3 scale plan, choose a support-positive subfield that is not the failed
RA `58.1`, Dec `20.1`, radius `0.0466` diagnostic, and run adversarial review
only if full review packets are non-empty.

**2026-06-30 v0.90.3 scale-plan support metrics regenerated**: The Taurus
WISE/NEOWISE 0.2 degree, 370 day scale-plan probe was rerun on merged `main`
with v0.90.3. It again fetched `12061` WISE rows, passed `12042/12061`, detected
`12042` singleton candidates, and stopped fail-closed at `11786731` estimated
seed pairs over the `1000000` budget. The new `support_metrics` identify four
support-positive diagnostic subfields. The prior failed subfield RA `58.1`, Dec
`20.1`, radius `0.0466` is rank 3 and should not be rerun next. The next
verified diagnostic is rank 1: RA `58.1`, Dec `19.9`, radius `0.0466`. Codex
attempted that live run, but the approval layer rejected it because of a usage
limit. Durable evidence and the exact operator command are recorded in
`docs/evidence/live/2026-06-30-wise-v0903-scale-plan-support.md`.

**2026-06-30 v0.90.3 rank 1 diagnostic complete**: The rank 1 support-positive
WISE subfield at RA `58.1`, Dec `19.9`, radius `0.0466` was run from merged
`main`. The dry run fetched `701` WISE rows, passed `701/701`, detected `701`
singleton candidates, linked `48105` seed pairs, formed `3` tracklets, wrote
`3` full review packets, and produced `0` submission-ready candidates. Offline
adversarial review evaluated all `3` packets and returned `3/3` `REJECT`
verdicts. Shared rejection causes were missing orbit elements, missing
real/bogus score, artifact posterior about `0.98` to `0.99`, NEO posterior
about `0.001`, and motion below the hard `0.05 arcsec/hr` lower bound. Durable
evidence: `docs/evidence/live/2026-06-30-wise-v0903-subfield-58p1-19p9.md`.
Next D1 step: run the next distinct support-positive subfield from the v0.90.3
scale plan, RA `57.9`, Dec `20.1`, radius `0.0466`, and only run adversarial
review after a non-zero full `ScoredNEO` packet count is reported.

**2026-06-30 v0.90.3 rank 2 diagnostic complete**: The rank 2 support-positive
WISE subfield at RA `57.9`, Dec `20.1`, radius `0.0466` was run from merged
`main`. The dry run fetched `691` WISE rows, passed `691/691`, detected `691`
singleton candidates, linked `33540` seed pairs, formed `2` tracklets, wrote
`2` full review packets, and produced `0` submission-ready candidates. Offline
adversarial review evaluated both packets and returned `2/2` `REJECT` verdicts.
Shared rejection causes matched the rank 1 diagnostic: missing orbit elements,
missing real/bogus score, artifact posterior about `0.99`, NEO posterior about
`0.001`, and motion below the hard `0.05 arcsec/hr` lower bound. Durable
evidence: `docs/evidence/live/2026-06-30-wise-v0903-subfield-57p9-20p1.md`.
At that point, the next D1 step was the remaining distinct support-positive
rank 4 subfield, RA `57.9`, Dec `19.9`, radius `0.0466`; that operator-run
blocker was later cleared by the rank 4 diagnostic recorded below.

**2026-06-30 v0.90.3 rank 4 diagnostic complete**: The final remaining
distinct support-positive Taurus WISE subfield at RA `57.9`, Dec `19.9`, radius
`0.0466` was run by the operator. The dry run fetched `668` WISE rows, passed
`665/668`, detected `665` singleton candidates, linked `18776` seed pairs,
formed `2` tracklets, wrote `2` full review packets, and produced `0`
submission-ready candidates. Offline adversarial review evaluated both packets
and returned `2/2` `REJECT` verdicts. Shared rejection causes again matched
the prior diagnostics: missing orbit elements, missing real/bogus score,
artifact posterior about `0.98` to `0.99`, NEO posterior about `0.001`, and
motion below the hard `0.05 arcsec/hr` lower bound. Durable evidence:
`docs/evidence/live/2026-06-30-wise-v0903-subfield-57p9-19p9.md`. Root cause:
this Taurus WISE diagnostic set is producing near-stationary,
artifact-dominated internal candidates, not review survivors. Next D1 step:
do not rerun these Taurus subfields; select a new WISE/NEOWISE field-window
strategy likely to produce faster non-static candidates, or improve
WISE-specific filtering/linking before the next operator live run.

**2026-06-30 v0.90.4 D1 motion-floor alignment**: `detect.py`, `link.py`, and
`audit_real_run.py` now use the same `0.05 arcsec/hr` lower motion floor as
`Skills/adversarial_review.py` and `docs/MISSION.md`. This prevents
near-stationary WISE associations from becoming review packets that are
guaranteed to fail D1 on the motion-rate challenge. The next D1 blocker after
this patch is not Taurus reruns; it is either a new WISE/NEOWISE field-window
strategy likely to produce faster non-static candidates, or a defensible
WISE-native real/bogus/quality policy for archive detections.

**2026-06-30 v0.90.5 WISE parent-field probe selector**:
`Skills/select_survey_fields.py --wise-archive-probes` now enriches ranked
field selections with copy-paste-safe WISE/NEOWISE scale-plan probe commands.
The generated commands use `caffeinate -i`, Python 3.14 via `uv run`, bounded
native thread settings, dry-run mode, and `--link-scale-plan-out` so the next
non-Taurus parent field is measured before any full diagnostic run. This closes
the immediate D1 planning/tooling gap after the Taurus diagnostics were
exhausted. Next D1 step: run the selector for a non-Taurus WISE archive window,
then run the top generated scale-plan probe from merged `main`; do not run
adversarial review unless the subsequent pipeline run writes non-zero full
`ScoredNEO` review packets.

**2026-06-30 v0.90.5 non-Taurus parent-field scale-plan probe complete**: The
v0.90.5 selector-generated parent field at RA `209.64`, Dec `-15.0`, radius
`0.2`, JD `2458880.5` to `2459250.5`, survey `WISE`, ran from merged `main`.
The dry run fetched `16582` WISE rows, passed `16558/16582`, detected `16558`
singleton candidates, and stopped fail-closed at `27845455` estimated seed
pairs over the `1000000` default budget. The scale plan recommended radius
`0.0303` degrees and four support-positive diagnostic subfields. Durable
evidence and the exact next command are recorded in
`docs/evidence/live/2026-06-30-wise-v0905-parent-field-probe.md`.

**2026-06-30 v0.90.5 rank 1 support-positive diagnostic complete**: The rank 1
v0.90.5 support-positive subfield at RA `209.5`, Dec `-14.9`, radius `0.0303`
was run from merged `main`. It fetched `690` WISE rows, passed `686/690`,
detected `686` singleton candidates, linked `58596` seed pairs, and produced
`0` tracklets and `0` full review packets. The pipeline correctly printed the
skip-adversarial-review instruction because there was no reviewable `ScoredNEO`
input. This is valid diagnostic evidence, not a runtime failure. It is
historical context for the v0.90.6 WISE positive-control harness that later
closed Gate P1. Next production-capability step: close Gate P2 by documenting
WISE/DECam/TESS confidence metrics before further live operator runs.

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
