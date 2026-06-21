# T2-C Evidence: Citizen-Science Architecture Evidence Packet

**Date**: 2026-06-20  
**Pipeline version**: v0.88.0  
**Prepared by**: automated session (Claude Code)  
**Operator review required**: Jerome W. Lindsey III  
**External expert review**: NOT AVAILABLE — no-submission constraint applies

---

## Purpose

This packet records the three-tier ML architecture assumptions, calibration KPI
results, known limitations, and no-submission guardrails for the NEO Detection
and Ranking Pipeline. It is the durable evidence artifact required by the T2-C
gap in `docs/PRODUCTION_READINESS.md`.

This packet does NOT constitute expert validation. External MPC submission
remains blocked until qualified astronomer or ML review is obtained or a
separate submission policy with appropriate oversight is adopted.

---

## 1. Architecture Decisions

### DECISION-001: ZTF as Primary Survey
ZTF provides the richest freely available alert stream with pre-computed
difference images, a native real/bogus score, and a well-documented Python API.
Public access via IRSA (authenticated) and the ALeRCE broker (public).

**Limitation**: ZTF covers the northern sky only. Southern-sky NEOs visible only
to ATLAS/Pan-STARRS will not appear in ZTF-only fetches.

### DECISION-002: Three-Tier ML Architecture
- **Tier 1 — XGBoost on tabular features**: Fast, interpretable. Trained on
  ZTF labeled alerts (rb/drb features) and MPC confirmed NEO/MBA catalog.
  Handles missing features by passing `None` scores as neutral (0-contribution).
- **Tier 2 — CNN on 63×63 image triplets**: Science/reference/difference
  cutouts; architecture adapted from Duev et al. 2019. Trained on 10,000
  real ZTF Avro alerts (8,588 real / 1,412 bogus).
- **Tier 3 — Transformer on tracklet sequences**: Encoder-only BERT-style
  model. Trained on a five-class pilot dataset (50 sequences per class,
  250 total) sourced from MPC observation histories and ALeRCE bogus histories.
- **Ensemble stacker**: Logistic regression meta-learner over Tier 1 + Tier 2
  outputs, isotonic-calibrated.

**Limitation**: Tier 3 was trained on a small pilot dataset (50 sequences per
class). Real-sky class distributions differ from the training mix. Performance
on rare orbital classes (IEO, comets) is unvalidated beyond pilot data.

### DECISION-003: No Autonomous Impact Claims
The pipeline never asserts an impact probability. The alert pathway requires
MOID ≤ 0.05 AU AND independent MPC confirmation before any NASA notification.
This constraint is enforced in code (`ready_for_submission()` gate) and in all
output formatting functions.

### DECISION-004: MPC-Compatible Output First
All detections are formatted in MPC 80-column and ADES PSV formats before any
downstream reporting. This ensures interoperability even if the ML layer is
later retrained.

### DECISION-005: Conservative Classification
- `None` feature scores fail all gate conditions (neutral = no evidence).
- Unknown objects default to `"candidate"`, never `"confirmed NEO"`.
- PHAs require orbit quality code ≥ 2 before flagging.
- Alert pathway gates are ordered: `internal_candidate` → `mpc_submission` →
  `neocp_followup` → `nasa_pdco_notify`.

---

## 2. Calibration KPI Results

All results from operator-run evaluations on held-out real labeled data.
Reports are gitignored local operational artifacts; KPI summaries are recorded
here for durable reference.

### Tier 1 XGBoost (Isotonic Calibration) — 2026-06-14

| KPI | Threshold | Result | Pass |
|---|---|---|---|
| Brier score | < 0.10 | 0.0000 | ✓ |
| ECE (10-bin) | < 0.05 | 0.0000 | ✓ |
| Log-loss | < 0.50 | 0.0004 | ✓ |
| ROC AUC | > 0.95 | 1.0000 | ✓ |
| CV ECE mean | < 0.05 | 0.0000 | ✓ |
| CV ECE std | ≤ 0.02 | 0.0000 | ✓ |
| Bootstrap Brier CI upper | < 0.12 | 0.0000 | ✓ |

### Tier 2 CNN (Isotonic Calibration) — 2026-06-14

| KPI | Threshold | Result | Pass |
|---|---|---|---|
| Brier score | < 0.10 | 0.0462 | ✓ |
| ECE (10-bin) | < 0.05 | 0.0132 | ✓ |
| Log-loss | < 0.50 | 0.2398 | ✓ |
| ROC AUC | > 0.95 | 0.9593 | ✓ |
| CV ECE mean | < 0.05 | 0.0212 | ✓ |
| CV ECE std | ≤ 0.02 | 0.0076 | ✓ |
| Bootstrap ECE CI upper | < 0.07 | 0.0185 | ✓ |

### Ensemble Stacker (Isotonic Calibration) — 2026-06-14

