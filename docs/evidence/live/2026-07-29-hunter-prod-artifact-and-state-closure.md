# Hunter PROD artifact and state closure

**Date**: 2026-07-29 local time.

**Scope**: NEO-Hunter software, distribution, persistence, and operator
contract. No new live acquisition, MPC/NEOCP submission, public alert,
discovery claim, or impact claim was made.

## Adversarial result

The 2026-07-29 re-audit disproved the prior PROD claim with six blocking
findings, recorded as HP-15 through HP-20 in
`docs/OPERATOR_GO_NO_GO_RUNBOOK.md`:

- an exhausted `0/N` selection could become a successful empty run;
- the release wheel contained metadata but no runnable application;
- the planning universe was neither a distinct durable catalog nor
  10,000-plus at supported scale;
- manifest and follow-up displays omitted required operator fields;
- installed state paths and structured operational logging were undefined;
  and
- the acceptance boundary did not test an isolated installed artifact.

Implementation commit `fd9897509d2fe2c65f1b3f0e97be5489a20415ce`
closes the local software defects.

## HP-15 — exact lifecycle invariant

Manifest creation now requires
`requested_n == actual_n_selected > 0` and `sufficiency_met=true`. Natural
universe exhaustion and an explicit operator pool cap both fail nonzero
without creating a pending manifest. Execution independently validates the
stored manifest before creating a run, so empty, short, overfull, non-positive,
or falsely sufficient legacy rows cannot exploit zero-target completion
semantics. Behavioral controls assert that rejected manifests do not mutate
run state.

## HP-16 — installable standalone artifact

Version 0.91.1 explicitly packages the runtime modules, the canonical
`Skills` orchestration modules, ranking and coverage inputs, production model
artifacts, and the cited immutable evidence resource. Mutable state is resolved
separately from package resources.

`Skills/verify_hunter_distribution.py` builds the wheel, inspects its contents,
installs it into an isolated Python 3.14 environment with no checkout on
`sys.path`, and exercises:

```text
NEOHunter --command /Help
NEO-Hunter --command /Help
Create-New-Search --help
Run-New-Search --help
Show-Follow-Ups --help
```

It also runs an installed state operation and proves that only the configured
state root receives the SQLite database and JSONL event log. A metadata-only
wheel is an explicit negative control. Pull-request/main CI and release CI now
invoke this verifier on the artifact each workflow builds.

## HP-17 — durable planning catalog and scale

Hunter schema v3 adds `target_catalog`, distinct from the post-detection
candidate ledger. Its version-preserving key is
`(catalog_version, target_id)`. Records retain stable survey/canonical
identity, target kind, coordinates, NEO class, ranking value, resource
estimates, scientific metrics, and source provenance.

At controlled epoch JD 2461000.5, the supported `all` mode materializes
30,096 viable one-degree planning targets and ranks a request for 100 from
that universe. Exact feasibility remains a separate mandatory gate: a large
planning universe does not authorize an unexecutable manifest.

## HP-18 — complete operator records

Durable manifest targets and their grid/CSV representations now include
mode, stable survey and canonical identifiers, target kind, prior-search count
and provenance, ranking score and reason, honest distance applicability,
storage/compute estimates, and domain scientific metrics. The grid-versus-CSV
boundary uses requested N, so exhaustion cannot silently change the requested
operator behavior.

Follow-up output includes the originating run, evidence reference, prior
history, reason, priority, required data, recommended action, and resource
estimates. Solar-system sky fields record distance as not applicable rather
than inventing a light-year value.

Storage is a measured-product planning estimate derived from the cited
three-product live preflight. Exact selected targets replace it with the sum
of HEAD-confirmed product byte counts. The 180-second compute value remains an
explicit uncalibrated transparent operator prior and is not used for ranking.

## HP-19 — installed configuration and structured events

Immutable resources resolve from the checkout in development and the
installation prefix in a built artifact. Mutable state uses the operating
system application-data location and supports the documented
`NEOHUNTER_HOME`, `NEOHUNTER_RESOURCE_ROOT`, and `NEOHUNTER_MODEL_ROOT`
overrides.

The append-only JSONL event stream covers command failure, search creation,
run start/final state, every target outcome, and follow-up display. Open and
short-write failures are visible mandatory failures. Tests prove state-root
isolation and that no secret-bearing configuration is written to events.

## HP-20 — verification boundary

Clean hosted-boundary commit
`7b8bb59e6f3855eae2fce43e69b0ff5065a448a2` produced:

```text
directive parity: PASS
silent-exception gate: PASS
incomplete-implementation gate: PASS
ruff: PASS
mypy src: PASS
pytest: 2,335 passed, 2 deselected
src coverage: 5,993/5,993 statements, 100.00%
adversarial verification: 85 passed
isolated wheel contents/install/launch/state isolation: PASS
repository unchanged by adversarial run: PASS
freshness: CURRENT AND VERIFIED
```

The REL-05 record identifies that exact commit, a clean working tree, and UTC
check time `2026-07-29T06:23:16.481410+00:00`.

