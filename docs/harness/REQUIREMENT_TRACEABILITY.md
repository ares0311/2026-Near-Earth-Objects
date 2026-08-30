# NEO Harness Requirement Traceability

Status: `HB01_TRACEABILITY_ACCEPTED_AFTER_INDEPENDENT_REVIEW`

The machine authority for this mapping is `configs/harness/traceability.json`.
This document is the author interpretation of the independently reconstructed
HB-01 map. It connects the governing source records to the requested NeoHunter
product without turning scientific domains into roadmap phases or implementation
authority.

## Author reconstruction basis

The author reconstructed every binding from these controlling sources rather
than accepting the orchestrator draft:

- `docs/harness/OPERATOR_OBJECTIVE.md`;
- the operator requirement records in `configs/harness/requirements.json`;
- `reference/accepted-specification-v3/requirements-register.csv`;
- `reference/accepted-specification-v3/incomplete-requirements.csv`;
- `reference/accepted-specification-v3/unresolved-dependencies.csv`.

The source profile on every machine binding resolves to a source path, record-ID
field, and exact controlling fields. Normative text remains in the source record
and is not weakened by a summary here.

## Coverage

The author map contains exactly 95 individually addressable bindings:

- 15 operator product requirements, `OPR-001` through `OPR-015`;
- 48 accepted specification requirements, `REQ-001` through `REQ-048`;
- 16 incomplete evidence requirements, `IR-001` through `IR-016`;
- 16 open dependencies, `OQ-01` through `OQ-16`.

There are no omissions, duplicates, unknown IDs, or grouped accepted-requirement
shortcuts. Every record maps to at least one product workflow, one or more
canonical output sets, exact prerequisite IDs or controlling source-register
fields, and one or more acceptance-test families.

## Product and scientific workflow rule

Product workflows cover the Spec Prompt/control plane, NeoHunter shell,
`/New Search`, `/Review Search Logs`, `/Follow-On Search`, `/Exit`, data intake,
persistence, operations, bounded evaluation, detection disposition, and Codex
CLI handoff.

Point-source detection, trail detection, association, tracklet formation,
multi-night/cross-survey linking, historical recovery/precovery, and initial
orbit uncertainty are stored separately as subordinate scientific workflows.
Every binding has a product workflow; a scientific workflow can never stand
alone, become an HB roadmap phase, or authorize implementation or execution.

## Evidence-before-use rule

Every listed prerequisite ID must be canonical, present, and independently
validated before the affected future work begins. Each `REQ` and `IR` binding
materializes the exact dependency IDs in its source row. Each `OQ` binding names
the exact closure-evidence, blocking-scope, and specification-disposition fields
that govern closure.

An empty prerequisite-ID array is fail-closed: it means the named source fields
and a complete canonical specification govern the decision. It never means a
later coding agent may research, infer, choose, or invent the missing content.

## Acceptance-test families

The map assigns requirement-family contracts for control, product behavior,
data interfaces, methods, labels, metrics, operations, disposition, independent
review, handoff, and traceability. HB-01 maps these families; it does not claim
that HB-02 or later work has instantiated or passed their final attacks.

Author diagnostics rejected ten unsafe mapping mutations—omission, duplicate,
unknown ID, wrong product workflow, missing evidence dependency, missing output,
missing test, scientific-domain promotion, empty-evidence invention, and status
drift—while accepting the unmodified candidate as the matched legitimate control
for every family. Exact results are in
`evidence/HB01-traceability-author-v1.json`.

## Differences from the orchestrator draft

The author retained the draft only as a comparison target. The reconstructed map:

- expands 16 accepted-requirement groups into 48 individual bindings;
- separates product workflows from subordinate scientific workflows;
- adds exact source-record identity and controlling fields to every binding;
- materializes all source dependency IDs and makes empty evidence fail closed;
- changes 78 workflow bindings, 16 output-set bindings, and 2 acceptance-test
  bindings relative to the draft.

The exact changed-ID lists are recorded in the author evidence JSON.

## Author conclusion

The source registers support an unambiguous HB-01 mapping. Fresh role-separated
review at `reviews/HB01-traceability-independent-review-v2/` accepted the exact
author commit after complete 95-record review and 12 attack/control pairs. HB-01
is complete. This acceptance does not close any open operator requirement,
incomplete requirement, or dependency; HB-02 remains the next separate work
package.
