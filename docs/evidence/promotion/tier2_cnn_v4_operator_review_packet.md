# tier2_cnn_v4 Promotion — Operator Review Packet

**Date**: 2026-07-12
**Prepared for**: Jerome W. Lindsey III
**Decision status**: Pending operator review
**Scope**: Internal model promotion only. This packet does not authorize MPC
submission, NEOCP escalation, NASA PDCO notification, live-search expansion,
or any impact-probability claim.

## 1. Decision summary

`tier2_cnn_v4` is the hard-negative retune requested after the operator
rejected `tier2_cnn_v3`. The retune clearly closes the measured adversarial
artifact failure and preserves strong calibration on real held-out ZTF data.

The evidence also exposes a real tradeoff that must be part of the decision:
all 14 scored synthetic moving-source injections are classified with
`stellar_artifact` as the final ensemble argmax. This matches the frozen
`benchmark_cnn_v1` on the same harness but is more conservative than v3,
which classified 8 of those 14 as `neo_candidate` and then failed the
adversarial artifact test catastrophically.

No automatic recommendation is substituted for operator judgment. The
machine-readable report remains fail-closed with exactly one blocker:
`operator_signoff_missing`.

## 2. What changed from tier2_cnn_v3

The CNN architecture and real training source are unchanged. V4 adds 3,000
deterministic synthetic `stellar_artifact` hard negatives to the real training
split only:

- Real training rows: 58,500.
- Synthetic hard negatives: 3,000.
- Total training rows: 61,500.
- Real-only validation rows: 18,000.
- Held-out, unused test rows: 13,500.
- Synthetic sigma range: 0.05–0.35 px, seed 0.
- Device: Apple MPS.
- Epochs: 20; best checkpoint at epoch 20.
- Best validation loss: 0.1098.
- Validation accuracy at the saved checkpoint: 0.961.
- Model SHA-256:
  `515d92ba776f9ca2a70b26f60a3ca7886d27af5bd10b0d9027890ca39a372a7a`.

Training provenance is split across two validated manifests:

1. `ztf_labeled_alerts_tier2_cnn_v3.json` for the 90,000 real ZTF alert
   source and grouped train/validation/test split.
2. `tier2_cnn_v4_synthetic_hard_negatives_v1.json` for the deterministic
   in-memory augmentation and its exact generator parameters.

## 3. Promotion evidence

All nine evidence artifacts accepted by the mechanical A7 builder pass. The
second dataset manifest makes this nine artifacts across the existing eight
evidence categories.

| Evidence | Result | Material fact |
|---|---:|---|
| Real training manifest | Pass | 90,000 real ZTF alerts; checksum and 18-night provenance recorded |
| Synthetic training manifest | Pass | 3,000 deterministic hard negatives; synthetic-only and non-persisted caveats explicit |
| Grouped split | Pass | Zero `object_id` leakage; night and sky overlap remain monitored limitations |
| Canonical eval | Pass | 5/5 cases, 25/25 checks, including exact v4 checkpoint SHA and posterior behavior |
| Model-specific injection recovery | Pass | n=200; 16 detected, 14 linked/scored; all required curve dimensions present |
| Calibration | Pass | All quantitative KPIs pass on 18,000 real held-out cutouts |
| False-discovery gate | Pass | Existing Gate Z4 real archived-negative evidence remains 0/200; threshold semantics unchanged |
| Pretrained-model audit | Pass | No third-party pretrained weights used |
| Benchmark model card | Pass | Architecture remains comparable with frozen `benchmark_cnn_v1` |

Machine-readable result:

```text
promotion_allowed=false
promotion_blockers=operator_signoff_missing
```

## 4. Adversarial artifact acceptance test

The same n=200, seed=42 sub-pixel artifact test that rejected v3 was run
against all three checkpoints:

| Model | Full-ensemble false discovery | Tier 2-only false discovery |
|---|---:|---:|
| `benchmark_cnn_v1` | 31/200 (15.5%) | 33/200 (16.5%) |
| `tier2_cnn_v3` — rejected | 200/200 (100%) | 200/200 (100%) |
| `tier2_cnn_v4` | **0/200 (0%)** | **0/200 (0%)** |

All 200 artifacts passed detection and linking, so the v4 result measures
classification behavior rather than an upstream filter.

