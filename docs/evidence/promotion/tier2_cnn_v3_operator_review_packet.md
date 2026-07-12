# tier2_cnn_v3 Promotion — Operator Review Packet

**Date**: 2026-07-11 (updated 2026-07-12)
**Prepared by**: automated session (Claude Code)
**Operator review required**: Jerome W. Lindsey III
**Scope**: Internal model promotion only (A7 gate). Does not authorize MPC
submission, NEOCP escalation, NASA PDCO notification, or any impact-probability
claim — those remain governed separately by `docs/MPC_SUBMISSION_POLICY.md`
and the Alert Protocol.

---

## 0. Read this first: a major finding from 2026-07-12, not in the original 8/8 table

Closing the remaining evidence-quality gaps (per your "close all gaps"
direction) surfaced something more consequential than an evidence-quality
fix. A new adversarial test — synthetic sub-pixel-spike artifacts,
designed to pass `detect()`/`link()` on brightness alone and isolate
`classify()`'s shape discrimination — found:

| Model | False-discovery rate on this test |
|---|---|
| `benchmark_cnn_v1` | 15.5% (31/200) |
| **`tier2_cnn_v3`** | **100% (200/200) — zero discrimination** |

Full writeup, caveats, and why this is **not** mechanically wired into the
pass/fail gate below (the existing 5% threshold was calibrated against a
different, easier test — changing that without your sign-off would be an
unauthorized scientific-threshold change):
`docs/evidence/a7/2026-07-12-cnn-adversarial-false-discovery.md`. Read
that file before the attestation checklist in §7 — this is the one piece
of evidence most likely to change your decision, and it is real, not
speculative: measured directly from both models' actual weights.

---

## 1. What is being promoted, and why

`tier2_cnn_v3` is a retrained Tier 2 CNN (real/bogus image classifier, one of
three ML tiers in the pipeline). It is a new candidate, not a replacement —
the frozen `benchmark_cnn_v1` stays as the historical baseline per the A3
freeze policy.

**Why a new candidate was needed**: `benchmark_cnn_v1`'s training data
(`data/ztf_labeled_alerts.json`, 10,000 alerts) never captured per-alert
RA/Dec/JD/night metadata, so it structurally cannot produce a real
grouped-split leakage report (A4) — there was nothing to group by. This
session downloaded a new batch with that provenance captured
(`data/ztf_labeled_alerts_v3.json`, 18 real nights, 90,000 alerts) and
retrained on it.

Architecture is unchanged from `benchmark_cnn_v1` (same `_build_cnn_model()`
three-branch CNN in `src/classify.py`) — only the training data and the
addition of a real device-selection fix differ. One real PyTorch MPS bug
(`AdaptiveAvgPool2d` on non-divisible input sizes) was found and fixed along
the way; see `docs/evidence/a7/2026-07-10-seventh-attempt-mps-adaptive-pool-bug-and-fix.md`.

## 2. Training result

| Metric | Value |
|---|---|
| Epochs | 20 (all completed, no errors) |
| Device | `mps` (confirmed via console output, not CPU fallback) |
| Best epoch | 19 |
| Best `val_loss` | 0.1155 |
| Best `val_acc` | 0.965 |
| Training data | 90,000 real ZTF alerts, 18 real nights (2026-06-22 to 2026-07-09), 73,560 distinct real objects |
| Wall time | 17m53s (training + full calibration run, combined) |

## 3. A7 promotion evidence — all 8 checks, real values

**Read this table with the "Reflects this model?" column, not just the pass column.**
As of 2026-07-12, injection-recovery and canonical-eval are both genuinely
model-specific (closed, see §3a). `false_discovery_report`'s gate itself
still cites shared Gate Z4 evidence deliberately (see §3a and §0) — real,
model-specific false-discovery evidence now exists but is **not**
mechanically wired into the pass/fail gate, because doing so would
silently change what the existing 5% threshold means without your
sign-off.

