# Phase 2 Aten Exhaustive Calibration + Stratified Null-Control Build

Date: 2026-07-24 (America/Los_Angeles)

## Objective

Close the Aten side of the `≥20 source-aligned positives + ≥20 searched
controls per mode` calibration-eligibility bar from
`docs/evidence/live/2026-07-21-phase2-field-ranking-calibration.md`, and
start closing the searched-control side, which that audit's own next-work
section flagged as biased (top-ranked only, not a random/stratified
sample).

## Aten source-aligned positives: exhaustive result

Re-ran `Skills/build_field_ranking_calibration.py` against the full MPC
`atens` list (`--list-name atens --all-per-year --years 2018..2026`),
evaluating every candidate the API returns per year rather than a capped
per-year sample:

- `Logs/pipeline_runs/field_ranking_calibration/mpc_aten_discovery_fields_exhaustive.json`
- 2,109 candidates selected, 2,085 accepted (24 rejected as ineligible —
  single-night-only published history or missing discovery marker; see
  the PR #270 fix below), all checkpointed with `query_log` entries.
- **57 of the 2,085 accepted events have a real `I41` (ZTF) discovery
  station** — verified directly from the file:
  `[e for e in events if e["discovery_observation"]["station"] == "I41"]`
  → `len == 57`.

This **supersedes** the `docs/PRODUCTION_READINESS.md` "only 1 Aten...
exist today" figure, which was the 2026-07-21 audit's earlier, much
smaller 56-candidate/8-per-year sample (1 I41 hit). The exhaustive result
definitively clears the ≥20 source-aligned-positive threshold for Aten.

## Bug found and fixed en route (PR #270)

`build_field_ranking_calibration.py`'s per-candidate loop treated a
deterministic ineligibility (`ValueError` from `_event_from_observations`,
e.g. a candidate whose only published history is a single UTC night) the
same as a transient fetch failure — both aborted the whole run. Found live
at candidate 352/450 of the first exhaustive-style attempt. Fixed by
splitting the retry loop so `ValueError` is caught, logged to `query_log`
as `rejected_ineligible`, and the loop continues to the next candidate;
resume now also skips already-rejected candidates without re-fetching. 2
new regression tests (`test_build_field_ranking_calibration.py`). Merged
to `main` before the exhaustive run above.

## Searched-null controls: stratified sample built (PR #271)

The existing `data_selection/calibration/ztf_field_null_outcomes_v1.json`
has 6 controls, all top-ranked (score 0.87-0.93) — its own
`interpretation_limits` already discloses this as "not a random or
bottom-ranked control sample."

Added `Skills/build_field_null_outcome_controls.py` (reuses
`hunter_cli.execute_target()` for the real acquisition -> link -> review
chain; checkpoints per field; isolates per-field failures) and a
predeclared 12-field stratified sample,
`data_selection/calibration/stratified_control_targets_v1.json`: 3
top-ranked, 3 middle-ranked, 3 bottom-ranked, 3 uniform-random draws from
`select_survey_fields.select_fields(jd=2461246.64, mode='aten')`'s full
388-field eligible set, excluding all 43 coordinates already present in
`data_selection/target_priority_queue.csv`, seed=20260724.

10 new offline tests, ruff/mypy clean, full sharded suite green with 100%
`src/` coverage. Merged as PR #271.

## Not yet done

The 12 predeclared fields have not yet been executed — that requires 12
real, live multi-night ZTF acquisition+link+review runs. Once run, results
extend (not overwrite) `ztf_field_null_outcomes_v1.json` as a new
versioned dataset. 6 existing + up to 12 new = 18; may need one more small
stratified batch to clear 20 if any of the 12 fail coverage/execution.

## Atira ceiling: exhaustive result, definitive

Ran the same exhaustive command shape against `--list-name atiras`,
replacing the earlier incomplete `mpc_atira_all_discovery_fields_v2.json`
(`complete: false`, only 10/40 accepted):

- `Logs/pipeline_runs/field_ranking_calibration/mpc_atira_discovery_fields_exhaustive.json`
- **23/23 candidates accepted, 0 rejected.** This is every Atira MPC's
  `atiras` list returns for 2018-2026 — the entire real population, not a
  sample. Confirms the "only 23 Atiras ever discovered" figure in
  `CLAUDE.md`/`docs/near_earth_objects_research_brief.md`.
- **7 of the 23 are I41 (ZTF)-attributed**: 2019 AQ3, 2019 LF6, 2020 AV2,
  2020 OV1, 2021 PB2, 2021 BS1, 2021 VR3.

Because this is the full, current, exhaustive population (not a partial
sample that more querying could grow), **7 is a hard ceiling, not a
data-gathering gap**: the ≥20-source-aligned-positive bar as written is
structurally unreachable for Atira mode under this evidence definition
and will remain so unless ZTF discovers more Atiras in the future. This
is a finding for the operator to weigh — whether to revise the Atira
threshold (e.g. to a number ≤7, or to a different evidence type), treat
Atira mode as permanently non-calibratable and keep it on the
deterministic-transparent-prior path indefinitely, or something else — no
threshold has been changed in this sync; the deterministic v2 prior
remains in force for Atira mode unchanged.

## Verification commands

```bash
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python \
  Skills/build_field_ranking_calibration.py \
  --out Logs/pipeline_runs/field_ranking_calibration/mpc_aten_discovery_fields_exhaustive.json \
  --years 2018 2019 2020 2021 2022 2023 2024 2025 2026 \
  --all-per-year --list-name atens --seed 42
```
