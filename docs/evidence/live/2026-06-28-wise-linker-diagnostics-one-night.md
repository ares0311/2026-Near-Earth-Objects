# WISE Linker Diagnostics: One-Night Window

Date: 2026-06-28

Branch/run state: `main` at `b8ca1312` after PR #136.

## Command

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_MAX_THREADS=1 PYTHONPATH=src caffeinate -i uv run --python 3.14 python Skills/run_pipeline.py --ra 58.0 --dec 20.0 --radius 1.0 --start-jd 2458880.5 --end-jd 2458887.5 --surveys WISE --force-refresh --no-resume --output Logs/reports/wise_prefilter_diagnostic_58_20_7d.json
```

## Result

- Run ID: `a24c48a5b975`
- Mode: dry run; no external submission was possible or attempted
- Field: RA `58.0`, Dec `20.0`, radius `1.0` degree
- Window: JD `2458880.5` to `2458887.5`
- WISE rows: `5206`
- WISE columns:
  `['source_id', 'ra', 'dec', 'mjd', 'w1mpro', 'w1sigmpro', 'sso_flg', 'allwise_cntr', 'n_allwise', 'r_allwise']`
- Preprocessed sources: `5200/5206`
- Detected candidates: `5200`
- Known matches: `0`
- Linked tracklets: `0`
- Candidates processed: `0`
- Submission-ready candidates: `0`
- Elapsed time: `68.88` seconds

## Linker Diagnostics

From `Logs/pipeline_runs/a24c48a5b975/checkpoint.json`:

```json
{
  "n_tracklets": 0,
  "min_nights": 2,
  "min_observations": 3,
  "n_nights": 1,
  "n_observations": 5200,
  "n_seed_pairs_total": 0,
  "n_seed_pairs_rate_window": 0,
  "n_seed_pairs_satellite_rejected": 0,
  "n_arcs_below_min_observations": 0,
  "n_arcs_below_min_nights": 0,
  "n_arcs_chi2_rejected": 0
}
```

## Interpretation

PR #136 worked: the checkpoint now explains the zero-tracklet result. This
specific 1.0-degree, 7-day Taurus diagnostic is not a valid multi-night WISE
linking test because all `5200` usable detections fell into one integer-JD
night. The linker correctly formed `0` seed pairs because it requires at least
two nights for a tracklet.

The next D1 diagnostic should use a WISE selection that spans at least two
integer-JD nights after preprocessing, rather than rerunning this same 7-day
window.

## Safety

No MPC submission was performed. No NASA/PDCO notification was performed. No
impact-probability claim was made. No object was described as confirmed.
