# NEO Harness Requirement Traceability

Status: `ORCHESTRATOR_DRAFT_NOT_REVIEW_ELIGIBLE`

The machine authority for this mapping is `configs/harness/traceability.json`.
This document explains how it keeps the harness connected to the requested
NeoHunter product without turning the seven scientific domains into a substitute
roadmap.

## Coverage

The traceability map covers exactly:

- 15 operator product requirements, `OPR-001` through `OPR-015`;
- 48 accepted specification requirements, `REQ-001` through `REQ-048`;
- 16 incomplete evidence requirements, `IR-001` through `IR-016`;
- 16 open dependencies, `OQ-01` through `OQ-16`.

Every record resolves to one or more stable product or scientific workflow IDs,
canonical output sets, prerequisite evidence, and acceptance-test families. The
original normative text and exact dependency/closure fields remain in their
source registers; the traceability file binds rather than paraphrases them.

## Product workflows

The controlling workflows are the Spec Prompt/control plane; NeoHunter shell;
New Search; Review Search Logs; Follow-On Search; Exit; data intake; persistence;
operations; bounded evaluation; detection disposition; and Codex CLI handoff.

Point-source detection, trail detection, association, tracklet formation,
multi-night/cross-survey linking, historical recovery/precovery, and initial
orbit uncertainty are subordinate scientific workflows. They enter the harness
only through an operator-facing search, follow-on, evaluation, or disposition
workflow and only with their evidence prerequisites satisfied.

## Evidence-before-use rule

An implementation step may use a requirement only after every evidence ID in its
binding and source register is independently validated and present in the
canonical repository. Missing evidence blocks the affected workflow before the
coding agent begins it. Empty evidence arrays mean that the requirement is a
product or control decision still requiring canonical specification, not that a
coding agent may invent the decision.

## Acceptance-test families

The machine map defines tests for control, product behavior, data interfaces,
methods, labels, metrics, operations, disposition, independent review, handoff,
and traceability completeness. These are requirement-family contracts. Later
work packages must instantiate exact attacks and matched legitimate controls;
HB-01 does not claim those downstream tests are complete.

## Current conclusion

The objective-to-requirement connection is present only as an orchestrator draft.
It has not been independently reconstructed or adopted by an author agent, so it
must not proceed to review. HB-01 remains active until a separate author verifies
every governing source ID, workflow, output set, evidence prerequisite, and test
family and returns an author-only handoff. HB-02 and all later work packages
remain unstarted.
