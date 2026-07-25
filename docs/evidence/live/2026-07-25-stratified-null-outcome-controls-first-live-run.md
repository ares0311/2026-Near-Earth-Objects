# Stratified Searched-Null-Control Build: First Live Run

Date: 2026-07-25 (America/Los_Angeles)

## Objective

Execute the 12 predeclared, stratified (top/middle/bottom/random) Aten
fields from `data_selection/calibration/stratified_control_targets_v1.json`
(PR #271) for real, to extend `ztf_field_null_outcomes_v1.json`'s
top-ranked-only, biased control cohort toward the ≥20-per-mode Aten
searched-null-control target.

## Bugs found and fixed live (three PRs, before a clean result was obtained)

1. **PR #272** — `hunter_cli.execute_target()` requires a pre-committed
   coverage-inventory record, which only `create-new-search --mode new`'s
   adaptive-expansion loop populates. A field selected directly from the
   planning grid (as this builder's predeclared inputs are) had not been
   through that step, so 11/12 fields failed with `no committed coverage
   record found`. Fixed by adding `_ensure_coverage_committed()`, which
   runs one real live coverage-preflight check via `hunter_cli.
   _live_coverage_check()` (the same helper `create-new-search` itself
   uses) only when a field isn't already covered.
2. **PR #273** — The fix above passed `hunter_state.target_id_from_radec()`'s
   dotted ID (e.g. `radec_31.06_15.00`) as the coverage batch manifest's
   `field_id`; that validator (`ztf_alert_archive_portfolio.py`) rejects
   dots. Fixed by using the same dot-free `_field_id_from_radec()` helper
   `discover_new_targets()` already uses for this exact purpose.
3. **PR #274** — After both fixes, the real run left 23 failure entries in
   the checkpoint for only 1 genuine failure: `build_controls()` deduped
   `entries` by `outcome_id` on resume but never cleared stale `failures`
   records from the two earlier debugging attempts. Fixed by dropping any
   existing failure entry for a field's `outcome_id` immediately before
   retrying it.

Each fix was verified with the full sharded test suite (100% `src/`
coverage) and merged (auto-merge on green CI) before the next real run.

## Real result (clean, post-fix)

`Logs/pipeline_runs/field_ranking_calibration/null_outcome_controls_v1.json`
(gitignored checkpoint; manually cleaned of the pre-PR-#274-fix stale
failure records it accumulated during the debugging runs above, using the
same outcome_id-keyed dedup logic the fix now applies automatically):

**11/12 fields produced real, genuine `null_result` outcomes** (zero
candidates survived adversarial review in every case, tracklet counts
ranged 0-52 — including one field with 52 raw tracklets and still zero
survivors, the same "high tracklet count, zero survivors" pattern already
seen in this project's prior field tests):

| outcome_id | stratum | rank | RA | Dec | nights | tracklets |
|---|---|---:|---:|---:|---|---:|
| ztf-null-top-ra0031p06-decp015p00 | top | 5 | 31.06 | 15.0 | 20230924,26,27 | 0 |
| ztf-null-top-ra0040p59-decp022p50 | top | 7 | 40.59 | 22.5 | 20230924,26,27 | 0 |
| ztf-null-top-ra0037p82-decp007p50 | top | 8 | 37.82 | 7.5 | 20230924,26,27 | 0 |
| ztf-null-middle-ra0310p15-decm007p50 | middle | 210 | 310.15 | -7.5 | 20230922,24,27 | 1 |
| ztf-null-middle-ra0324p72-decm022p50 | middle | 211 | 324.72 | -22.5 | 20230924,28,30 | 6 |
| ztf-null-middle-ra0236p34-decp037p50 | middle | 212 | 236.34 | 37.5 | 20231005,07,11 | 8 |
| ztf-null-bottom-ra0293p06-decp037p50 | bottom | 387 | 293.06 | 37.5 | 20230924,26,30 | 2 |
| ztf-null-bottom-ra0283p61-decp037p50 | bottom | 388 | 283.61 | 37.5 | 20230922,25,27 | 1 |
| ztf-null-random-ra0330p00-decp060p00 | random | 271 | 330.0 | 60.0 | 20230924,26,27 | 2 |
| ztf-null-random-ra0243p54-decp022p50 | random | 319 | 243.54 | 22.5 | 20230928,1004,06 | 0 |
| ztf-null-random-ra0194p83-decm022p50 | random | 23 | 194.83 | -22.5 | 20240114,18,0211 | 52 |

**1/12 fields (bottom stratum, rank 386, RA 17.32 Dec -30.0) genuinely
failed**: `only acquired 0/3 real exposure(s) ... after trying 29/29
available covered night(s)`. All 29 nights the wide coverage-preflight box
(2.0 deg) recorded as covered failed to resolve a single exposure at the
narrow 0.01-deg single-exposure acquisition box. This is the same real
ZTF field/CCD-grid alignment limitation already disclosed in
`docs/evidence/live/2026-07-24-hunter-followup-mode-first-live-run.md`
(PR #268) — not a new bug, and not usable as a control (it is neither a
`null_result` nor a `survivor_found`; the field was never actually
searched).

## What this does and does not establish

- Extends the real, stratified (not just top-ranked) null-control evidence
  from 0 to 11 fields. Combined with the existing 6 top-ranked controls in
  `ztf_field_null_outcomes_v1.json`, that is **17 total real searched-null
  controls**, still 3 short of the ≥20-per-mode Aten calibration threshold.
- Does not claim a real discovery (all 11 executed fields are genuine null
  results, consistent with this project's entire prior history).
- Does not authorize fitting or promoting ranking-coefficient weights —
  that still requires ≥20 source-aligned positives (closed, 57 real, see
  `docs/evidence/live/2026-07-24-phase2-aten-exhaustive-calibration-and-null-controls.md`)
  **and** ≥20 searched controls per mode (still open at 17/20).

## Exact next work

1. Merge `ztf_field_null_outcomes_v1.json`'s 6 entries with these 11 new
   ones into a new versioned dataset (not overwriting v1 in place, per
   this project's storage-policy convention), citing this evidence file.
2. Select and execute ~3 more stratified fields (the same
   `stratified_control_targets_v1.json` predeclare-then-execute pattern)
   to close the 17-to-20 gap.
3. `Skills/validate_field_null_outcomes.py --manifest <new file>` and
   `Skills/evaluate_field_ranking_policy.py --nulls <new file>` both
   accept an explicit override path, so no change to their defaults is
   needed until calibration coefficient-fitting is actually authorized.
