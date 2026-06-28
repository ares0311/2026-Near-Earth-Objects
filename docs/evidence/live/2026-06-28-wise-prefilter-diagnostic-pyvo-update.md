# WISE Prefilter Diagnostic: pyvo Poll Compatibility Blocker

Date: 2026-06-28

Branch/run state: `main` at `2a786e18` after PR #134.

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
- WISE ADQL included the PR #133 prefilter:
  `sso_flg = 1 OR allwise_cntr IS NULL OR n_allwise = 0`
- Failure: `AttributeError: 'AsyncTAPJob' object has no attribute 'update'`
- Parsed alerts: `0`
- Candidates: `0`
- Tracklets: `0`
- Output JSON written locally: `Logs/reports/wise_prefilter_diagnostic_58_20_7d.json`
- Run summary written locally: `Logs/pipeline_runs/a24c48a5b975/run_summary.json`

## Root Cause

The WISE async polling code assumes the installed `pyvo.AsyncTAPJob` object has
an `update()` method. The operator environment's pyvo job object does not expose
that method, so the polling loop fails before the completed TAP result can be
fetched.

## Required Fix

Make WISE TAP polling compatible with pyvo versions that expose phase refresh
through a method other than `update()`, or no explicit refresh method at all.
The fix must preserve dry-run safety, progress output, and the PR #133 WISE
prefilter.

## Fix Implemented

Branch `codex/wise-pyvo-poll-compat` adds a narrow TAP job refresh helper that
uses public `update()` when present, falls back to pyvo 1.9.0's `_update()`
one-shot refresh when needed, and otherwise reports the cached phase for simple
job handles. The fetch loop still owns the heartbeat output and does not switch
to a blocking silent `wait()`.

Predicted operator output after merge:

- If the diagnosis is correct, the smaller WISE diagnostic will print
  `[fetch] WISE IRSA TAP: phase=... elapsed ...` heartbeats, then either a WISE
  row-count line or a true IRSA job terminal phase.
- If the diagnosis is still wrong, the next failure should no longer be
  `AttributeError: 'AsyncTAPJob' object has no attribute 'update'`; it should
  identify the next IRSA/TAP/fetch-stage failure explicitly.

Validation on the feature branch:

- `PYTHONPATH=src uv run --python 3.14 --extra dev python -m pytest tests/test_fetch.py::TestFetchWiseArchive -q`:
  `20 passed`
- `uv run --python 3.14 --extra dev ruff check src/fetch.py tests/test_fetch.py`:
  all checks passed
- `PYTHONPATH=src uv run --python 3.14 --extra dev python -m mypy src`:
  success across 12 source files

## Safety

No MPC submission was performed. No NASA/PDCO notification was performed. No
impact-probability claim was made. No object was described as confirmed.
