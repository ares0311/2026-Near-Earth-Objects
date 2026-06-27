# WISE Live Archive Sweep Evidence

Date: 2026-06-27

Operator: Jerome W. Lindsey III

Command source: operator terminal transcript pasted into Codex.

## Command

```bash
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run python Skills/run_pipeline.py \
    --ra 58.0 --dec 20.0 --radius 3.5 \
    --start-jd 2458880.5 --end-jd 2458910.5 \
    --surveys WISE --no-dry-run --force-refresh --no-resume
```

## Code State

- Starting branch: `main`
- Pull result: fast-forward from `6b01a6d7` to `4a1a1762`
- Included PRs through: PR #127
- This run happened before PR #131, which changes discovery sweeps to stay in alert dry-run mode and fail closed for MPC submission.

## Run Summary

- Run ID: `756e0dc7b6be`
- Field: RA `58.0`, Dec `20.0`, radius `3.5` degrees
- Window: JD `2458880.5` to `2458910.5` (`30.0` days)
- Survey: `WISE`
- IRSA query mode: WISE async TAP against `neowiser_p1bs_psd`
- IRSA returned rows: `111913`
- IRSA returned columns: `['ra', 'dec', 'mjd', 'w1mpro', 'w1sigmpro']`
- Parsed WISE observations: `85335`
- Preprocess pass: `85335/85335`
- Moving-object candidates: `535`
- Known matches: `0`
- Tracklets formed: `0`
- Candidates processed: `0`
- Submission-ready candidates: `0`
- Elapsed time: `34m08s`
- Run summary path: `Logs/pipeline_runs/756e0dc7b6be/run_summary.json` (local, gitignored)
- Pipeline output: empty JSON list `[]`

## Observed Warnings

The run printed masked-value warnings while parsing WISE photometry:

- `Warning: converting a masked element to nan` for `w1sigmpro`
- `Warning: converting a masked element to nan` for `w1mpro`

These warnings indicate that the WISE table can contain masked photometric values. The parser converted some masked values to `nan`, and downstream stages still completed without crashing.

## Interpretation

This run is useful production evidence even though it did not produce a candidate:

- The WISE async TAP query path works on a real archive field and returned a large, time-filtered catalog result.
- The previous WISE zero-fetch/schema uncertainty is resolved for this field: the live catalog columns are `ra`, `dec`, `mjd`, `w1mpro`, and `w1sigmpro`.
- The current discovery blocker is now downstream of fetch: WISE detection/linking produced `535` candidates but `0` multi-night tracklets.
- The run used the old `--no-dry-run` instruction and printed that external submissions were enabled. No submission attempt occurred because zero candidates reached alert processing, but this confirms why PR #131 is needed before the next operator command.

## Safety

- No external MPC submission was performed.
- No NASA PDCO contact was performed.
- No impact-probability claim was made.
- No candidate was described as confirmed.

## Next Production Implication

Do not ask the operator to repeat this exact 34-minute run until the result is used. The next code work should:

1. Keep discovery sweeps in alert dry-run mode via PR #131 or later.
2. Treat WISE masked photometry explicitly rather than allowing masked values to become `nan`.
3. Diagnose why `535` WISE candidates yielded `0` tracklets before widening the field or running another long WISE sweep.