| Check | Result | Reflects this model? | Real value |
|---|---|---|---|
| `dataset_manifest` | ✅ pass | Yes — model-specific | `data_selection/dataset_manifests/ztf_labeled_alerts_tier2_cnn_v3.json`, checksum-verified |
| `grouped_split_report` | ✅ pass | Yes — model-specific (validates the training data, not classification behavior) | `object_id` purity: 0 leaks (hard-gated). `night_key`/`sky_cell` monitored (not gated) at 100%/91.3% overlap — see §4 below, this is the one item that needs your judgment, not just a pass/fail read |
| `canonical_eval_report` | ✅ pass | **Yes, as of 2026-07-12 — real CNN inference** (see §3a) | `docs/evidence/promotion/tier2_cnn_v3_canonical_eval.json`: the 4 original pipeline-level cases (unchanged) plus a new 5th case citing this model's real injection-recovery evidence. 5/5 cases, 21/21 checks pass |
| `injection_recovery_report` | ✅ pass | **Yes, as of 2026-07-12 — real CNN inference** (see §3a) | `docs/evidence/promotion/tier2_cnn_v3_real_cnn_injection_recovery.json`: real triplet-cutout synthesis + this model's actual weights, n=200, seed=42. 14/200 scored; posteriors diverge from `benchmark_cnn_v1` on 8/14 (e.g. stellar_artifact 0.771 vs 0.438) — genuine model-specific disagreement, not noise |
| `calibration_report` | ✅ pass | **Yes.** Real inference from this model's actual weights on 18,000 real held-out cutouts | See table below — real, new KPIs for this specific model |
| `false_discovery_report` | ✅ pass (gate unchanged) | **Gate itself: No — still Gate Z4's logistic-regression baseline.** But see §0 above and `docs/evidence/a7/2026-07-12-cnn-adversarial-false-discovery.md`: real, model-specific adversarial evidence now exists as a *separate* artifact and shows a major difference (`tier2_cnn_v3` 100% vs `benchmark_cnn_v1` 15.5% false-discovery on a synthetic sub-pixel-artifact test) — deliberately not substituted into this gate; read §0 before treating this row's "pass" as the whole story | `false_discovery_rate: 0.0` (shared Gate Z4 evidence, 0/200 false positives, real archived data) |
| `pretrained_audit` | ✅ pass | N/A by design — a true/false compliance statement (no pretrained model is used by either candidate), not a performance measurement, so sharing it doesn't weaken it | Shared project evidence (no third-party pretrained model used) |
| `benchmark_model_card` | ✅ pass | Architecture description only, legitimately shared since the architecture is verified unchanged | `benchmarks/benchmark_cnn_v1/MODEL_CARD.md` (architecture reference, shared since architecture is unchanged) |

### 3a. What "shared" actually means here, and what changed 2026-07-12

Originally three checks — `canonical_eval_report`, `injection_recovery_report`,
`false_discovery_report` — were not just reused from `benchmark_cnn_v1`;
none were model-specific for *any* CNN candidate. Verified by reading the
code, not inferred from file paths. All three now have real,
model-specific evidence, but they were closed differently:

- `canonical_eval_report`: `src/canonical_eval.py` is a static regression
  checker (loads pre-existing JSON at each case's `observed_path`,
  compares fields to thresholds) — this remains true and by design. Fixed
  by *adding* a new `cnn_injection_recovery` case type (registered in
  `SUPPORTED_CASE_TYPES`) and a new per-model suite
  (`data_selection/canonical_evals/production_suite_tier2_cnn_v3_v1.json`)
  that keeps the 4 original pipeline-level cases unchanged (still real
  regression protection) and adds a 5th case citing this model's real
  injection-recovery evidence. This is a safe substitution — same
  eq/gte/lte threshold semantics as every other canonical-eval check, no
  scientific-threshold reinterpretation involved.
- `injection_recovery_report`: fixed by wiring real CNN inference into
  `Skills/injection_recovery.py` (see below) — a direct, in-kind fix.
- `false_discovery_report`: fixed differently, and deliberately **not**
  substituted into the gate — see §0 above. Real, model-specific evidence
  exists (`Skills/evaluate_cnn_false_discovery.py`, new script) but
  applying the existing 5% `max_false_discovery_rate` threshold to this
  much harder, deliberately adversarial synthetic test (versus Gate Z4's
  real-archived-data test the threshold was actually calibrated against)
  would be an unauthorized scientific-threshold reinterpretation. This is
  presented as separate, disclosed evidence for your judgment, per
  `docs/astrometrics_coding_agents_master_guide.md`'s non-negotiable rule
  10.

