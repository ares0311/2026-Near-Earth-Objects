# tier2_cnn_v3 Promotion — Operator Review Packet

**Date**: 2026-07-11
**Prepared by**: automated session (Claude Code)
**Operator review required**: Jerome W. Lindsey III
**Scope**: Internal model promotion only (A7 gate). Does not authorize MPC
submission, NEOCP escalation, NASA PDCO notification, or any impact-probability
claim — those remain governed separately by `docs/MPC_SUBMISSION_POLICY.md`
and the Alert Protocol.

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

| Check | Result | Real value |
|---|---|---|
| `dataset_manifest` | ✅ pass | `data_selection/dataset_manifests/ztf_labeled_alerts_tier2_cnn_v3.json`, checksum-verified |
| `grouped_split_report` | ✅ pass | `object_id` purity: 0 leaks (hard-gated). `night_key`/`sky_cell` monitored (not gated) at 100%/91.3% overlap — see §4 below, this is the one item that needs your judgment, not just a pass/fail read |
| `canonical_eval_report` | ✅ pass | Shared A5 suite, 4/4 case types, 16/16 checks |
| `injection_recovery_report` | ✅ pass | Shared A6 image-level curves (n=200) |
| `calibration_report` | ✅ pass | See table below — real, new KPIs for this specific model |
| `false_discovery_report` | ✅ pass | `false_discovery_rate: 0.0` (shared Gate Z4 evidence, 0/200 false positives) |
| `pretrained_audit` | ✅ pass | Shared project evidence (no third-party pretrained model used) |
| `benchmark_model_card` | ✅ pass | `benchmarks/benchmark_cnn_v1/MODEL_CARD.md` (architecture reference, shared since architecture is unchanged) |

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

- [ ] I have read the training result and the 8 evidence checks above.
- [ ] I understand and accept the `object_id`-only grouped-split policy in §4 (or I am rejecting/revising it — note below).
- [ ] I understand the known limitations in §5.
- [ ] I confirm this does not authorize external submission, live-search expansion, or benchmark replacement.
- [ ] I approve `tier2_cnn_v3` for internal production promotion.

**Operator notes** (optional free text):


**If approved**, run:

```bash
uv run --python 3.14 python Skills/build_promotion_report.py \
    --model-id tier2_cnn_v3 --model-type tier2_cnn --model-version 3.0.0 \
    --dataset-manifest data_selection/dataset_manifests/ztf_labeled_alerts_tier2_cnn_v3.json \
    --grouped-split-report Logs/reports/tier2_cnn_v3_grouped_split_report.json \
    --canonical-eval-report docs/evidence/promotion/benchmark_cnn_v1_canonical_eval.json \
    --injection-recovery-report docs/evidence/promotion/benchmark_cnn_v1_injection_recovery.json \
    --calibration-report Logs/reports/calibration_report_v3.json \
    --false-discovery-report docs/evidence/promotion/benchmark_cnn_v1_false_discovery.json \
    --pretrained-audit docs/evidence/phase0/pretrained_model_audit.md \
    --benchmark-model-card benchmarks/benchmark_cnn_v1/MODEL_CARD.md \
    --operator-signoff-id "jlindsey-2026-07-11" \
    --out docs/evidence/promotion/tier2_cnn_v3_promotion_report.json
```
(replace the signoff-id string with whatever identifier/date you want on record)
