# tier2_cnn_v4 — Real Retrain, Acceptance Test, and Calibration (all PASS)

Date: 2026-07-12
Follows: `docs/evidence/a7/2026-07-12-hard-negative-augmentation-implemented.md`
(code) and `docs/evidence/a7/2026-07-12-model-rejected-retune-required.md`
(the "Reject - Retune" decision that motivated this retrain).

## What was run

Operator ran, on their Mac (real MPS hardware), the exact command block
handed off in the prior sync, in one terminal tab, sequentially:

```bash
caffeinate -i uv run --python 3.14 python Skills/train_tier2_cnn.py \
    --labels data/cutouts_v3/index.csv --epochs 20 --num-workers 8 \
    --n-hard-negatives 3000 --out models/tier2_cnn_v4.pt \
    --grouped-split-report Logs/reports/tier2_cnn_v3_grouped_split_report.json \
    --production-candidate

caffeinate -i uv run --python 3.14 python Skills/evaluate_cnn_false_discovery.py \
    --cnn-model models/tier2_cnn_v4.pt --n-artifacts 200 --seed 42 \
    --json Logs/reports/cnn_false_discovery_tier2_cnn_v4.json

caffeinate -i uv run --python 3.14 python Skills/evaluate_calibration.py \
    --alerts data/ztf_labeled_alerts_v3.json --cutouts-csv data/cutouts_v3/index.csv \
    --cnn-model models/tier2_cnn_v4.pt --report-out Logs/reports/calibration_report_v4.json
```

Total wall time: 19m01s for all three steps.

## 1. Training

`Device: mps` (real GPU, not CPU fallback). Grouped split gate passed
(reused `tier2_cnn_v3_grouped_split_report.json` — valid because hard
negatives are added only inside `train()`'s in-memory training set, never
touching the split CSV).

- Real train: 58,500 rows. Synthetic hard negatives added: +3,000
  (`stellar_artifact`, sigma range 0.05–0.35px, seed=0). Total training set:
  61,500.
- Validation: 18,000 (real-data-only, confirmed — hard negatives are never
  added to val/test).
- Train label counts (post-augmentation): `neo_candidate` 46,169,
  `stellar_artifact` 15,331 (= 12,331 real + 3,000 synthetic — consistent
  with the 3,000 requested).
- Class weights recomputed to reflect the combined composition:
  `neo_candidate` 0.666, `stellar_artifact` 2.006.
- 20 epochs, monotonic improvement with the usual noise; best checkpoint at
  epoch 20 (`val_loss=0.1098`, `val_acc=0.961`), saved to
  `models/tier2_cnn_v4.pt`.

## 2. Acceptance test — `evaluate_cnn_false_discovery.py` (n=200, seed=42)

This is the test that produced the disqualifying evidence against
`tier2_cnn_v3` (100% false-discovery). Same script, same seed, same n,
against the new model:

| Model | Full ensemble false-discovery | Tier 2 CNN alone |
|---|---|---|
| `benchmark_cnn_v1` | 15.5% (31/200) | 16.5% (33/200) |
| `tier2_cnn_v3` (REJECTED) | 100% (200/200) | 100% (200/200) |
| **`tier2_cnn_v4`** | **0.0% (0/200)** | **0.0% (0/200)** |

All 200/200 synthetic artifacts were still detected and linked (the
geometry is designed to pass `detect()`/`link()` regardless of image
content — unchanged from before), so this is purely a `classify()` shape-
discrimination result, confirmed both in the full ensemble and in the
isolated Tier 2 CNN output (rules out Tier 1 tabular features carrying the
result).

**Honest caveat, not overclaimed**: the hard-negative augmentation's sigma
range (0.05–0.35px) was deliberately chosen to bracket this exact test's
artifact sigma (0.15px), because the whole point of the retune was to
directly attack this demonstrated failure mode (per the original retune
plan). A 0.0% result on the same adversarial-test family the model was
trained against is the expected, intended outcome of that design — it is
real, verified evidence that the specific failure mode is closed, not
independent proof of general real-world artifact robustness beyond this
test family. The calibration results below (run on real ZTF data the model
was never trained to specifically defeat) are the independent check on
overall production behavior, and those also passed cleanly.

## 3. Calibration — `evaluate_calibration.py` (T1-D gate)

Real 90,000-alert batch, same data as `tier2_cnn_v3`'s calibration run.
Tier 1 XGBoost unaffected (same model, unchanged): all 7 KPIs PASS
(Isotonic Brier=0.0000, ECE=0.0000, ROC AUC=1.0000).

**Tier 2 CNN (`tier2_cnn_v4`)** — all 7 KPIs PASS, `promotion_gate_passed: true`:

| KPI | tier2_cnn_v3 (2026-07-10) | tier2_cnn_v4 (2026-07-12) | Threshold |
|---|---|---|---|
| Brier (Isotonic) | 0.0192 | 0.0192 | < 0.1 |
| ECE (Isotonic) | 0.0054 | 0.0048 | < 0.05 |
| Log-loss (raw) | 0.0760 | 0.0909 | < 0.5 |
| ROC AUC (raw) | 0.9954 | 0.9950 | > 0.95 |
| CV ECE mean | 0.0056 | 0.0050 | < 0.05 |
| CV ECE std | 0.0010 | 0.0012 | ≤ 0.02 |
| Bootstrap Brier CI upper | (not in prior sync) | 0.0191 | < 0.12 |
| Bootstrap ECE CI upper | (not in prior sync) | 0.0048 | < 0.07 |

**The hard-negative augmentation did not degrade real-data calibration** —
`tier2_cnn_v4`'s numbers are essentially identical to or slightly better
than `tier2_cnn_v3`'s, well within all thresholds. This addresses the
natural concern that adding 3,000 synthetic examples might distort
real-world probability calibration; it did not.

## Bottom line

The retune succeeded on both measures that matter: it closed the specific
adversarial gap that got `tier2_cnn_v3` rejected (100% → 0.0%
false-discovery), and it did so without harming real-data calibration
performance (all 7 T1-D KPIs pass, comparable to v3).

`Logs/reports/cnn_false_discovery_tier2_cnn_v4.json` and
`Logs/reports/calibration_report_v4.json` are local-only on the operator's
Mac (same convention as prior local calibration reports), not committed
here — this file is the durable evidence record.

## Not yet done

`tier2_cnn_v4` does not yet have its own promotion report or operator
review packet (the `tier2_cnn_v3` promotion framework — dataset manifest,
grouped-split report reuse, canonical-eval suite, real CNN
injection-recovery, false-discovery evidence, `build_promotion_report.py`
— has not been re-run for this new candidate). `benchmark_cnn_v1` remains
the production/frozen model; no promotion, no benchmark replacement, no
live-search expansion follows from this evidence alone. Operator review
and explicit signoff are still required before any promotion decision on
`tier2_cnn_v4`, per this project's two-stage review discipline.
