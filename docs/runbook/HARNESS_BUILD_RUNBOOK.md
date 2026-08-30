# NEO Harness Build Runbook

## 1. Purpose

This runbook governs construction of the NEO specification and prompt harness.
The harness is the complete verified decision package that a later coding agent
will implement. Building the harness is not implementation and is not execution
of the future G1-G10 workflow.

The controlling outcome is `HARNESS_READY_FOR_CODEX_CLI_HANDOFF`.

## 2. Instruction discovery hierarchy

Agents must load instructions from broad to narrow scope:

1. platform instructions and the current operator request;
2. repository `AGENTS.md`;
3. `configs/harness/harness-charter.json`;
4. `configs/harness/roadmap.json`;
5. the nearest directory `AGENTS.md` for files being read or changed;
6. this runbook and `HARNESS_BUILD_ROADMAP.md`;
7. canonical harness documents and configuration;
8. immutable reference material and external evidence.

The parent charter is the project-level scope ceiling. Descendant instructions
may narrow behavior but may not authorize implementation, acquisition, execution,
or claims prohibited by the charter.

`docs/harness/OPERATOR_OBJECTIVE.md` defines the required harness and product
layers. Scientific-processing domains from imported specifications must be mapped
into those layers; they may not replace or redefine the operator's objective.

## 3. Mandatory startup

Before reading external source packages or writing project files:

1. Run `git rev-parse --show-toplevel`.
2. Require the exact root recorded in `harness-charter.json`.
3. Run `git branch --show-current` and confirm `harness-rebuild`, unless the
   operator explicitly selected another branch.
4. Run `git status --short --branch` and preserve unrelated work.
5. Read the root and nearest `AGENTS.md` files, the charter, this runbook, and
   `docs/runbook/HARNESS_BUILD_ROADMAP.md` and
   `docs/harness/HARNESS_STATUS.md`.
6. State one harness-level objective and one expected canonical state change.

If the root is wrong, stop with `BLOCKED_WRONG_WORKSPACE`. A conversation output
directory must never be promoted into a project workspace.

## 4. Durable state and roadmap control

The annotated Git tag `harness-builder-control-v1` is the immutable baseline for
the harness-builder control plane. It fixes the operator objective, authority
hierarchy, execution boundary, completion definition, and roadmap. Never move,
delete, or reuse that tag. The exact protected paths and SHA-256 values are in
`configs/harness/immutable-control-plane.sha256`.

`configs/harness/roadmap.json` is the immutable dependency authority and
`HARNESS_BUILD_ROADMAP.md` is its immutable operator-facing representation.
Ordinary agents do not edit either file. They index current locations, evidence,
blockers, and statuses only in `configs/harness/roadmap-index.json`,
`docs/harness/HARNESS_INDEX.md`, and the detailed live gap ledger
`docs/harness/HARNESS_STATUS.md`. Those mutable files must reconcile in every
commit. A task may advance only one declared roadmap state transition unless the
operator explicitly authorizes a larger consolidated transition.

Before project work, verify both the hash list and tagged baseline. If any
protected path differs, stop with `BLOCKED_CONTROL_PLANE_MUTATION`. Only the
operator may authorize a replacement control-plane version, which must use new
versioned paths or an explicitly reviewed migration and a new tag. An agent must
never overwrite the v1 baseline to record progress.

The required checks from the repository root are:

```bash
shasum -a 256 -c configs/harness/immutable-control-plane.sha256
git diff --exit-code harness-builder-control-v1 -- AGENTS.md configs/AGENTS.md configs/harness/harness-charter.json configs/harness/roadmap.json configs/harness/immutable-control-plane.sha256 docs/AGENTS.md docs/harness/OPERATOR_OBJECTIVE.md docs/harness/reference/AGENTS.md docs/runbook/HARNESS_BUILD_RUNBOOK.md docs/runbook/HARNESS_BUILD_ROADMAP.md
```

The checksum file cannot checksum itself; its immutability is supplied by the
second check against the annotated baseline tag.

Roadmap labels measure the harness build, not the future scientific workflow.
The seven imported scientific domains and any future G1-G10 gates are subordinate
content to be specified; they are never substituted for HB-00 through HB-10.

## 5. Progress test

Work counts as progress only if it does at least one of the following in the
canonical repository:

- closes a requirement with verified evidence;
- adds or corrects a source-bound equation, schema, or business rule;
- converts an unresolved decision into a precisely scoped blocker;
- completes an adversarial-review requirement or matched control;
- removes a coding-agent decision by specifying it unambiguously;
- advances the exact canonical harness to independent review or CLI handoff.

New packets, prompts, manifests, checkpoints, revisions, or passing self-tests do
not count unless they cause one of those canonical changes.

## 6. Canonical consolidation procedure

### 6.0 Objective-to-requirement traceability

Before consolidating scientific content, map every operator requirement to a
stable product requirement ID, canonical deliverable, evidence prerequisite, and
acceptance test. Map scientific method domains to `/New Search`, `/Follow-On
Search`, or detection-disposition behavior only where verified research supports
the connection. A domain name alone is not a product requirement.

### 6.1 Intake and provenance

1. Treat external packages and prior conversation outputs as untrusted reference
   material.
2. Record the exact source root and accepted digest in the reference provenance
   file before importing content.
