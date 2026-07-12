# Real CNN Inference Wired Into Injection-Recovery (A7 gap closure)

Date: 2026-07-12
Scope: A7 promotion evidence for `tier2_cnn_v3`; also re-run for
`benchmark_cnn_v1` per explicit operator direction ("if we need to roll
back and do this for the last CNN then let's do so").

## What was found (2026-07-11, during operator review of the tier2_cnn_v3 packet)

Operator asked whether `tier2_cnn_v3` passed all tests the System
Directives require. Investigation found `injection_recovery_report`,
`canonical_eval_report`, and `false_discovery_report` — 3 of the
promotion report's 8 evidence checks — had never exercised any CNN
candidate's live inference, for `tier2_cnn_v3` or `benchmark_cnn_v1`:

- `src/canonical_eval.py` is a static regression checker against
  pre-existing, CNN-independent artifacts. No model is loaded.
- `Skills/injection_recovery.py`'s `_analytic_real_bogus()` derived
  real_bogus from an analytic SNR formula. `classify.py`'s
  `_tier2_predict()` requires a full science/reference/difference cutout
  triplet to run at all; the harness only ever synthesized
  `cutout_difference`, so `_tier2_predict` silently returned `None` on
  every call.
- `false_discovery_report` is derived from Gate Z4's logistic-regression
  ranking baseline, not any CNN.

`docs/astrometrics_coding_agents_master_guide.md`'s own validation rule —
*"a model cannot be promoted unless **it** has injection-recovery
curves"* — reads as requiring model-specific curves. What existed
satisfied the promotion-report checklist but not that reading of the
rule's intent.

Operator direction (2026-07-11/12): fix injection-recovery to use real
CNN inference, and re-run for both `tier2_cnn_v3` and `benchmark_cnn_v1`,
not just the new candidate.

## What was built (commit `75899a3d`)

- `src/classify.py`: `_load_cnn_model()` gained an optional `model_path`
  parameter (default unchanged: `models/tier2_cnn.pt`). `classify()`
  already accepted a `cnn_model` parameter — no other change needed there.
- `Skills/injection_recovery.py`:
  - New `_synthesize_cutout_triplet()` builds science/reference/difference
    cutouts where `science - reference == difference` by construction.
    The difference image and real_bogus proxy are byte-identical to the
    pre-existing `_synthesize_difference_cutout()`, so committed baselines
    (e.g. `data/injection_recovery_image_level_n200.json`) stay
    reproducible and unaffected.
  - New `--cnn-model PATH` flag (requires `--image-level`): loads the
    specified checkpoint once, synthesizes full triplets, passes the
    loaded model into every `classify()` call. Fails closed (raises) if
    the model can't be loaded, rather than silently falling back to
    analytic-only scoring.
  - Checkpoint key now includes `cnn_model_path`, applying the exact
    lesson from the `ztf_alert_archive_ingest.py` checkpoint bug (commit
    `a0fb56e0`, found the same day) proactively: two runs scoring
    different models can never share a checkpoint.
- 11 new regression tests (2 in `test_classify.py`, 9 in
  `test_injection_recovery.py`). Full suite 1872 passed / 2 deselected
  (was 1861), ruff/mypy clean.

## Real run results (n=200, seed=42, both models)

| Model | Detection | Link | Score | Hazard flags |
|---|---|---|---|---|
| `benchmark_cnn_v1` (`models/tier2_cnn.pt`) | 8.0% (16/200) | 7.0% (14/200) | 7.0% (14/200) | 14x unknown |
| `tier2_cnn_v3` (`models/tier2_cnn_v3.pt`) | 8.0% (16/200) | 7.0% (14/200) | 7.0% (14/200) | 14x unknown |

Detection/link/score rates are identical between models because
`detect()`'s pre-filter still uses the (unchanged) analytic real_bogus
proxy — model-independent by design, matching how real ZTF pipelines gate
on the survey's own native real/bogus score before any project-specific
CNN runs inside `classify()`.

**Decisive evidence the wiring works**: comparing the 14 scored tracklets'
`NEOPosterior` between the two models, **8 of 14 show genuinely different
values** — e.g. tracklet 0: `stellar_artifact` 0.771 (`benchmark_cnn_v1`)
vs. 0.438 (`tier2_cnn_v3`); `neo_candidate` 0.222 vs. 0.555. This is a
real, substantial divergence (not floating-point noise), confirming two
different checkpoints' weights are genuinely being exercised.

Real output files (local/gitignored, referenced here for provenance):
`Logs/reports/injection_recovery_cnn_benchmark_v1_n200*.json`,
`Logs/reports/injection_recovery_cnn_tier2_cnn_v3_n200*.json`.

## Promotion report updated

`Skills/extract_promotion_evidence.py` derived promotion-report-schema
inputs from both real runs:
`docs/evidence/promotion/tier2_cnn_v3_real_cnn_injection_recovery.json`
and `docs/evidence/promotion/benchmark_cnn_v1_real_cnn_injection_recovery.json`
(both committed, durable).

`docs/evidence/promotion/tier2_cnn_v3_promotion_report.json` regenerated
citing the real, model-specific injection-recovery report in place of the
shared `benchmark_cnn_v1_injection_recovery.json`. Still 8/8 checks pass;
`promotion_allowed: false`; `operator_signoff_missing` remains the sole
blocker (unchanged — this closes an evidence-quality gap, not the
human-gated signoff step itself).

`docs/evidence/promotion/tier2_cnn_v3_operator_review_packet.md` updated
to reflect the new evidence and narrow the remaining open question to just
`canonical_eval_report`/`false_discovery_report` (still pipeline-level,
out of scope for this fix).

## What remains open (explicitly, not silently deferred)

`canonical_eval_report` and `false_discovery_report` are still
pipeline-level, not model-specific, for both CNN candidates. Not addressed
in this session — the operator's direction was scoped to injection-recovery
specifically. A future session would need a comparable fix (likely:
building model-specific canonical-eval cases and re-deriving false-discovery
from a real CNN-scored ranking run) before those two checks could also be
considered genuinely model-specific.
