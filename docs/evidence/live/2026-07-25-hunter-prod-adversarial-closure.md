# Hunter PROD adversarial closure

**Date**: 2026-07-25 local time (live search identifiers use UTC 2026-07-26).

**Scope**: NEO-Hunter only. This validation made no MPC/NEOCP submission,
sent no public alert, and makes no discovery or impact claim.

## Why the 2026-07-24 closure was superseded

An adversarial re-audit found nine production defects behind the earlier
feature-level closure. The durable remediation ledger is HP-01 through HP-09
in `docs/OPERATOR_GO_NO_GO_RUNBOOK.md`. The material defects were:

- executed targets were not written to governing new-target history;
- normal discovery had a fixed 200-candidate ceiling;
- partial/failed execution returned a successful process status;
- a crash window could lose ledger/follow-up effects while preserving a
  terminal checkpoint;
- follow-up selection did not derive additional work from actual run history
  and could reacquire the same nights;
- canonical review always lacked live epoch-aware known-object evidence;
- selected-input and execution provenance was incomplete;
- documented lower-level commands bypassed the durable optimizer; and
- prior live evidence used a seeded follow-up rather than real run history.

## Canonical implementation

The installed product commands are:

```bash
Create-New-Search --targets N --mode new
Create-New-Search --targets N --mode follow-up
Run-New-Search --search-id <exact-search-id>
Show-Follow-Ups
```

They delegate to one implementation in `Skills/hunter_cli.py`. The durable
state now includes exact manifests, runs, per-target run state, the follow-up
registry, and append-only stable-ID target search history. New-target
selection reserves identity transactionally. Terminal target checkpoint and
history update occur in one transaction only after idempotent candidate-ledger
and follow-up effects. Follow-up discovery uses real prior run history and
subtracts previously acquired nights.

Normal new-target discovery has no arbitrary candidate-pool cap. It expands
until N is supported or the reasonably accessible planning grid is exhausted.
An operator-provided `--max-pool` is a deliberate exploration limit and fails
loudly if it prevents sufficiency. Ranking never treats an absolute score as
an eligibility threshold.

Coverage inventories now record source, URL, source version, as-of boundary,
retrieval time, transformations, hashes, and validity state. Selection rejects
`refresh-required` and `invalid` inputs and live-refreshes a selected stale
target. Candidate records include the known-object evidence sources,
retrieval time, policy version, transformations, validity, scorer/model
versions, and exact pipeline commit plus tracked-worktree state.

## Real new-target workflow

Commands:

```bash
UV_CACHE_DIR=.uv-cache caffeinate -i uv run --no-sync --python 3.14 \
  Create-New-Search --targets 1 --mode new --neo-class all \
  --db Logs/pipeline_runs/hunter_prod_acceptance_20260725/hunter_state.sqlite

UV_CACHE_DIR=.uv-cache caffeinate -i uv run --no-sync --python 3.14 \
  Run-New-Search \
  --search-id search_new_20260726T005819Z_bbd56ba3 \
  --db Logs/pipeline_runs/hunter_prod_acceptance_20260725/hunter_state.sqlite \
  --candidate-ledger-db \
    Logs/pipeline_runs/hunter_prod_acceptance_20260725/candidate_ledger.sqlite \
  --checkpoint-root \
    Logs/pipeline_runs/hunter_prod_acceptance_20260725/checkpoints
```

Result:

- selected exact target: `radec_22.69_7.50`;
- selection score: `0.7893` (quality reported separately from rank);
- current-valid IRSA coverage: 100 distinct nights;
- explored pool: 42; sufficiency: true;
- exact run: `run_search_new_20260726T005819Z_bbd56ba3_ec02daec`;
- exact acquired nights: `20230924`, `20230925`, `20230926`;
- real observations: 333;
- deterministic candidate ID:
  `77fdaeaa-1e65-5586-a1cc-8b2ff2270560`;
- live SkyBoT epoch association: no positional match, validity `valid`;
- result: one candidate, adversarial verdict `REJECT` because four scientific
  challenges failed; candidate ledger persisted the packet and provenance;
