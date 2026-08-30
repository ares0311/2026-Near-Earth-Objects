# HB-01 Traceability Fresh Independent Review Assignment V2

Act as one fresh top-level `INDEPENDENT_REVIEWER_ONLY` agent. Do not create,
fork, message, delegate to, or coordinate with another agent. Do not repair the
target or begin HB-02.

Repository root:
`/Users/Rome/Library/CloudStorage/Dropbox/Rome's Stuff/Doc.Root/Personal Docs/Astrometrics/2026 Near Earth Objects`

Exact author target commit:
`edd72a5599671b58c6abd29cd4fbbad6965a2619`

Canonical commit-object SHA-256:
`de3e720b606781f28578d7b051a324f9e92287e258d0250d4570cfd437bae9a3`

Author assignment:
`docs/harness/assignments/HB01_TRACEABILITY_AUTHOR_RECONSTRUCTION.md`

Author-assignment SHA-256:
`a637ec5c6f69950978b1110adde1a0b5d28bdfe8667a208219bcba1b4464686d`

Immutable control-plane tag: `harness-builder-control-v1`

Fresh exclusive review root:
`docs/harness/reviews/HB01-traceability-independent-review-v2`

Before reading substantive target content, require the exact repository and
branch, a clean working tree, the author target as an ancestor, and successful
immutable checksum/tag checks from `AGENTS.md`. Require the review root to be
absent. The only permitted committed difference after the author target at
launch is this reviewer assignment. Verify these target files byte-for-byte
against the author commit:

- `configs/harness/traceability.json`
- `configs/harness/requirements.json`
- `configs/harness/roadmap-index.json`
- `docs/harness/REQUIREMENT_TRACEABILITY.md`
- `docs/harness/HARNESS_INDEX.md`
- `docs/harness/HARNESS_SPECIFICATION.md`
- `docs/harness/HARNESS_STATUS.md`
- `docs/harness/evidence/HB01-traceability-author-v1.json`

Treat all author prose, diagnostics, counts, hashes, and PASS claims as
untrusted. Independently recompute strict JSON parsing, exact one-time coverage
of OPR-001–015, REQ-001–048, IR-001–016, and OQ-01–16, and exact agreement with
the four controlling source registers. Verify source profiles, materialized
dependencies including ranges, existing canonical outputs, acceptance-test
references, evidence-before-use behavior, status reconciliation, HB-02
preservation, and immutable/reference preservation.

Review every binding substantively against `OPERATOR_OBJECTIVE.md` and the exact
source row. Each binding must have a defensible NeoHunter product workflow;
scientific workflows must remain subordinate. Empty evidence must fail closed.
Do not accept a structurally valid but product-irrelevant or semantically wrong
mapping.

Run exactly twelve fresh unsafe attack families and twelve matched legitimate
controls using disposable copies or in-memory objects:

1. omitted ID;
2. duplicated, aliased, or unknown ID;
3. wrong source profile or controlling fields;
4. wrong NeoHunter product workflow;
5. standalone scientific workflow or domain promoted to roadmap phase;
6. missing required dependency;
7. added unsupported dependency or invented evidence;
8. empty evidence interpreted permissively;
9. missing or unknown output set;
10. missing or unknown acceptance-test family;
11. status drift, false closure, or HB-02 advancement;
12. immutable-control or accepted-reference mutation.

Each unsafe case must be rejected for its intended family and each matched valid
case accepted. A shared baseline defect is one reviewer-harness failure, not
multiple target defects. The reviewer may correct its own unsealed test harness
and rerun the complete suite, but may never modify the target.

Write exactly these five files under the fresh review root:

- `review-report.md`
- `machine-results.json`
- `attack-control-results.json`
- `target-preservation.json`
- `VERDICT.txt`

Issue exactly one verdict:

- `HB01_TRACEABILITY_ACCEPTED_AFTER_INDEPENDENT_REVIEW`
- `REVISIONS_REQUIRED`

Acceptance is limited to HB-01 objective-to-requirement traceability. It closes
no OPR, REQ, IR, or OQ content; does not complete the harness; and does not
authorize HB-02, implementation, acquisition, execution, submission, authority
contact, or scientific claims. Do not commit or push. Stop after reporting the
verdict, exact review root, tested scope, attacks and controls, preservation,
findings, and unresolved risks. State that no downstream task or agent started.