- `Skills/injection_recovery.py`'s `_analytic_real_bogus()` derived its
  real_bogus score from an analytic SNR formula, never invoking any CNN.
  **This one is now fixed** (operator direction, 2026-07-11): `classify.py`'s
  `_load_cnn_model()` accepts an explicit `model_path`, and
  `injection_recovery.py` gained `--cnn-model` plus real
  science/reference/difference cutout triplet synthesis (the CNN requires
  all three; the old harness only ever built `cutout_difference`). Re-run
  for both `tier2_cnn_v3` and `benchmark_cnn_v1` at n=200, seed=42 — same
  synthetic injections, same detect/link gating (unchanged, still
  analytic-proxy-based), but classify() now runs each model's real
  weights. Result: **8 of the 14 scored tracklets get genuinely different
  posteriors between the two models** — concrete, non-trivial proof this
  is exercising real, distinct model behavior, not a no-op. Commit
  `75899a3d`; real run evidence in
  `Logs/reports/injection_recovery_cnn_tier2_cnn_v3_n200*.json` and the
  `benchmark_v1` counterparts (local/gitignored); the promotion-report
  input is the durable, committed
  `docs/evidence/promotion/tier2_cnn_v3_real_cnn_injection_recovery.json`.

**What remains for your judgment, now precise:**
1. `injection_recovery_report` and `canonical_eval_report` are now
   genuinely model-specific, satisfying
   `docs/astrometrics_coding_agents_master_guide.md`'s "a model cannot be
   promoted unless it has injection-recovery curves" rule in both letter
   and intent.
2. `false_discovery_report`'s *gate* is unchanged (still Gate Z4, real
   data, 0.0%) — deliberately, per §0/§3a, to avoid an unauthorized
   threshold reinterpretation. The real, model-specific evidence that
   *does* exist (§0) is the single most important thing in this packet:
   `tier2_cnn_v3` showed zero discrimination (100%) against a synthetic
   adversarial artifact that `benchmark_cnn_v1` partially rejected
   (15.5%). This is not a checkbox item — it needs your explicit decision,
   not just an attestation.

### Calibration KPIs (the real, model-specific result — Isotonic calibration)

| KPI | Threshold | Result | Pass |
|---|---|---|---|
| Brier score | < 0.10 | 0.0192 | ✓ |
| ECE (10-bin) | < 0.05 | 0.0054 | ✓ |
| Log-loss | < 0.50 | 0.0760 | ✓ |
| ROC AUC | > 0.95 | 0.9954 | ✓ |
| CV ECE mean | < 0.05 | 0.0056 | ✓ |
| CV ECE std | ≤ 0.02 | 0.0010 | ✓ |
| Bootstrap Brier CI upper | < 0.12 | 0.0192 | ✓ |
| Bootstrap ECE CI upper | < 0.07 | 0.0056 | ✓ |

Evaluation sample: 18,000 held-out validation cutouts (real=14,256, bogus=3,744).

## 4. The one thing that needs your judgment, not just a checkbox

This session made a real policy call earlier and got your sign-off on it
conversationally, but it belongs written down here where the actual
promotion decision gets made: `src/grouped_splits.py` now treats
`object_id` as the only hard-gating leakage check. `night_key` and
`sky_cell` are computed and reported but do not block `passed`.

**Why**: real, quantified evidence (four separate attempts, two data
scales) showed that 10.4% of real ZTF objects are detected on more than
one distinct night, and this gets *worse*, not better, with more data —
so simultaneous `object_id` + `night_key` + `sky_cell` purity is not
achievable for this survey's real data via any splitter design. Full
trail: `docs/evidence/a7/2026-07-10-fourth-attempt-scale-test-confirms-structural-incompatibility.md`.

**What this means concretely**: the grouped-split report passing does
*not* mean this model was tested on a held-out night or sky region it
never saw training data from — `night_key` overlap is 100% (every night
appears in every split) and `sky_cell` overlap is 91.3%. What it does
guarantee is that no single physical object's detections leaked across
train/validation/test. If you want night- or sky-region holdout as a
harder bar before promoting future models, that's a policy change to make
now, not something the report will ever surface on its own since it no
longer gates on it.