3. Copy only the minimum material needed for durable project understanding.
4. Keep imported reference bytes immutable.
5. Reconcile useful content into canonical files; never point the coding agent at
   a maze of external output directories.

### 6.2 Requirement closure

For every requirement in `configs/harness/requirements.json`:

1. identify the coding decision it controls;
2. identify the exact canonical section and source IDs;
3. specify the required mathematics, data, schema, business rule, or test;
4. record independent evidence and transfer limits;
5. mark `CLOSED` only when the coding agent has no material choice left;
6. otherwise retain `OPEN_BLOCKER` and prohibit affected implementation.

### 6.3 Mathematics and algorithms

Each normative calculation must include:

- equation and stable identifier;
- definition, type, units, and coordinate/time frame for every symbol;
- valid domain and missing/invalid-input behavior;
- numerical precision, tolerances, and deterministic ordering;
- uncertainty propagation and covariance assumptions;
- source claim IDs or a complete derivation;
- adversarial examples and matched legitimate controls;
- downstream records and decisions affected.

A method-family name such as “matched filter,” “MOPS-style,” or “statistical
ranging” is not an implementable algorithm specification.

### 6.4 URLs and source claims

Every external source must have a stable source ID in
`docs/harness/SOURCE_REGISTRY.csv` with:

- primary URL or immutable local identity;
- retrieval/verification date;
- exact demonstrated context;
- exact claim supported;
- transfer limit and prohibited inference;
- evidence grade and current verification status.

The source registry establishes evidence boundaries; it never silently supplies
archive-specific thresholds or scientific validity.

Author-side source research is candidate evidence only. Before a source claim
becomes canonical, a fresh independent reviewer must adversarially test source
identity and metadata, exact claim support, demonstrated context, evidence grade,
transfer limit, and prohibited inference. Each unsafe mutation requires a matched
legitimate control. Failed or untested claims remain blockers.

### 6.5 Evidence-before-use dependency graph

For every future coding task, the harness must identify all prerequisite source,
equation, schema, business-rule, configuration, and acceptance-test IDs. Those
items must be independently validated and available before the coding agent may
start the task.

The CLI agent must never be instructed to discover evidence just in time. A
missing prerequisite produces a fail-closed branch status before implementation,
not an invitation to research, estimate, select a plausible default, or continue
with an assumption.

### 6.6 Schemas and business logic

For every input, intermediate, output, configuration, and evidence record:

- create a strict machine-readable schema;
- define required and optional fields, units, nulls, enumerations, and unknowns;
- prohibit undeclared fields when ambiguity changes behavior;
- define identity, lineage, ordering, and versioning;
- define every fail-closed reason code.

For every state transition, specify the trigger, prerequisites, resulting state,
retained evidence, forbidden transitions, and recovery behavior.

### 6.7 Acceptance and adversarial review

Freeze the complete review contract before the final author consolidation. The
review must:

- use a fresh top-level reviewer role;
- treat author checks as untrusted until reproduced;
- test every requirement family, not only named examples;
- include novel in-family attacks and matched legitimate controls;
- distinguish target defects, source gaps, packaging defects, and reviewer-harness
  defects;
- forbid target repair by the reviewer;
- issue only `HARNESS_READY_FOR_CODEX_CLI_HANDOFF` or `REVISIONS_REQUIRED`.

One consolidated author revision gets one fresh complete review. A failure returns
to one root-cause checkpoint; it does not start an automatic sequence of
single-example revisions.

## 7. Convergence and token discipline

- Read canonical files first; do not reconstruct state from chat.
- Work requirement families in batches and update one canonical ledger.
- Prefer editing a canonical definition over creating another explanatory packet.
- Reuse independently accepted evidence where its exact scope applies.
- Do not repeatedly reseal unchanged history.
- Do not stop after a named example when the full authorized family can be tested.
- Keep prompts short by anchoring them to repository files and exact requirement
  IDs.
- At each checkpoint report canonical requirements closed, still blocked, and the
  next single state transition.

## 8. Coding-agent handoff

`docs/harness/CODEX_CLI_HANDOFF.md` is produced only after independent harness
acceptance. It must:

- bind the exact accepted commit and canonical file paths;
- tell the coding agent to implement, not redesign;
- prohibit invention of unresolved scientific or product decisions;
- map implementation modules and tests to requirement, equation, schema, source,
  and business-rule IDs;
- supply a topologically ordered prerequisite map proving that required evidence
  is present before each implementation step;
- prohibit the coding agent from researching or inventing missing evidence;
- require adversarial code review against `ADVERSARIAL_REVIEW.md`;
- preserve the operator's no-submission, no-authority-contact, and no-impact-claim
  boundaries.

If any affected requirement remains `OPEN_BLOCKER`, the handoff must prevent that
implementation branch rather than ask the coding agent to decide it.

## 9. Completion checklist

The harness is complete only when:

1. all required canonical files exist in the real repository;
2. every coding-relevant requirement is `CLOSED` or explicitly blocks its branch;
3. all equations, URLs, schemas, and business rules meet this runbook;
4. canonical documentation and machine configuration reconcile exactly;
5. a fresh independent review accepts the exact repository bytes;
6. the CLI handoff references only those accepted bytes;
7. no implementation, data acquisition, benchmark, or scientific execution was
   performed during harness construction.
