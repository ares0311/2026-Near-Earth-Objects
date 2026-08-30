# HB-01 Traceability Independent Review Assignment

Status: `VOID_ROLE_BOUNDARY_VIOLATION`

Do not execute this assignment. The target was constructed by the orchestrator
instead of a separate author agent and is not review-eligible. It is retained only
as audit evidence. A replacement reviewer assignment may be issued only after a
separate author returns a valid HB-01 author handoff.

Act as one fresh top-level independent reviewer. Do not create, fork, message, or
delegate to another agent. Do not repair the target or begin HB-02.

Repository root:
`/Users/Rome/Library/CloudStorage/Dropbox/Rome's Stuff/Doc.Root/Personal Docs/Astrometrics/2026 Near Earth Objects`

Exact author target commit:
`0f7a4b79fd79e980adfc6da05bb6ba6a43b749ae`

Immutable control-plane tag: `harness-builder-control-v1`

Fresh exclusive review root:
`docs/harness/reviews/HB01-traceability-independent-review-v1`

Before reviewing, require the exact repository root, verify the immutable checksum
file and tag comparison prescribed by `AGENTS.md`, require the review root to be
absent, and verify that every target file below is identical to the target commit:

- `configs/harness/requirements.json`
- `configs/harness/roadmap-index.json`
- `configs/harness/traceability.json`
- `docs/harness/HARNESS_INDEX.md`
- `docs/harness/HARNESS_SPECIFICATION.md`
- `docs/harness/HARNESS_STATUS.md`
- `docs/harness/REQUIREMENT_TRACEABILITY.md`

Treat author validation as untrusted. Independently verify strict JSON parsing;
exact one-time coverage of OPR-001–015, REQ-001–048, IR-001–016, and OQ-01–16;
agreement with the four controlling source registers; valid workflow, output-set,
evidence, and test references; existing canonical paths; machine/prose/status
reconciliation; and the substantive correctness of every binding.

Test the complete scope with fresh unsafe mutations and matched legitimate
controls. At minimum cover omitted, duplicate, unknown, and misclassified IDs;
wrong product-workflow bindings; missing evidence dependencies; missing or wrong
canonical outputs; missing acceptance-test families; promotion of a scientific
domain into a harness phase; treating empty evidence as permission to invent;
status/index drift; and immutable-control mutation. A global baseline defect must
not be counted as multiple target failures.

Write exactly these five files under the fresh review root:

- `review-report.md`
- `machine-results.json`
- `attack-control-results.json`
- `target-preservation.json`
- `VERDICT.txt`

Issue exactly one verdict:

- `HB01_TRACEABILITY_ACCEPTED_AFTER_INDEPENDENT_REVIEW`
- `REVISIONS_REQUIRED`

Acceptance is limited to objective-to-requirement traceability. It does not close
any OQ or IR, complete the harness, authorize HB-02, implementation, acquisition,
execution, submission, authority contact, or scientific claims. Stop after the
review output and do not modify or commit the target.
