# Stratified Searched-Null-Control Build: Second Batch (Closing the 17→20 Gap)

Date: 2026-07-25 (America/Los_Angeles)

## Objective

The first batch (`docs/evidence/live/2026-07-25-stratified-null-outcome-controls-first-live-run.md`)
produced 11 real controls but left Aten mode at 17/20 after field 7's
genuine acquisition failure. This batch supplies 4 more predeclared
bottom-stratum fields (a margin buffer above the 3 needed) to close the
gap.

## Predeclaration

`data_selection/calibration/stratified_control_targets_v2.json`: 4
bottom-stratum Aten fields (ranks 380-383), selected from the same
`select_survey_fields.select_fields(jd=2461246.64, mode='aten', top_n=99999)`
planning grid, excluding the 55 coordinates in
`data_selection/target_priority_queue.csv` (parsed from its notes/
selection_rule columns) plus the 12 fields already used in
`stratified_control_targets_v1.json`.

## Real result

`Logs/pipeline_runs/field_ranking_calibration/null_outcome_controls_v2.json`:
**4/4 fields produced real, genuine `null_result` outcomes**, 0 failures.

| outcome_id | RA | Dec | nights | tracklets |
|---|---:|---:|---|---:|
| ztf-null-bottom-ra0307p59-decp045p00 | 307.59 | 45.0 | 20230922,24,25 | 0 |
| ztf-null-bottom-ra0302p51-decp037p50 | 302.51 | 37.5 | 20230922,30,1003 | 1 |
| ztf-null-bottom-ra0274p15-decp037p50 | 274.15 | 37.5 | 20230922,25,27 | 1 |
| ztf-null-bottom-ra0008p66-decm030p00 | 8.66 | -30.0 | 20240822,0901,02 | 8 |

No bugs found this run — all three fixes from the first batch (PRs
#272-274) held up cleanly against a fresh set of fields.

## Combined result

6 (v1, top-ranked only) + 11 (first stratified batch) + 4 (this batch) =
**21 Aten-mode real searched-null controls**, clearing the ≥20-per-mode
threshold from `docs/evidence/live/2026-07-21-phase2-field-ranking-calibration.md`.
Combined with the 57 real I41-attributed Aten positives already closed
(`docs/evidence/live/2026-07-24-phase2-aten-exhaustive-calibration-and-null-controls.md`),
**both halves of the Aten-mode calibration-eligibility bar are now met**.

## What this does and does not establish

- Both counts (≥20 positives, ≥20 searched nulls) being met makes fitting
  new Aten ranking coefficients *authorized to attempt*, not *already
  fit*. No coefficient change is made in this sync; the deterministic
  `uncalibrated_transparent_prior` v2 policy remains in force. Actually
  fitting and validating coefficients (and deciding whether to promote
  them) is separate follow-on work, not performed here.
- Atira mode remains structurally capped at 7 real positives (the entire
  population MPC has ever recorded) and is not eligible for this same
  path — see the operator decision flagged as still open in
  `docs/PRODUCTION_READINESS.md`.
- Does not claim a real discovery — all 15 new fields across both batches
  are genuine null results, consistent with this project's entire prior
  history.

## Exact next work

1. Merge `data_selection/calibration/ztf_field_null_outcomes_v2.json`'s 20
   entries with these 4 new ones into a v3 dataset (not overwriting v2 in
   place), citing this evidence file.
2. Decide whether/how to pursue Aten coefficient fitting now that both
   evidence thresholds are met, or whether to keep the transparent-prior
   policy indefinitely per the Hunter directive's own framing (a
   deterministic, explainable ranker was never blocked on calibration).
