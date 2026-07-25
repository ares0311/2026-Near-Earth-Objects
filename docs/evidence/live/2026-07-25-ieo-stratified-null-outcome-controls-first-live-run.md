# IEO/Atira Stratified Searched-Null-Control Build: Closing the 3→7 Gap

Date: 2026-07-25 (America/Los_Angeles)

## Objective

PR #276 revised the Atira/ieo calibration threshold to its real
population ceiling (7 positives, already met) and set the matching
`searched_null` minimum to 7 as well (not yet met, at 3). Close that gap
with the same predeclare-then-execute stratified pattern already
validated for Aten mode.

## Predeclaration

`data_selection/calibration/stratified_control_targets_ieo_v1.json`: 6
IEO-mode fields (2 top, 2 middle, 2 bottom stratum), selected from
`select_survey_fields.select_fields(jd=2461246.64, mode='ieo', top_n=99999)`'s
161-field eligible pool, excluding the 59 coordinates already in
`data_selection/target_priority_queue.csv`, the 3 existing ieo entries in
`ztf_field_null_outcomes_v3.json`, and the 12 Aten-mode stratified fields
already used. 6 predeclared (a margin buffer above the 4 needed).

## Real result

`Logs/pipeline_runs/field_ranking_calibration/null_outcome_controls_ieo_v1.json`:
**4/6 fields produced real, genuine `null_result` outcomes**; 2 genuinely
failed acquisition.

| outcome_id | stratum | rank | RA | Dec | nights | tracklets |
|---|---|---:|---:|---:|---|---:|
| ztf-null-top-ra0158p86-decp007p50 | top | 2 | 158.86 | 7.5 | 20231012,13,19 | 0 |
| ztf-null-top-ra0155p29-decp015p00 | top | 3 | 155.29 | 15.0 | 20231030,31,1208 | 0 |
| ztf-null-middle-ra0127p50-decp000p00 | middle | 86 | 127.5 | 0.0 | 20230924,1013,15 | 29 |
| ztf-null-middle-ra0108p70-decm015p00 | middle | 87 | 108.7 | -15.0 | 20231003,05,07 | 47 |

Both failures were bottom-stratum fields at Dec=-30.0 (RA 103.92 and RA
95.26), each exhausting all 22-28 covered nights without resolving a
single narrow-box exposure — the same disclosed ZTF field/CCD-grid
alignment limitation from PR #268 (not a new bug). Notably, the one Aten
bottom-stratum failure from the earlier batch was also at Dec=-30.0 — a
real, observed pattern worth flagging for a future session, though not
investigated further here (2 failures at the same declination is
suggestive, not conclusive, and not this session's scope to chase).

## Combined result

3 (v3, pre-existing) + 4 (this batch) = **7 IEO/Atira-mode real
searched-null controls**, exactly meeting the revised threshold from
PR #276.

## What this does and does not establish

- **Both halves of the revised Atira/ieo calibration-eligibility bar are
  now met** (7/7 positives, 7/7 searched nulls), alongside Aten's
  already-met 57/21 (vs. 20/20). The gate's `all(...)` check across every
  mode should now evaluate `True` for the first time.
- Per the gate's own deliberate design
  (`if coefficient_update_authorized: raise ValueError(...)`), this is
  expected to **crash loudly** the next time `build_policy_audit()` runs
  with all current data — a forced checkpoint requiring an explicit human
  decision (implement and review real coefficient-fitting logic, which
  does not exist yet) before anything is fit or promoted. This is
  correct, intended behavior, not a bug to fix.
- Does not claim a real discovery — all 4 new fields are genuine null
  results, consistent with this project's entire prior history.

## Exact next work

1. Merge `ztf_field_null_outcomes_v3.json`'s 24 entries with these 4 new
   ones into a v4 dataset (not overwriting v3 in place).
2. Run `evaluate_field_ranking_policy.py` against the new v4 defaults —
   expect it to raise the tripwire `ValueError`. This is the signal that
   real coefficient-fitting implementation work (design, code, tests,
   operator review) is now a legitimate next initiative, not yet started.
