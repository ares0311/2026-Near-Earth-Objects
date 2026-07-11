# A7 promotion report — 2026-07-11 (8/8 evidence checks pass)

## Command run

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
    --out docs/evidence/promotion/tier2_cnn_v3_promotion_report.json
```

## Result

All 8 evidence checks pass:

| Check | Passed | Source |
|---|---|---|
| dataset_manifest | ✅ | `data_selection/dataset_manifests/ztf_labeled_alerts_tier2_cnn_v3.json` |
| grouped_split_report | ✅ | `Logs/reports/tier2_cnn_v3_grouped_split_report.json` |
| canonical_eval_report | ✅ | shared project evidence |
| injection_recovery_report | ✅ | shared project evidence |
| calibration_report | ✅ | `Logs/reports/calibration_report_v3.json` (`promotion_gate_passed: true`, `tier_count: 2`) |
| false_discovery_report | ✅ | shared project evidence (`false_discovery_rate: 0.0`) |
| pretrained_audit | ✅ | shared project evidence |
| benchmark_model_card | ✅ | shared project evidence |

`promotion_allowed: false`, exactly one blocker: `operator_signoff_missing`.

This is the natural end state of a fail-closed promotion report with no
evidence gaps — every check this session's real work (grouped-split policy
change, real 18-night retrain, real calibration run) was designed to close
is now closed. The only remaining input is `--operator-signoff-id`, which
by design can only come from the operator (Jerome W. Lindsey III) reviewing
this report and its cited evidence directly.

## Status

`operator_signoff_missing` is the sole remaining A7 blocker, and the sole
remaining blocker in this project's entire code-and-evidence-closable
production roadmap as of this session. Everything upstream of it (A1
manifest, A3 freeze, A4 grouped split, A5 canonical evals, A6
injection-recovery, A7's dataset/split/calibration/false-discovery/audit/
model-card checks) is real and passing. No further coding step can close
this; it is a human decision, not a bug or a gap.
