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
wheel is an explicit negative control. Release CI now invokes this verifier on
the artifact it builds.

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

Clean implementation commit
`fd9897509d2fe2c65f1b3f0e97be5489a20415ce` produced:

```text
directive parity: PASS
silent-exception gate: PASS
incomplete-implementation gate: PASS
ruff: PASS
mypy src: PASS
pytest: 2,334 passed, 2 deselected
src coverage: 5,993/5,993 statements, 100.00%
adversarial verification: 85 passed
isolated wheel contents/install/launch/state isolation: PASS
repository unchanged by adversarial run: PASS
freshness: CURRENT AND VERIFIED
```

The REL-05 record identifies that exact commit, a clean working tree, and UTC
check time `2026-07-29T05:58:26.805228+00:00`.

Hosted CI and clean post-merge verification remain the final HP-20 evidence
boundary. Until both pass, this record proves local implementation and
verification but does not restore a merged-current-main PROD claim.

## Genuine limitations and separate gates

- Broader ZTF DR24 scientific-capability gate M8 remains separate and open
  until its own evidence closes it.
- This remediation did not repeat the earlier live exact-manifest science run;
  it repaired and independently tested the software/artifact defects exposed
  after that run.
- A search may validly produce no surviving scientific candidate.
- External submission and authority-facing communications remain human-gated.
- No internally computed result is an impact-probability claim.