- durable run status: `completed`, target status: `success`.

A second identical new-target request on the same database selected
`radec_15.13_7.50`, not the already selected/executed target. Its manifest is
`search_new_20260726T010023Z_b608b777`; this proves future new-target
eligibility was updated rather than relying on an operator-maintained CSV.

## Real history-derived follow-up workflow

Command:

```bash
UV_CACHE_DIR=.uv-cache caffeinate -i uv run --no-sync --python 3.14 \
  Create-New-Search --targets 1 --mode follow-up \
  --db Logs/pipeline_runs/hunter_prod_acceptance_20260725/hunter_state.sqlite

UV_CACHE_DIR=.uv-cache caffeinate -i uv run --no-sync --python 3.14 \
  Run-New-Search \
  --search-id search_follow_up_20260726T010036Z_6cf3a355 \
  --db Logs/pipeline_runs/hunter_prod_acceptance_20260725/hunter_state.sqlite \
  --candidate-ledger-db \
    Logs/pipeline_runs/hunter_prod_acceptance_20260725/candidate_ledger.sqlite \
  --checkpoint-root \
    Logs/pipeline_runs/hunter_prod_acceptance_20260725/checkpoints
```

No registry row was seeded. Durable new-search history supplied
`radec_22.69_7.50` as the highest-value follow-up with 97 current-valid nights
remaining after the first three. Exact acquired nights were `20230927`,
`20230928`, and `20231003`—none repeats a new-search night. The run loaded 248
real observations, formed no valid cross-night tracklet, and durably completed
with the scientifically honest `null_result`. Run ID:
`run_search_follow_up_20260726T010036Z_6cf3a355_8ca32df9`.

Append-only history preserves pending selection, new-search success with its
three nights, follow-up selection, and follow-up null result with its three
different nights. Restart therefore retains both identity eligibility and
remaining-work state.

## Adversarial behavioral evidence

Independent deterministic controls prove conditions that a convenient live
sample cannot:

- a higher-value candidate unavailable in the first expansion is found in the
  second expansion;
- weak absolute scores still return the best eligible N;
- an explicit pool cap that prevents N creates no manifest and exits non-zero;
- invalid/refresh-required provenance cannot drive selection;
- a crash after idempotent side effects but before the terminal checkpoint
  replays without missing or duplicate candidate/follow-up records;
- follow-up execution excludes previously acquired nights;
- installed commands all delegate to one canonical implementation;
- README and production script contracts demote lower-level diagnostics; and
- deterministic tracklet IDs make candidate-ledger upserts replay-safe.

`Skills/run_adversarial_verification.py` includes the Hunter acceptance module,
so the negative controls are part of the repository's verification-of-
verification workflow rather than an informal test list.

## Cross-project knowledge audit

The supplied computed-path read technique was verified live: Python running
inside this checkout read the sibling Techno-Hunter and EXO-Hunter
`AGENTS.md` files (67,606 and 80,728 bytes). No sibling write was attempted.
NEO-Hunter identities are minor-planet/candidate designations, disjoint from
the stellar catalog identities governed by the two sibling Hunters. No
cross-project prior-search bridge is therefore needed for correct NEO target
eligibility, and adding one would create coupling without business value.

## Verification

The final working-tree canonical reliability workflow passed all six stages
with 2,273 tests, two intentional deselections, and 100% `src/` coverage.
The adversarial workflow passed all 53 negative-control tests. The final
clean-commit and post-merge verification results are recorded in the PR
handoff and the freshness record at
`Logs/reports/reliability_verification.json`; a `VERIFIED` claim is valid only
when that record matches the current clean `HEAD`.

## Genuine limitations

- The ranking policy is deterministic and explainable; coefficient
  calibration remains a scientific refinement, not a missing product stage.
- Wide-box coverage does not guarantee every nominal point resolves inside
  the executor's narrow single-exposure box. This is surfaced as a target
  failure, never hidden as success.
- The real follow-up produced no candidate. That is a valid durable null
  result, not evidence of a discovery.
- External submission and hazard notification remain separately gated.
