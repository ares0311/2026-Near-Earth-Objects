# HB-02 Source Registry and Evidence Admission Author Assignment V1

Act as one top-level `AUTHOR_RESEARCHER_ONLY` agent. Do not create, fork,
message, delegate to, or coordinate with another agent. Do not perform
independent acceptance.

Repository root:
`/Users/Rome/Library/CloudStorage/Dropbox/Rome's Stuff/Doc.Root/Personal Docs/Astrometrics/2026 Near Earth Objects`

Controlling orchestrator checkpoint commit:
`47f2899f67ad446e4627a412bdeefa95fe937a11`

Immutable control-plane tag: `harness-builder-control-v1`

Macroscopic objective: complete the HB-02 author-side source registry and
evidence-admission map so every external factual claim needed by the accepted
95-record traceability map has exact candidate evidence before any later coding
step needs it. Internal operator decisions must be distinguished from external
claims. Do not implement the product.

Before substantive work, require the exact repository and branch, a clean
working tree, the checkpoint commit as an ancestor, successful immutable
checksum/tag checks from `AGENTS.md`, and exact HB-01 accepted-review state. The
only permitted committed post-checkpoint changes at launch are this assignment
and the orchestrator's HB-02 assignment-ready status updates.

Controlling inputs:

- `configs/harness/traceability.json`
- `configs/harness/requirements.json`
- `docs/harness/OPERATOR_OBJECTIVE.md`
- `docs/harness/SOURCE_REGISTRY.csv`
- `docs/harness/reference/accepted-specification-v3/neo003-independent-source-checks.csv`
- the exact source registers referenced by the traceability map
- `docs/harness/reviews/HB01-traceability-independent-review-v2/`

Review every one of the 95 traceability bindings and every normative factual
claim needed by its product workflows, evidence prerequisites, outputs, and
acceptance-test families. Classify each requirement/claim relationship as exactly
one of:

- `INTERNAL_NORMATIVE_DECISION_NO_EXTERNAL_CLAIM`
- `SUPPORTED_BY_ACCEPTED_CLAIM_ID`
- `NEW_AUTHOR_CANDIDATE_CLAIM`
- `OPEN_SOURCE_GAP_BLOCKER`

No binding or material external claim may remain unclassified. Existing
SC-001–SC-035 identities and independent results are reserved and must remain
semantically unchanged. Assign new stable claim IDs from SC-036 upward without
reuse or gaps.

Public primary-source research is authorized for documentation, standards,
papers, provider interfaces, access terms, licensing, and method evidence. Use
primary authoritative sources whenever available. Do not acquire scientific
payloads, execute provider data queries, create credentials, access Keychain,
accept terms, create external state, or use current/future scientific outcomes.

For every new external claim, record at minimum:

- exact claim text and stable source identity;
- primary URL or immutable local identity and retrieval date;
- source metadata and demonstrated context;
- exact support boundary and evidence grade;
- applicable requirement and workflow IDs;
- transfer limit and prohibited inference;
- canonical location that will use the claim;
- status `AUTHOR_CANDIDATE_AWAITING_INDEPENDENT_REVIEW`.

A reachable URL, abstract-level resemblance, secondary summary, or author-side
PASS is not canonical admission. Do not mark a new claim independently accepted.
If a defensible primary source cannot be found, retain an explicit
`OPEN_SOURCE_GAP_BLOCKER`; do not estimate, substitute, or invent.

Authorized outputs and edits are limited to:

- `docs/harness/SOURCE_REGISTRY.csv`
- new `configs/harness/source-claim-index.json`
- new `docs/harness/SOURCE_EVIDENCE_MAP.md`
- new `docs/harness/evidence/HB02-source-registry-author-v1.json`
- HB-02 status/location fields in `configs/harness/requirements.json`
- HB-02 status/location fields in `configs/harness/roadmap-index.json`
- the HB-02 row in `docs/harness/HARNESS_INDEX.md`
- the HB-02 sections of `docs/harness/HARNESS_STATUS.md` and
  `docs/harness/HARNESS_SPECIFICATION.md`

Do not edit the immutable control plane, accepted references, HB-01 accepted
artifacts/review, traceability bindings, assignments, schemas, or HB-03 and later
content.

Run complete author diagnostics over the full claim inventory with exactly
twelve unsafe families and twelve matched legitimate controls:

1. omitted requirement or claim relationship;
2. duplicate, reused, skipped, or unknown claim ID;
3. non-primary source presented as primary without justification;
4. URL availability substituted for claim support;
5. wrong source identity or metadata;
6. unsupported exact claim;
7. context or regime transfer overreach;
8. missing evidence grade;
9. missing or permissive transfer limit;
10. missing prohibited inference;
11. author candidate mislabeled independently accepted;
12. source/reference/status mutation or HB-03 advancement.

Record complete coverage counts, accepted-seed preservation, every new candidate
claim, every source-gap blocker, diagnostics, matched controls, and before/after
source preservation in the single HB-02 evidence JSON.

If every external claim has accepted or candidate evidence and no source-gap
blocker remains, create one local commit and stop with
`HB02_AUTHOR_COMPLETE_AWAITING_INDEPENDENT_REVIEW`. If any source gap remains,
create one local commit preserving the complete gap inventory and stop with
`HB02_AUTHOR_BLOCKED_SOURCE_GAPS_AWAITING_ORCHESTRATOR`. Do not push.

Report the terminal status, local commit, exact changed files, number of 95
bindings classified, accepted claims retained, new candidate claims, internal
decisions, source-gap blockers, twelve attack/control results, preservation, and
unresolved risks. State explicitly that no reviewer, HB-03 work, implementation,
scientific acquisition/execution, credential action, push, or additional agent
was started.