| KPI | Threshold | Result | Pass |
|---|---|---|---|
| ROC AUC | > 0.95 | 0.9809 | ✓ |
| Brier score | < 0.10 | 0.0211 | ✓ |
| ECE (10-bin) | < 0.05 | 0.0000 | ✓ |
| Log-loss | < 0.50 | 0.0761 | ✓ |
| CV ECE mean | < 0.05 | 0.0247 | ✓ |
| Bootstrap Brier CI upper | < 0.12 | 0.0330 | ✓ |
| Bootstrap ECE CI upper | < 0.07 | 0.0225 | ✓ |

Evaluation sample: 394 ZTF-origin validation examples.
`promotion_gate_passed=true` in `Logs/reports/calibration_report.json` (local).

### Tier 3 Transformer — Pilot Only

Tier 3 was evaluated on the five-class pilot held-out test set only.
val_macro_f1=0.9400, val_loss=0.2492 at best epoch 17/30.

**This is NOT a production calibration evaluation.** The pilot dataset is small
(50 sequences per class, 250 total). No separate held-out calibration run has
been performed. The T1-D gate covers Tier 1 and Tier 2 only.

---

## 3. Known Limitations

### Data limitations
- Tier 3 trained on 50 sequences per class (250 total). Real class distributions
  are highly unbalanced; the pilot mix is synthetic.
- Training data is not fully independent from the evaluation data for Tier 3
  due to the small pilot size (designation-grouped splits were used as a proxy).
- Tier 2 CNN trained on 10,000 ZTF Avro alerts from 2019–2020. Distribution
  shift from newer ZTF operations is uncharacterized.
- Known-object recovery has been validated via ATLAS forced-photometry mode:
  5/5 objects recovered (100%) in the Option A follow-up run (2026-06-20),
  passing the ≥90% T1-C gate. ZTF multi-night recovery has not been validated.

### Orbital coverage limitations
- IEO (Atira) and unusual-inclination objects are rare in training data.
- Comet candidates (low Tisserand parameter) are represented by only 50 MPC
  sequences in Tier 3 training.
- High-eccentricity and very short-arc candidates have not been separately
  evaluated.

### Pipeline coverage limitations
- The full pipeline has completed one bounded ZTF pilot (2026-06-16) and
  multiple ATLAS recovery pilots. No multi-night ZTF tracklet linking
  against a known-object manifest has been validated.
- The T1-C known-object recovery KPI (≥90%) **has been passed** as of
  2026-06-20: 5/5 ATLAS-forced objects recovered (100%) in the Option A
  follow-up run. Earlier runs: 36.36% (run 1), 75.00% (run 2).

### Scoring model limitations
- The Bayesian log-score priors (5% neo_candidate, 35% MBA) reflect broad
  survey averages and have not been tuned for any specific field.
- The `discovery_priority`, `followup_value`, and `scientific_interest` scores
  are composite heuristics, not probabilistic quantities.

---

## 4. No-Submission Guardrails

The following constraints are enforced in code and policy and cannot be
bypassed by the background automation CLI:

- `ready_for_submission()` in `alert.py` requires ALL of: MOID ≤ 0.05 AU,
  orbit quality code ≥ 2, Tier 1 real_bogus_score ≥ 0.90, and no MPC
  known-object match. This gate must pass before any MPC report is formatted.
- `format_impact_notification()` includes a mandatory guardrail statement:
  "Do NOT publicly announce any impact probability."
- The background automation config (`background/config.json`) has
  `no_external_submission_confirmed: true` enforced by the live review policy.
- `Skills/audit_real_run.py` writes `no_mpc_submission: true` and
  `no_impact_probability_claim: true` in every audit packet.
- No operator command issued by this project has performed or authorized
  external MPC submission or NASA notification.

---

## 5. Citizen-Science Framing

This pipeline operates as a citizen-science project under the following
explicit constraints:

- **No domain expert available**: Jerome W. Lindsey III is the project operator
  and reviewer. No NEO domain expert or professional astronomer is currently
  available for validation.
- **Internal promotion only**: The pipeline may be promoted to internal
  production use (running scheduled background searches, generating candidate
  lists, auditing recovery) once T2-C is closed. T1-C is now closed (2026-06-20).
- **External submission blocked**: MPC submission, NEOCP follow-up escalation,
  NASA PDCO notification, and all public hazard claims remain blocked until
  qualified external review or a separate externally supervised submission
  policy is adopted.
- **This packet does not authorize external submission.** It records the
  architecture and limitations for operator awareness only.

---

## 6. Operator Review

**Operator**: Jerome W. Lindsey III  
**Review date**: (to be completed by operator)  
**Operator attestation**:

- [ ] I have read the architecture decisions and calibration KPIs above.
- [ ] I understand the known limitations section.
- [ ] I confirm that no external submission has been authorized.
- [ ] I confirm that this packet does not replace expert validation.
- [ ] I accept the citizen-science framing as accurate.

**Operator notes** (optional free text):

---

## 7. What This Packet Does NOT Authorize

- MPC submission of any pipeline-detected object.
- NEOCP follow-up escalation.
- NASA PDCO notification.
- Public announcement of any hazard probability.
- Claim that the pipeline has detected a confirmed NEO.
- Claim that this packet constitutes expert validation of the ML architecture.
