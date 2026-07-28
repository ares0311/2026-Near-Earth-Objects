# Hunter PROD configurable-concurrency closure

**Date**: 2026-07-27 local time.

**Scope**: NEO-Hunter only. No MPC/NEOCP submission, public alert, discovery
claim, impact claim, or new live field acquisition was made.

## Blocking finding

The HP-01 through HP-13 implementation was scientifically and transactionally
complete, but `Run-New-Search` still executed every independent manifest target
serially. It exposed no worker configuration and had no behavioral concurrency
control. That contradicted the Hunter PROD directive's explicit requirements
for configurable parallel execution and concurrency testing.

## Production contract

`Run-New-Search` and `/Run-Search` now accept `--workers 1..3`, defaulting to
three. The ceiling comes from `docs/SYSTEM_PROFILE.md`: three concurrent IRSA
ZTF DR24 pixel-product downloads is the documented conservative starting point,
and it must not be raised until a clean stable-connection probe establishes a
higher safe level.

Concurrency is deliberately limited to target-local work:

- each target owns a disjoint checkpoint directory;
- target acquisition, conversion, linking, classification, orbit fitting,
  scoring, and adversarial review may overlap;
- candidate-ledger, follow-up-registry, target-history, and run-state writes
  remain serialized on the main thread;
- durable writes occur in manifest rank order regardless of worker completion
  order;
- the execution contract records scheduler version, configured workers,
  service ceiling, and durable commit order in the search run and every target
  result;
- a resumed run must use its original worker contract;
- a legacy resumable run receives the execution contract before work resumes;
  and
- `--workers 0` or a value above three fails before creating or mutating run
  state.

The scheduler remains deterministic: parallelism changes wall-clock overlap,
not target identity, selected nights, scoring, interpretations, or durable
ordering.

## Independent behavioral evidence

`test_run_search_executes_targets_concurrently_but_commits_in_manifest_order`
uses three isolated targets and a synchronization barrier. The test fails if
the executor is serial. It observed three simultaneous target executions, then
independently asserted that `hunter_run_execution` history was committed in
manifest rank order and that every target carried the three-worker contract.

Additional controls prove:

- out-of-range worker counts fail loudly;
- a resume with a different worker contract fails loudly;
- legacy run model-version provenance is upgraded without discarding prior
  values;
- the parser defaults to three and accepts an explicit serial value; and
- all pre-existing crash/restart, partial-run, idempotence, exact-manifest,
  follow-up, and installed-shell controls continue to pass.

## Verification

Focused implementation-state verification:

```text
ruff: PASS
mypy src: PASS
Hunter/state/shell/acceptance tests: 152 passed
```

Clean implementation commit
`cd41bf47a3ce66e1881203350eb8c810bff2bf7a`:

```text
directive parity: PASS
silent-exception gate: PASS
incomplete-implementation gate: PASS
ruff: PASS
mypy src: PASS
pytest: 2,314 passed, 2 deselected, 100.00% src coverage
adversarial verification: 81 passed
freshness: CURRENT AND VERIFIED
```

The clean verification used an isolated same-repository checkout of the exact
commit so the operator's unrelated `.codex/config.toml` working-tree change
could not contaminate REL-05 freshness. Hosted CI and clean post-merge
verification remain required before the branch is represented as merged
current `main`.

## Genuine limitations

- Three is a conservative service-protection limit, not a measured throughput
  optimum.
- A one-target manifest correctly uses one active worker.
- Scientific output may still be null or rejected.
- External submission and authority-facing communications remain separately
  gated.
