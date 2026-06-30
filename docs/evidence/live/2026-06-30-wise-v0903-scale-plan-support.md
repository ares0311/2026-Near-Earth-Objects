# WISE v0.90.3 Scale-Plan Support Metrics

Date: 2026-06-30 UTC

## Purpose

Regenerate the Taurus WISE/NEOWISE 0.2 degree, 370 day dry-run scale plan after
v0.90.3 added local cross-night support metrics to recommended diagnostic
subfields. This verifies that the next D1 diagnostic can be selected from actual
pipeline output rather than guessed sky coordinates.

## Command

```bash
# Keep native numerical libraries to one thread each so Python-level pipeline
# work does not oversubscribe the local Apple Silicon system.
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export NUMEXPR_MAX_THREADS=1
export PYTHONPATH=src

# Prevent macOS sleep during the live IRSA TAP query. This is dry-run only:
# it writes a scale plan and does not authorize any external submission.
caffeinate -i uv run --python 3.14 python Skills/run_pipeline.py \
  --ra 58.0 --dec 20.0 --radius 0.2 \
  --start-jd 2458880.5 --end-jd 2459250.5 \
  --surveys WISE --no-resume --force-refresh \
  --link-scale-plan-out Logs/reports/wise_link_scale_plan_v0903_58_20_370d.json \
  --output Logs/reports/wise_link_scale_plan_probe_v0903_58_20_370d.json
```

## Results

- Run ID: `296774bc0b0e`
- Mode: dry run; no external submission
- Field: RA `58.0`, Dec `20.0`, radius `0.2` degrees
- Window: JD `2458880.5` to `2459250.5`
- Survey: WISE
- WISE rows/alerts: `12061`
- Preprocessed sources: `12042/12061`
- Detected singleton candidates: `12042`
- Known matches: `0`
- Integer-JD nights: `6`
- Estimated link seed pairs: `11786731`
- Default link seed-pair budget: `1000000`
- Status: expected fail-closed seed-pair budget stop
- Scale plan: `Logs/reports/wise_link_scale_plan_v0903_58_20_370d.json`
- Probe output: `Logs/reports/wise_link_scale_plan_probe_v0903_58_20_370d.json`

## v0.90.3 Recommended Subfields

The regenerated plan ranks recommended subfields by local cross-night seed-pair
support and reports whether the radius contains at least three observations
across at least two nights.

| Rank | RA | Dec | Radius | Support | Observations | Nights | Estimated seed pairs |
|---:|---:|---:|---:|---|---:|---:|---:|
| 1 | `58.1` | `19.9` | `0.0466` | yes | `701` | `4` | `48105` |
| 2 | `57.9` | `20.1` | `0.0466` | yes | `691` | `5` | `33540` |
| 3 | `58.1` | `20.1` | `0.0466` | yes | `531` | `4` | `25053` |
| 4 | `57.9` | `19.9` | `0.0466` | yes | `665` | `5` | `18776` |
| 5 | `58.3` | `19.9` | `0.0466` | no | `0` | `0` | `0` |
| 6 | `58.3` | `20.1` | `0.0466` | no | `0` | `0` | `0` |

The prior failed diagnostic was rank 3: RA `58.1`, Dec `20.1`, radius
`0.0466`. Do not rerun it as the next diagnostic.

## Next Verified Diagnostic

The next D1 live diagnostic should use the rank 1 support-positive subfield:
RA `58.1`, Dec `19.9`, radius `0.0466`.

This command was attempted by Codex after the scale plan, but the Codex approval
layer rejected the escalated live run because of a usage limit. The command was
not rejected by the repository, Python environment, IRSA, or the pipeline.

```bash
# Keep native numerical libraries to one thread each so local Python pipeline
# work remains deterministic and avoids oversubscription.
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export NUMEXPR_MAX_THREADS=1
export PYTHONPATH=src

# Run the top v0.90.3 support-positive WISE diagnostic subfield. This is dry-run
# only, prevents macOS sleep, writes full ScoredNEO review packets if any
# tracklets are produced, and does not enable external submission.
caffeinate -i uv run --python 3.14 python Skills/run_pipeline.py \
  --ra 58.1 --dec 19.9 --radius 0.0466 \
  --start-jd 2458880.5 --end-jd 2459250.5 \
  --surveys WISE --no-resume --force-refresh \
  --review-packet-out Logs/reports/wise_diag_subfield_58p1_19p9_review_packets.json \
  --output Logs/reports/wise_diag_subfield_58p1_19p9_candidates.json
```

Do not run `Skills/adversarial_review.py` unless the pipeline reports a non-zero
full `ScoredNEO` packet count.

## Safety

No MPC submission was performed. No NASA/PDCO pathway was triggered. No impact
probability was computed or claimed. Raw run outputs remain under ignored
`Logs/`; this document is the durable sanitized evidence.
