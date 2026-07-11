# A7 CNN retrain + calibration — 2026-07-10, eighth pass (REAL SUCCESS)

## Command run (operator's Mac, real MPS device, post-fix)

```bash
git pull origin main
export PYTHONPATH=src

caffeinate -i uv run --python 3.14 python Skills/train_tier2_cnn.py \
    --labels data/cutouts_v3/index.csv \
    --epochs 20 --num-workers 8 \
    --out models/tier2_cnn_v3.pt \
    --grouped-split-report Logs/reports/tier2_cnn_v3_grouped_split_report.json \
    --production-candidate

caffeinate -i uv run --python 3.14 python Skills/evaluate_calibration.py \
    --alerts data/ztf_labeled_alerts_v3.json \
    --cutouts-csv data/cutouts_v3/index.csv \
    --cnn-model models/tier2_cnn_v3.pt \
    --report-out Logs/reports/calibration_report_v3.json
```

## Result: real success, no errors, both commands completed

Total wall time: **17m53s** for both commands combined (training + full
18,000-sample calibration inference + bootstrap/CV) — confirms the
v0.90.78/79 MPS device-selection and AdaptiveAvgPool2d fixes delivered the
expected speedup versus this session's sandboxed CPU-only estimate of 3+
hours for training alone.

### Training (`Skills/train_tier2_cnn.py`)

`Device: mps` printed correctly (the v0.90.79 `AdaptiveAvgPool2d` CPU-detour
fix worked — no `RuntimeError` this time). Grouped split gate passed
(citing the real `tier2_cnn_v3_grouped_split_report.json`). 20/20 epochs
completed. Best checkpoint: epoch 19, `val_loss=0.1155`, `val_acc=0.965`.
Saved to `models/tier2_cnn_v3.pt` (7.1 MB).

### Calibration (`Skills/evaluate_calibration.py`) — Tier 2 CNN section (NEW real result)

```
Total cutouts: 90000
Val set: 18000  (real=14256  bogus=3744)

Raw CNN               Brier=0.0211  [PASS < 0.1]   ECE=0.0229  [PASS < 0.05]
+ Platt                Brier=0.8190  [FAIL < 0.1]   ECE=0.6113  [FAIL < 0.05]
+ Isotonic             Brier=0.0192  [PASS < 0.1]   ECE=0.0054  [PASS < 0.05]

Log-loss (raw)   : 0.0760  [PASS < 0.5]
ROC AUC  (raw)   : 0.9954  [PASS > 0.95]

CV ECE mean : 0.0056  [PASS < 0.05]
CV ECE std  : 0.0010  [PASS < 0.02]

Bootstrap Brier 95% CI upper : 0.0192  [PASS < 0.12]
Bootstrap ECE   95% CI upper : 0.0056  [PASS < 0.07]

T1-D gate (all 7 KPIs): PASS
  brier, ece, log_loss, roc_auc, cv_ece_mean, cv_ece_std,
  bootstrap_brier_upper, bootstrap_ece_upper : all PASS
```

(Platt calibration fails as expected/known for this model family — Isotonic
is the selected calibrator, matching the same pattern already seen for
`benchmark_cnn_v1` in the 2026-06-14 T1-D closure.)

`promotion_gate_passed : True`. JSON report written to
`Logs/reports/calibration_report_v3.json` (local-only, gitignored, on the
operator's Mac — not present in this sandboxed session; this evidence file
transcribes the real printed console output, which is the same convention
already used for the original `benchmark_cnn_v1` T1-D closure).

## Status

`calibration_report_missing`: **CLOSED (real evidence, 2026-07-10)**. This
is the first real, passing calibration report for a genuinely retrained
Tier 2 CNN (`tier2_cnn_v3`) trained on the real 18-night, 90,000-alert,
`object_id`-pure grouped-split batch. Combined with the `grouped_split_report_missing`
closure (fifth pass, same session), both real-evidence A7 blockers that
required an actual retrain are now closed. **`operator_signoff_missing`
is the sole remaining A7 blocker**, and it is inherently human-gated per
`docs/PRODUCTION_READINESS.md`'s Production Definition — no further coding
step can close it. The next coding step is regenerating
`benchmark_cnn_v1_promotion_report.json`-style promotion evidence for the
new `tier2_cnn_v3` candidate citing this session's real grouped-split and
calibration reports, once the operator confirms `Logs/reports/calibration_report_v3.json`
is on disk (it is local-only and this sandboxed session cannot read it
directly).