## 5. Known limitations (carried over from T2-C, still accurate)

- **New, 2026-07-12, the most significant item on this list**: `tier2_cnn_v3` showed 100% (200/200) false-discovery on a synthetic sub-pixel-artifact adversarial test, versus 15.5% for `benchmark_cnn_v1` on the identical test. See §0 and `docs/evidence/a7/2026-07-12-cnn-adversarial-false-discovery.md`.
- Distribution shift: training data is from 2026-06-22 to 2026-07-09 (recent), unlike `benchmark_cnn_v1`'s 2019-2020 data — this is newer, not a limitation, but is a real behavioral difference between the two candidates worth knowing about.
- No external/expert ML or astronomer review has occurred (per T2-C's original citizen-science framing, unchanged).
- WISE field-sweep testing this session (see `docs/evidence/a7/` for the real classification demo) confirms the pipeline mechanics work end-to-end but continues to find zero genuine NEO candidates in WISE data — expected, matches Gate D1's history, does not affect this promotion decision.

## 6. What this promotion does NOT authorize

- MPC submission of any pipeline-detected object.
- NEOCP follow-up escalation.
- NASA PDCO notification.
- Any impact-probability claim.
- Treating `tier2_cnn_v3` as the new frozen benchmark (`benchmark_cnn_v1` stays frozen per A3).
- Expanding live search scope.

## 7. Operator Review

**Operator**: Jerome W. Lindsey III
**Review date**: _____________
**Operator attestation**:

- [ ] I have read §0 (the 2026-07-12 adversarial false-discovery finding) and `docs/evidence/a7/2026-07-12-cnn-adversarial-false-discovery.md` in full — this is the item most likely to change my decision.
- [ ] I have read the training result and the 8 evidence checks in §3.
- [ ] I understand and accept the `object_id`-only grouped-split policy in §4 (or I am rejecting/revising it — note below).
- [ ] I understand §3a: calibration, grouped-split, injection-recovery, and canonical-eval now genuinely reflect this model's own behavior. `false_discovery_report`'s automated gate deliberately still cites Gate Z4's real-data evidence (not the new adversarial test) to avoid an unauthorized threshold change — I have made my own judgment about the 100%-vs-15.5% adversarial finding independent of that gate passing (note below).
- [ ] I understand the known limitations in §5, including the new artifact-discrimination finding.
- [ ] I confirm this does not authorize external submission, live-search expansion, or benchmark replacement.
- [ ] I approve `tier2_cnn_v3` for internal production promotion — **despite, and having weighed, the artifact-discrimination finding** (or I am rejecting/deferring promotion pending further investigation — note below).

**Operator notes** (optional free text):


**Note**: `docs/evidence/promotion/tier2_cnn_v3_promotion_report.json` has
already been regenerated (2026-07-12) citing the real, model-specific
injection-recovery evidence above — `promotion_allowed: false`,
`operator_signoff_missing` is still the only blocker. **If approved**, only
`--operator-signoff-id` needs adding; re-run:

```bash
uv run --python 3.14 python Skills/build_promotion_report.py \
    --model-id tier2_cnn_v3 --model-type tier2_cnn --model-version 3.0.0 \
    --dataset-manifest data_selection/dataset_manifests/ztf_labeled_alerts_tier2_cnn_v3.json \
    --grouped-split-report Logs/reports/tier2_cnn_v3_grouped_split_report.json \
    --canonical-eval-report docs/evidence/promotion/benchmark_cnn_v1_canonical_eval.json \
    --injection-recovery-report docs/evidence/promotion/tier2_cnn_v3_real_cnn_injection_recovery.json \
    --calibration-report Logs/reports/calibration_report_v3.json \
    --false-discovery-report docs/evidence/promotion/benchmark_cnn_v1_false_discovery.json \
    --pretrained-audit docs/evidence/phase0/pretrained_model_audit.md \
    --benchmark-model-card benchmarks/benchmark_cnn_v1/MODEL_CARD.md \
    --operator-signoff-id "jlindsey-2026-07-12" \
    --out docs/evidence/promotion/tier2_cnn_v3_promotion_report.json
```
(replace the signoff-id string with whatever identifier/date you want on record)