Important limitation: the v4 hard-negative sigma range deliberately brackets
this test's 0.15 px artifact. This demonstrates closure of the targeted
failure mode, but it is not independent evidence of robustness to every
real-world artifact family.

## 5. Real-data calibration

The v4 checkpoint was evaluated on 18,000 held-out real cutouts
(14,256 real, 3,744 bogus). Isotonic calibration was selected.

| KPI | Threshold | V4 result | Status |
|---|---:|---:|---:|
| Brier score | < 0.10 | 0.01917 | Pass |
| ECE | < 0.05 | 0.00482 | Pass |
| Raw log-loss | < 0.50 | 0.09090 | Pass |
| Raw ROC AUC | > 0.95 | 0.99499 | Pass |
| CV ECE mean | < 0.05 | 0.00497 | Pass |
| CV ECE std | ≤ 0.02 | 0.00120 | Pass |
| Bootstrap Brier 95% CI upper | < 0.12 | 0.01909 | Pass |
| Bootstrap ECE 95% CI upper | < 0.07 | 0.00477 | Pass |

These results show that the hard-negative supplement did not materially
degrade broad real-data discrimination or calibration.

## 6. Moving-source injection behavior — read before deciding

The model-specific n=200 image-level injection run used v4's exact checkpoint,
verified by SHA-256 in the durable evidence. Sixteen synthetic moving sources
passed detection, fourteen linked and were scored, and all required recovery
curve dimensions were populated.

The corrected harness now retains classification posteriors rather than only
model-invariant stage booleans. Its result is:

| Final ensemble argmax | Count among 14 scored injections |
|---|---:|
| `stellar_artifact` | 14 |
| `neo_candidate` | 0 |
| all other classes | 0 |

Comparison on the identical 14 scored injections:

- V4 is bit-for-bit identical to `benchmark_cnn_v1` at final-posterior level.
- V4 differs from v3 on 8/14 cases.
- Example changed case: `stellar_artifact` 0.438 → 0.771 and
  `neo_candidate` 0.555 → 0.222.

Interpretation: v4 restores the benchmark's conservative behavior on this
synthetic moving-source family while eliminating the benchmark's residual
sub-pixel-artifact false discoveries. This may be desirable conservatism, but
it also means the current injection harness does not demonstrate improved
NEO-like classification sensitivity over the benchmark.

No new threshold is introduced here. Deciding whether this tradeoff is
acceptable for internal promotion is an operator/model-policy decision.

## 7. Grouped-split limitation

The split hard-gates physical `object_id` purity: no object appears across
train, validation, and test. It does not provide held-out-night or held-out-sky
generalization:

- `night_key` overlap: 100%.
- `sky_cell` overlap: 91.3%.

This is the existing operator-approved policy after real data showed that
10.4% of physical objects span multiple nights and ZTF revisits the same sky
cells. The overlap is disclosed and monitored; it is not silently described
as a night/sky holdout.

## 8. What approval would and would not mean

Approval would authorize use of `tier2_cnn_v4` as the internally promoted
Tier 2 candidate under the A7 model-governance process.

Approval would not:

- Replace or alter the frozen `benchmark_cnn_v1` historical benchmark.
- Make the CNN the scientific thesis or final candidate decision-maker.
- Authorize MPC submission, NEOCP escalation, or NASA/PDCO contact.
- Authorize an impact-probability statement.
- Expand live-search scope.
- Convert internally ranked objects into confirmed NEOs.

## 9. Operator decision

**Operator**: Jerome W. Lindsey III

**Review date**: _pending_
**Decision**: _pending_

Attestation:

- [ ] I reviewed the 0/200 adversarial artifact result and its same-family limitation.
- [ ] I reviewed the real-data calibration KPIs.
- [ ] I reviewed the 14/14 `stellar_artifact` moving-source injection result.
- [ ] I understand the `object_id`-only grouped-split hard gate and monitored night/sky overlap.
- [ ] I understand approval is internal model promotion only and authorizes no external submission or alert.
- [ ] I approve `tier2_cnn_v4` for internal production promotion.

If approved, record an operator-selected signoff identifier and regenerate the
report with the same inputs plus:

```text
--operator-signoff-id "<operator-selected-id>"
```

Until that explicit decision is recorded, `benchmark_cnn_v1` remains the
active frozen/production reference and `tier2_cnn_v4` remains unpromoted.
