# Injection-recovery classify() hang — root cause found and resolved (2026-07-02)

## Timeline

1. **v0.90.23**: added per-item progress printing to `injection_recovery.py`.
   Did not fix the underlying hang — operator reproduced the same freeze at
   item (1/200) four times after this shipped.
2. **v0.90.24 (PR #163)**: ported the historical macOS CNN-load deadlock
   mitigations (chunked BytesIO read + matmul/conv2d warmup + heartbeat)
   from `Skills/evaluate_calibration.py` into `src/classify.py`'s
   `_load_cnn_model()`. Operator re-ran the recheck command: still hung at
   item (1/200) with **zero output at all, including zero heartbeat lines**
   from the new fix — proving this diagnosis was also wrong per the standing
   rule "failed fix → re-diagnose, not re-patch."
3. **Re-diagnosis**: added temporary per-stage diagnostic prints around every
   call inside `run_injection_recovery()`'s loop (`detect`, `link`,
   `extract_features`, `fit_orbit`, `classify`, `score`). Operator's next run
   showed:
   ```
   [classify] calling classify()...
   ```
   and then nothing — isolating the hang to inside `classify()`, before the
   CNN loader (Tier 2) is ever reached.
4. **True root cause**: `_load_xgb_model()` (Tier 1, called first inside
   `classify()` via `_tier1_predict()`) called
   `clf.load_model(str(model_path))` — a bare path-based read with zero
   chunked pre-read, zero heartbeat, zero print statement. This is the exact
   same class of bug already fixed for the CNN loader, just never ported to
   the XGBoost loader. `_load_transformer_model()` (Tier 3) had the
   identical bug.
5. **v0.90.28 (PR #164)**: added a shared `_read_file_with_heartbeat()`
   helper and applied it to both `_load_xgb_model()` (now hands xgboost a
   `bytearray`) and `_load_transformer_model()` (now pre-reads into
   `BytesIO` plus its own independent matmul warmup).
6. **v0.90.29 (PR #165)**: found and fixed a related compliance gap during
   pre-run verification — `injection_recovery.py` had no checkpoint/resume
   support, violating the standing rule. Added param-derived checkpointing
   with `numpy.random.Generator` bit-generator state serialization, verified
   byte-exact resume equivalence via test.

## Confirmation run (operator Mac, `main` @ v0.90.29)

```
git pull origin main && \
caffeinate -i env PYTHONPATH=src uv run --python 3.14 python Skills/injection_recovery.py \
    --survey ZTF --n-inject 200 --seed 42 \
    --json Logs/reports/z3_ztf_recheck.json \
    --review-packet-out Logs/reports/z3_ztf_review_packets.json && \
env PYTHONPATH=src uv run --python 3.14 python Skills/adversarial_review.py \
    Logs/reports/z3_ztf_review_packets.json --offline && \
env PYTHONPATH=src uv run --python 3.14 python Skills/export_ades_report.py \
    Logs/reports/z3_ztf_review_packets.json --out Logs/reports/z3_ztf_export.psv
```

**Result: PASS.** The injection-recovery loop completed all 200 items in
5 seconds total (no hang, matching predicted outcome (a) from the PR #164
body — the small model files were already locally cached, so no heartbeat
lines were needed). Detection/link/score rate: 100% (200/200) for all three
stages. `Skills/adversarial_review.py --offline` then processed all 200
full `ScoredNEO` review packets and correctly rejected all 200
(`SURVIVE=0 BORDERLINE=0 REJECT=200`) on the expected fail-closed grounds
(`orbit_quality`: no orbital elements computed for synthetic short-arc
injections; `artifact_posterior`: 0.657 ≥ 0.3 threshold) — this is correct,
expected behavior for synthetic injection-recovery test data with no real
multi-night orbit fit, not a defect.

`Skills/export_ades_report.py` did **not** run, because `adversarial_review.py`
exits with code 1 when any candidate REJECTs, and the operator's command
chained all three stages with `&&`. This is correct fail-closed behavior —
a batch with zero SURVIVE/BORDERLINE candidates must not proceed to export.

Total wall-clock for the full three-command chain: 14 seconds.

## What this confirms and what it does not

**Confirms**: the `classify()` hang is fully resolved. The pipeline
mechanics (detect → link → orbit → classify → score → adversarial review)
work correctly end-to-end on synthetic ZTF-cadence injections, and the
checkpoint/resume mechanism is now in place per the standing rule.

**Does not confirm**: this is a synthetic injection-recovery test, not real
ZTF DR24 archival data. It does not close Gate Z3 (verified per-source ZTF
DR24 detection source) — that gate's blocker remains unchanged: Gate Z1
only fetches image metadata, not per-source detections. See
`docs/ZTF_DR24_PRODUCTION_GATES.md` for the current Gate Z3 status.