PR CI run `30428208537` passed both `lint-and-test (3.14)` and the new
`hunter-distribution` job on its successful attempt. The first test attempt
reached 99%, lost two xdist workers without an assertion failure, and hit the
15-minute job limit; the unchanged failed-job rerun passed in 2 minutes
8 seconds. E2E run `30428208539` passed all six independent pipeline, model,
recovery, and alert controls.

PR #284 merged as `c73455c64c1474d6c270569bafe45779126626b9`.
Clean merged `main` then repeated:

```text
directive parity: PASS
silent-exception gate: PASS
incomplete-implementation gate: PASS
ruff: PASS
mypy src: PASS
pytest: 2,335 passed, 2 deselected
src coverage: 5,993/5,993 statements, 100.00%
adversarial verification: 85 passed
isolated wheel contents/install/launch/state isolation: PASS
repository unchanged by adversarial run: PASS
freshness: CURRENT AND VERIFIED
```

The post-merge REL-05 record identifies clean commit `c73455c6` and UTC check
time `2026-07-29T06:48:54.686871+00:00`. HP-15 through HP-20 are closed.

## HP-21 — hosted test-process stability

The successful retry cited above was not sufficient evidence of stable hosted
acceptance. After PR #285 merged, main CI run `30430070885` independently
reproduced the same failure class: the suite reached 99%, reported
`gw2 node down: Not properly terminated`, and remained alive until GitHub
cancelled it at the 15-minute job limit. The earlier failed attempt in run
`30428208537` had likewise reached 99%, lost xdist workers, and timed out
before its unchanged rerun passed.

This is a blocking acceptance defect even though the exact repository tree
passes the serial canonical verifier. A production claim cannot depend on
rerunning an unstable gate until it happens to pass.

The CI workflow replaces runner-dependent `-n auto` with two explicit
`loadfile` workers and caps OpenMP, MKL, and OpenBLAS to one native thread per
worker. A workflow contract test rejects a return to automatic worker sizing
or removal of the thread caps. Two consecutive hosted full-suite passes on the
same pull-request tree, followed by a full-suite pass on merged `main`, are
required before HP-21 and the Hunter PROD claim may be closed.

Implementation commit `1eced6f427a001aa2957d3fd96295de59086bda0`
produced the following clean local evidence:

```text
exact two-worker CI-shaped suite: 2,336 passed, 100% src coverage
canonical reliability stages: 6/6 PASS
canonical pytest: 2,336 passed, 2 deselected
canonical src coverage: 5,993/5,993 statements, 100.00%
adversarial verification: 85 passed
isolated wheel contents/install/launch/state isolation: PASS
repository unchanged by adversarial run: PASS
freshness: CURRENT AND VERIFIED
```

The clean PR commit then passed hosted CI run `30439389527` twice without a
tree change:

- attempt 1: `success`, full suite 2 minutes 46 seconds;
- attempt 2: `success`, full suite 2 minutes 42 seconds.

PR #286 merged that exact implementation as clean `main` commit
`759b4f9664878987f13116138638982ff9678f87`. Main CI run `30440700068`
passed the full suite in 2 minutes 41 seconds and the isolated distribution
job in 4 minutes 3 seconds. Main Integration run `30440699904` and all six
E2E jobs in run `30440699893` also passed. No accepted run reported worker
loss or reached the job timeout.

**Current status**: VERIFIED. HP-21 is closed, and HP-15 through HP-21 now
satisfy the NEO-Hunter software PROD threshold subject to the genuine separate
scientific and authority limitations below.

## HP-22 — honest hosted integration boundary

Final documentation-bearing main commit `8cdff05d` passed CI run
`30441323215`, all six E2E jobs in `30441323151`, the clean local canonical
verifier, REL-05 freshness, all 85 adversarial controls, and isolated wheel
validation. Its separate Integration run `30441323193` then exposed another
acceptance-infrastructure defect: a workflow documented to skip all hosted
live tests still performed checkout, Python/uv setup, and a full dependency
sync before printing the policy notice. The run spent more than ten minutes in
those irrelevant setup/network operations, while the job had no explicit
timeout.

The hosted boundary now does exactly what it claims. It contains one notice
step, performs no checkout/interpreter/dependency operation, and has a
two-minute job timeout. The operator-Mac live-test command remains unchanged
and credential-gated. A workflow contract test rejects reintroducing setup or
dependency installation into the skip-only job.

PR #288 passed full CI run `30442352193` and all six E2E jobs in
`30442353757`. It merged as clean `main` commit
`fc46c0c8559fbbb8fe7ad427b4d30b9a49286e09`. Main Integration run
`30442543264` completed successfully in three seconds: set up job, emit the
policy notice, complete job. Main CI `30442543025` and all six E2E jobs in
`30442543061` also passed.

**Current status**: VERIFIED. HP-22 is closed. HP-15 through HP-22 satisfy the
NEO-Hunter software PROD threshold subject to the genuine separate scientific
and authority limitations below.

## Genuine limitations and separate gates

- Broader ZTF DR24 scientific-capability gate M8 remains separate and open
  until its own evidence closes it.
- This remediation did not repeat the earlier live exact-manifest science run;
  it repaired and independently tested the software/artifact defects exposed
  after that run.
- A search may validly produce no surviving scientific candidate.
- External submission and authority-facing communications remain human-gated.
- No internally computed result is an impact-probability claim.
