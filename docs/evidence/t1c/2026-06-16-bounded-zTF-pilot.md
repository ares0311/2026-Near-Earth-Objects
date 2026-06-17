# T1-C Evidence: Bounded Supervised ZTF Pilot

## Purpose

This file is the durable GitHub-visible summary for the first bounded T1-C real-data pilot. Raw operational outputs remain local under `Logs/` and are intentionally ignored so the repository supports the normal `git add .` cadence without committing run debris.

## Run Summary

| Field | Value |
|---|---|
| Run ID | `011dd53aa7f4` |
| Timestamp UTC | `20260616_231055_UTC` |
| Field center | RA `83.8221`, Dec `-5.3911` |
| Radius | `1.0` degree |
| JD window | `2458850.0` to `2461120.0` |
| Surveys | `ZTF` |
| Candidate cap | `80` |
| Mode | Dry run; no external submission |
| Elapsed time | `68.21` seconds |
| Pipeline outputs | `2` internal candidates |

## Audit Status

`Skills/audit_real_run.py` produced local JSON/CSV review evidence for run `011dd53aa7f4` and correctly blocked promotion because no expected-known manifest was supplied. This is historical/debug evidence only; it does not close T1-C.

The production T1-C recovery KPI still requires a non-Orion known-object-rich field, an expected-known manifest generated with `Skills/build_recovery_manifest.py`, at least `90%` known-object recovery through `Skills/audit_real_run.py`, and citizen-science operator review. This evidence does not authorize MPC submission, NASA notification, or any impact-probability statement.

## Candidate Review Extract

| Object ID | Review priority | Review flags | Observations | Nights | Arc days | NEO probability | Alert pathway | Human review status |
|---|---|---|---:|---:|---:|---:|---|---|
| `7cb29d31-bf35-4c9c-b03d-0f6c5dff37d0` | high | `below_min_solar_system_motion;long_arc_near_stationary` | 18 | 18 | `724.00125` | `0.108044` | `internal_candidate` | required |
| `459489ba-0e7f-4a72-a055-de35d5e78541` | high | `below_min_solar_system_motion;long_arc_near_stationary` | 4 | 4 | `37.860579` | `0.010054` | `internal_candidate` | required |

## Repository Artifact Policy Applied

The raw files formerly committed from this run are local operational artifacts and should not remain tracked:

- `Logs/pipeline_runs/011dd53aa7f4/checkpoint.json`
- `Logs/pipeline_runs/011dd53aa7f4/run_summary.json`
- `Logs/reports/t1c_real_run_review_011dd53aa7f4.csv`

Future agents should rely on this summary for historical context and regenerate local audit packets as needed.
