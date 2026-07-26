# Hunter PROD final remediation evidence — 2026-07-25

## Scope and authority

This record closes the three blockers reopened as HP-10 through HP-12 in
`docs/OPERATOR_GO_NO_GO_RUNBOOK.md`. It supersedes the earlier claim that the
v3 weighted prior plus 2-degree coverage eligibility was sufficient to call
Hunter PROD.

No MPC/NEOCP submission, external alert, impact claim, or discovery claim was
made.

## HP-10 — best-supported ranking/value contracts

New-target selection now uses
`data_selection/ranking_policies/ztf_field_ranking_v4.json`. Its production
score is the class-specific geometry ordering; `all` evaluates the union of
Aten and IEO eligibility and uses the stronger class-specific geometry score.
History is a hard eligibility rule. No absolute score threshold suppresses a
top-N result.

The promotion packet is
`data_selection/calibration/ztf_field_ranking_v4_promotion_report.json`.
Source-aligned outcome ordering:

| Mode | positives/nulls | former weighted AUC | geometry AUC | regularized three-feature LOO AUC |
|---|---:|---:|---:|---:|
| Aten | 56/21 | 0.454082 | 0.869048 | 0.812075 |
| IEO | 7/7 | 0.489796 | 1.000000 | 0.836735 |

The small independent 2024 Aten slice is 2 positives/4 nulls with AUC 1.0.
There is no 2024 IEO positive holdout. These are ordering diagnostics, not a
calibrated probability, causal yield estimate, or proof of global optimality.
They establish that v4 is the strongest currently supported simple policy and
that the more complex fitted alternative is not promoted.

Follow-up selection now uses
`data_selection/ranking_policies/hunter_follow_up_value_v1.json`:

1. open SURVIVE/BORDERLINE review obligations;
2. latest-status failed execution retries;
3. formerly insufficient-coverage retries that now have current coverage.

Success/null history without an open registry item is ineligible. Registry
priority now persists `metadata.followup_value`, not discovery priority.
Known-ground-truth behavioral controls independently verify that brighter,
shorter-arc, and lower-orbit-quality candidates increase follow-up value.

## HP-11 — exact selection/execution contract

Before a durable manifest is created, each ranked candidate now receives:

- one exact 0.01-degree IRSA metadata query over the governing replay window;
- isolation of one exposure on at least three distinct exact-position nights;
- HEAD availability checks for the difference image, science mask, science
  PSF catalog, and difference PSF on each selected night;
- content hashes, retrieval time, transformations, and validity state embedded
  in the manifest.

A candidate with broad coverage but fewer than three exact executable nights
is removed and the next ranked candidate is tested. If the current frontier is
insufficient, discovery expands again. Execution consumes the exact verified
nights stored in the manifest and refuses legacy/malformed targets lacking
that provenance.

The independent negative control
`test_exact_feasibility_replaces_a_higher_ranked_wide_only_candidate` gives
rank 1 five broad nights but only two exact nights and rank 2 three exact
nights. Rank 2 is the sole selected target. Existing adaptive-discovery
controls prove later expansion can recover a candidate outside the initial
sample.

## Real new-target workflow

Development-state installed commands:

```bash
Create-New-Search --targets 1 --mode new --neo-class all \
  --db Logs/pipeline_runs/hunter_prod_closure_20260725/hunter_state.sqlite
Run-New-Search \
  --search-id search_new_20260726T015430Z_485aeacb \
  --db Logs/pipeline_runs/hunter_prod_closure_20260725/hunter_state.sqlite \
  --candidate-ledger-db Logs/pipeline_runs/hunter_prod_closure_20260725/candidate_ledger.sqlite \
  --checkpoint-root Logs/pipeline_runs/hunter_prod_closure_20260725/checkpoints
```

Observed:

- broad pool explored: 42;
- exact selected target: `radec_310.15_-7.50`;
- exact nights: `20230922`, `20230924`, `20230927`;
- all 12 required product HEAD checks returned HTTP 200;
- three real difference images/masks/PSFs were downloaded and preprocessed;
- 369 real observations linked to one three-night tracklet;
- one adversarially reviewed candidate was durably written;
- run `run_search_new_20260726T015430Z_485aeacb_e1a538ef` completed with
  one target and zero failures;
- a second execution request failed closed with exit 1 because the manifest
  was already executed.

## Real follow-up workflow and exhaustion

The isolated state contained no open survivor registry item and no failed
execution. The sole remaining real retry was the committed
`insufficient_coverage` target at RA 211.81, Dec -7.5.

```bash
Create-New-Search --targets 1 --mode follow-up \
  --db Logs/pipeline_runs/hunter_prod_closure_20260725/hunter_state.sqlite
Run-New-Search \
  --search-id search_follow_up_20260726T015906Z_9c1743b7 \
  --db Logs/pipeline_runs/hunter_prod_closure_20260725/hunter_state.sqlite \
  --candidate-ledger-db Logs/pipeline_runs/hunter_prod_closure_20260725/candidate_ledger.sqlite
```

The current 2-degree query found 62 nights, while the complete exact 0.01-degree
window found one night. Its required difference image and difference PSF both
returned HTTP 404. Hunter therefore persisted and completed an honest 0/1
manifest: zero exact valid follow-ups existed after exhausting all current
follow-up evidence. It did not promote the prior null result from the new run
into follow-up work.

The nonzero follow-up lifecycle is covered with real SQLite transactions and
known-ground-truth records: survivor registry > failed retry > recovered
coverage; null/success without registry are excluded; acquired nights are not
reused; exact manifest provenance is mandatory; results action the originating
registry item.

## HP-12 — resource lifecycle

- removed obsolete XGBoost `use_label_encoder`;
- closed every SQLite connection in background tests while preserving
  commit/rollback behavior;
- replaced `Skills/run_tier3_pilot.py` SQLite context usage with an
  always-closing transaction context;
- production-relevant background/classifier tests pass with
  `ResourceWarning`, `FutureWarning`, and `UserWarning` promoted to errors.

No warning suppression or broad ignore was added.

## Verification commands

Focused behavioral verification:

```bash
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python -m pytest \
  tests/test_select_survey_fields.py tests/test_hunter_cli.py \
  tests/test_background.py tests/test_classify.py \
  -q -W error::ResourceWarning -W error::FutureWarning -W error::UserWarning
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python -m pytest \
  tests/test_evaluate_field_ranking_policy.py \
  tests/test_fit_field_ranking_coefficients.py -q
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 ruff check .
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 mypy src
```

Clean-commit canonical and adversarial results are appended only after the
exact committed state passes both mandatory workflows.

## Genuine scientific limitations

- v4 is the best-supported available ordering, not proof of a global optimum.
- The IEO source-aligned sample remains 7 positives/7 nulls with no positive
  2024 holdout.
- Follow-up value is deterministic and directionally verified, not calibrated
  to recovery probability.
- This validation state had zero scientifically valid nonzero follow-up
  targets; the product correctly exhausted the universe rather than fabricating
  one.
- Scientific results can validly be null or rejected. Hunter does not guarantee
  a discovery, designation, submission, or impact finding.
