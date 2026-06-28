# WISE Prefilter Diagnostic After pyvo Polling Fix

Date: 2026-06-28

Branch/run state: `main` at `dd35a8c0` after PR #135.

## Command

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_MAX_THREADS=1 PYTHONPATH=src caffeinate -i uv run --python 3.14 python Skills/run_pipeline.py --ra 58.0 --dec 20.0 --radius 1.0 --start-jd 2458880.5 --end-jd 2458887.5 --surveys WISE --force-refresh --no-resume --output Logs/reports/wise_prefilter_diagnostic_58_20_7d.json
```

## Result

- Run ID: `a24c48a5b975`
- Mode: dry run; no external submission was possible or attempted
- Field: RA `58.0`, Dec `20.0`, radius `1.0` degree
- Window: JD `2458880.5` to `2458887.5`
- Survey: `WISE`
- pyvo compatibility fix outcome: passed; the old
  `AttributeError: 'AsyncTAPJob' object has no attribute 'update'` did not recur
- WISE TAP phases:
  - `EXECUTING` at elapsed `0m00s`
  - `COMPLETED` at elapsed `0m31s`
- WISE rows: `5206`
- WISE columns:
  `['source_id', 'ra', 'dec', 'mjd', 'w1mpro', 'w1sigmpro', 'sso_flg', 'allwise_cntr', 'n_allwise', 'r_allwise']`
- Parsed alerts: `5206`
- Preprocessed sources: `5200/5206`
- Detected candidates: `5200`
- Known matches: `0`
- Linked tracklets: `0`
- Candidates processed: `0`
- Submission-ready candidates: `0`
- Elapsed time: `38.85` seconds
- Output JSON written locally: `Logs/reports/wise_prefilter_diagnostic_58_20_7d.json`
- Run summary written locally: `Logs/pipeline_runs/a24c48a5b975/run_summary.json`

## Interpretation

PR #135 closed the pyvo polling blocker. The remaining D1 blocker has moved
downstream: WISE rows now reach detection/linking, but the current discovery
archive path emits one singleton candidate per prefiltered row and the linker
forms no multi-night tracklets in this field/window.

## Safety

No MPC submission was performed. No NASA/PDCO notification was performed. No
impact-probability claim was made. No object was described as confirmed.
