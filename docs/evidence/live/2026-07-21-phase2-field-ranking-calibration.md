# Phase 2 Field-Ranking Calibration and Eligibility Audit

Date: 2026-07-21 (America/Los_Angeles)

## Objective

Close the highest-priority Phase 2 ranking gap without treating unsearched
fields as nulls or fitting scientific weights to a biased cohort. The work
binds real outcomes to evidence, builds a reproducible positive discovery
reference, audits the v1 policy, fixes the hard eligibility defect exposed by
that audit, and preserves both pre- and post-fix results.

## Authoritative acquisition contract

The positive builder uses the current official MPC APIs through the repo-native
Python client:

- [MPC List API](https://docs.minorplanetcenter.net/mpc-ops-docs/apis/list/):
  `atens` and `atiras`, filtered by provisional-designation year;
- [MPC Observations API](https://docs.minorplanetcenter.net/mpc-ops-docs/apis/get-obs/):
  `ADES_DF`, with an explicit discovery marker required.

No `curl`, AI judgment, unpublished cross-repo code, or manual target
substitution is in the path. The builder evaluates the complete API result for
each requested year, freezes the exact SHA256-ordered targets before history
acquisition, checkpoints every accepted event, and fails loudly on provider,
schema, identity, or discovery-marker errors.

## Durable inputs

- `mpc_aten_discovery_fields_v2.json`: 1,646 Aten candidates evaluated;
  56 deterministic positives selected (8/year, 2018-2024); 56/56 complete.
- `mpc_atira_discovery_fields_v2.json`: all 19 Atiras returned for 2018-2024;
  19/19 complete.
- `ztf_field_null_outcomes_v1.json`: nine genuinely searched, at-least-three-
  night ZTF null outcomes with exact rank, score, mode, ranking JD, execution,
  tracklet/review counts, evidence paths, and evidence hashes.
- `ztf_field_null_outcome_queue_rows_v1.csv`: immutable snapshot of the exact
  queue rows used. The mutable append-only operator queue remains the origin;
  later legitimate queue additions cannot invalidate this calibration record.
- `ztf_dr24_new_field_coverage_preflight_v1.json`: sanitized committed copy of
  the measured coverage inventory previously available only under ignored
  runtime logs.

Two insufficient-coverage searches are recorded as exclusions and never
relabeled as null outcomes.

## Pre-fix independent result

`ztf_field_ranking_audit_v1_pre_eligibility_fix.json` reproduces all nine
historical selector scores within `0.000058` absolute error. It then shows that
v1 used its narrow preference windows as hard eligibility vetoes:

| Mode | All positive eligible | ZTF I41 positive eligible | Searched null eligible |
|---|---:|---:|---:|
| Aten | 1/56 | 0/1 | 6/6 |
| Atira/IEO | 2/19 | 1/7 | 3/3 |

This is a behavioral defect: a preferred quadrature/twilight peak is a ranking
prior, not evidence that all discoveries outside that peak are ineligible.

## v2 decision and post-fix result

`ztf_field_ranking_v2.json` keeps the exact v1 weights and preference peaks,
but adds distinct hard eligibility ranges:

- Aten: 60-180 degrees;
- IEO/Atira: 20-60 degrees;
- all-NEO: 60-180 degrees;
- recovery: 120-180 degrees.

The Atira upper bound rounds the maximum of the seven source-aligned I41
positives (53.14 degrees) outward to 60 degrees. The Aten range contains the
source-aligned I41 positive (137.81 degrees) and the general MPC Aten reference
range. The evidence file and SHA256 are embedded in the policy.

`ztf_field_ranking_audit_v2.json` shows:

| Mode | All positive eligible | ZTF I41 positive eligible | Searched null eligible |
|---|---:|---:|---:|
| Aten | 55/56 | 1/1 | 6/6 |
| Atira/IEO | 14/19 | 7/7 | 3/3 |

The remaining all-source exclusions include geometry/visibility from non-ZTF
discovery stations; they are disclosed rather than used to broaden a
Palomar-specific production gate without source-aligned evidence.

## Coefficient decision

No coefficient change or calibrated probability claim is authorized. The
source-aligned cohort has only 1 Aten and 7 Atira positives, versus 6 and 3
top-selected searched nulls. The audit requires at least 20 source-aligned
positives and 20 searched controls per mode before fitting, and the current
nulls are not random/bottom-ranked controls. The deterministic transparent v2
prior is retained. Pairwise AUC remains a diagnostic only and is not used as a
promotion claim.

## Verification commands

```bash
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python \
  Skills/validate_field_null_outcomes.py

UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python \
  Skills/evaluate_field_ranking_policy.py \
  --out Logs/pipeline_runs/field_ranking_calibration/ztf_field_ranking_audit_v2.json
```

Focused verification after the v2 change: 101 tests passed; ruff passed.

## Exact next work

Phase 2 remains active. Build a predeclared, source-aligned field outcome
experiment with top/middle/bottom/random eligible fields, identical uncensored
processing, costs, and at least 20 positive plus 20 searched-control outcomes
per mode. Until that exists, do not fit or promote discovery-yield weights.
Phase 3 CLI/durable-search packaging remains blocked on Phase 2 closure.
