# WISE v0.90.5 Parent-Field Scale-Plan Probe

Date: 2026-06-30 UTC

## Purpose

Use the v0.90.5 WISE archive probe selector to move D1 beyond the exhausted
Taurus diagnostics. The selector produced a non-Taurus parent field and a
dry-run scale-plan command so the next WISE/NEOWISE window could be measured
before any full diagnostic run.

This is a D1 scale-planning result, not candidate evidence.

## Command

```bash
# Keep native numerical libraries to one thread each so local Python pipeline
# work remains deterministic and avoids oversubscription.
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export NUMEXPR_MAX_THREADS=1
export PYTHONPATH=src

# Run the v0.90.5-generated non-Taurus WISE parent-field scale-plan probe.
# This is dry-run only, prevents macOS sleep, writes a link scale plan, and
# does not authorize external submission.
caffeinate -i uv run --python 3.14 python Skills/run_pipeline.py \
  --ra 209.6400 --dec -15.0000 --radius 0.2000 \
  --start-jd 2458880.5 --end-jd 2459250.5 \
  --surveys WISE --no-resume --force-refresh \
  --link-scale-plan-out Logs/reports/wise_scale_plan_ra209p64_decm15p00_2458880.5_2459250.5.json \
  --output Logs/reports/wise_scale_probe_ra209p64_decm15p00_2458880.5_2459250.5.json
```

## Results

- Run ID: `d02685231d3f`
- Mode: dry run; no external submission
- Field: RA `209.64`, Dec `-15.0`, radius `0.2` degrees
- Window: JD `2458880.5` to `2459250.5`
- Survey: WISE
- WISE rows/alerts: `16582`
- Preprocessed sources: `16558/16582`
- Detected singleton candidates: `16558`
- Known matches: `0`
- Integer-JD nights: `4`
- Estimated link seed pairs: `27845455`
- Default link seed-pair budget: `1000000`
- Status: expected fail-closed seed-pair budget stop
- Scale plan: `Logs/reports/wise_scale_plan_ra209p64_decm15p00_2458880.5_2459250.5.json`
- Probe output: `Logs/reports/wise_scale_probe_ra209p64_decm15p00_2458880.5_2459250.5.json`
- Run summary: `Logs/pipeline_runs/d02685231d3f/run_summary.json`
- Elapsed: `96.1` seconds

The probe output JSON is an empty list (`[]`) because the run stopped before
linking, as intended, after writing the scale plan.

## Recommended Diagnostic Subfields

The scale plan recommended a diagnostic radius of `0.0303` degrees and ranked
subfields by local cross-night seed-pair support.

| Rank | RA | Dec | Radius | Support | Observations | Nights | Estimated seed pairs |
|---:|---:|---:|---:|---|---:|---:|---:|
| 1 | `209.5` | `-14.9` | `0.0303` | yes | `686` | `4` | `58596` |
| 2 | `209.7` | `-14.9` | `0.0303` | yes | `425` | `4` | `18599` |
| 3 | `209.5` | `-15.1` | `0.0303` | yes | `351` | `4` | `14280` |
| 4 | `209.7` | `-15.1` | `0.0303` | yes | `470` | `4` | `11864` |
| 5 | `209.9` | `-15.1` | `0.0303` | no | `0` | `0` | `0` |
| 6 | `209.9` | `-14.9` | `0.0303` | no | `0` | `0` | `0` |

## Root Cause And Interpretation

The v0.90.5 selector successfully found a non-Taurus, WISE-populated parent
field. The parent field is too dense for the default all-pairs linker budget,
so the correct next action is not to override `--max-link-seed-pairs`; it is to
run the top support-positive diagnostic subfield in dry-run mode and inspect
full review packets only if tracklets are formed.

## Next Diagnostic Command

Run this from merged `main` after this evidence is committed:

```bash
# Keep native numerical libraries to one thread each so local Python pipeline
# work remains deterministic and avoids oversubscription.
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export NUMEXPR_MAX_THREADS=1
export PYTHONPATH=src

# Run the rank 1 support-positive WISE diagnostic subfield from the v0.90.5
# parent-field scale plan. This is dry-run only, prevents macOS sleep, writes
# full ScoredNEO review packets if any tracklets are produced, and does not
# authorize external submission.
caffeinate -i uv run --python 3.14 python Skills/run_pipeline.py \
  --ra 209.5 --dec -14.9 --radius 0.0303 \
  --start-jd 2458880.5 --end-jd 2459250.5 \
  --surveys WISE --no-resume --force-refresh \
  --review-packet-out Logs/reports/wise_diag_subfield_209p5_m14p9_review_packets.json \
  --output Logs/reports/wise_diag_subfield_209p5_m14p9_candidates.json
```

Do not run `Skills/adversarial_review.py` unless the pipeline reports a
non-zero full `ScoredNEO` packet count.

## Safety

No MPC submission was performed. No NASA/PDCO pathway was triggered. No impact
probability was computed or claimed. Raw run outputs remain under ignored
`Logs/`; this document is the durable sanitized evidence.
