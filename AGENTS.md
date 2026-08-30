# NEO Harness Repository Directives

This repository is the only authoritative workspace for the NEO harness rebuild.
Codex conversation workspaces, pasted artifacts, sibling checkouts, and external
output packages are evidence sources only; they are never the project root.

## Startup gate

Before any project work:

1. Run `git rev-parse --show-toplevel` and require the exact root:
   `/Users/Rome/Library/CloudStorage/Dropbox/Rome's Stuff/Doc.Root/Personal Docs/Astrometrics/2026 Near Earth Objects`.
2. Read this file, `configs/harness/harness-charter.json`,
   `configs/harness/roadmap.json`, `configs/harness/roadmap-index.json`, the
   nearest applicable `AGENTS.md`,
   `docs/runbook/HARNESS_BUILD_RUNBOOK.md`, and
   `docs/harness/HARNESS_STATUS.md`.
3. Inspect `git status --short --branch` and preserve unrelated changes.
4. Verify `configs/harness/immutable-control-plane.sha256` and require the
   protected paths to match tag `harness-builder-control-v1` exactly. Stop with
   `BLOCKED_CONTROL_PLANE_MUTATION` on any difference.
5. Stop with `BLOCKED_WRONG_WORKSPACE` if the root check fails. Do not create a
   substitute workspace or copy project authority into a conversation directory.

## Macroscopic objective

Build a coding-agent-ready specification and prompt harness. It must pin the
verified mathematics, source URLs, schemas, business logic, acceptance tests,
adversarial-review procedure, unresolved dependencies, and stop conditions for
the NEO project so the later coding agent does not invent unverified decisions.

The complete operator objective is canonicalized in
`docs/harness/OPERATOR_OBJECTIVE.md`. It includes the Spec Prompt control system,
NeoHunter CLI and UX, data-source and credential-interface specifications,
classical and frontier-AI methods, persistence and operations, scientific and
software adversarial validation, detection disposition, and the final coding
handoff. Scientific method domains are subordinate content, not the harness
architecture.

The current repository state is `HARNESS_CONSOLIDATION_INCOMPLETE`.

Harness completion requires all deliverables listed in the machine-readable
charter and an independent review of their exact repository bytes. A reviewed
planning document, a gate label, a checksum packet, or a count of passing tests
is not by itself a completed harness.

## Current scope boundary

Allowed now:

- consolidate and verify harness specifications, equations, source citations,
  schemas, decision rules, tests-as-specification, and agent handoff instructions;
- perform read-only research against public primary documentation;
- write documentation and machine-readable configuration inside this repository;
- statically validate harness artifacts and independently review the completed
  specification package.

Prohibited until the operator explicitly changes the charter:

- implementation code or executable project scripts;
- scientific-data acquisition or provider data queries;
- pipeline, baseline, candidate, model, benchmark, search, or scientific runs;
- model training, RunSeals, runtime evidence, deployment, or production work;
- scientific submission, authority contact, discovery, impact, or operational
  fitness claims.

Future G1-G10 descriptions may be specified as coding-agent logic. They must not
be executed while constructing this harness.

Every new external claim must pass fresh independent adversarial validation of
its source identity, exact support, demonstrated context, evidence grade,
transfer limit, and prohibited inference, with a matched legitimate control,
before entering the canonical harness. Author research or a reachable URL is not
canonical evidence.

Evidence is required before use: each future coding step must map to prerequisite
evidence already present and independently validated in the harness. If evidence
is missing, the affected step is blocked before it starts. The Codex CLI agent may
not be asked to research, infer, or invent it during implementation.

## Directive hierarchy

Apply directives in this order, subject to platform instructions and the current
operator request:

1. `configs/harness/harness-charter.json` — machine-readable project objective,
   deliverables, completion test, and prohibited actions.
2. This root `AGENTS.md` — repository-wide working rules.
3. The nearest descendant `AGENTS.md` — directory-specific rules.
4. `docs/harness/OPERATOR_OBJECTIVE.md` — canonical product and harness scope.
5. `docs/runbook/HARNESS_BUILD_RUNBOOK.md` — operating process.
6. Canonical harness files under `docs/harness/` and `configs/harness/`.
7. Imported accepted source material under `docs/harness/reference/`.
8. External packages, historical artifacts, chat, and agent summaries.

Lower levels may not expand authority granted by higher levels. A conflict stops
work; it is not resolved by assumption.

## Canonical repository outputs

- `docs/harness/HARNESS_STATUS.md` — current truth and gap ledger.
- `docs/harness/HARNESS_SPECIFICATION.md` — consolidated normative specification.
- `docs/harness/SOURCE_REGISTRY.csv` — verified source URLs and transfer limits.
- `docs/harness/ADVERSARIAL_REVIEW.md` — independent review contract.
- `docs/harness/CODEX_CLI_HANDOFF.md` — final coding-agent assignment.
- `configs/harness/harness-charter.json` — parent machine charter.
- `configs/harness/roadmap.json` — immutable dependency order and completion map.
- `configs/harness/roadmap-index.json` — mutable current status and location map.
- `configs/harness/requirements.json` — machine-readable requirement closure.
- `configs/harness/schemas/` — machine-readable schemas required by the coding
  agent.

Imported files in `docs/harness/reference/` are immutable source material, not
canonical current instructions.

The annotated tag `harness-builder-control-v1` anchors the initial control plane.
Never move, delete, or reuse it. Every later roadmap-state claim must identify a
Git commit; chat, a packet path, or an agent status line is not durable state.

The runbook, roadmap definition, objective, charter, and directive files listed
in `configs/harness/immutable-control-plane.sha256` are immutable to ordinary
agents. Record progress by updating `configs/harness/roadmap-index.json`,
`docs/harness/HARNESS_INDEX.md`, and `docs/harness/HARNESS_STATUS.md`; do not add
progress notes to the runbook itself. Only an explicit operator-authorized,
versioned control-plane migration may replace protected instructions.

## Agent and review behavior

- Use one top-level agent unless the operator explicitly authorizes otherwise in
  the current request.
- An author may consolidate and revise but may not independently accept.
- An independent reviewer may test and issue the permitted specification verdict
  but may not repair the target.
- Complete the authorized scope and group findings by failure family. Do not run
  one revision per named example.
- Optimize for canonical content closed, not packets, manifests, prompts, or
  iterations produced.
- Do not stop merely because a checkpoint was reached while safe, authorized
  harness work remains.

## Required final handoff

Report the Git root and branch, files changed, requirement closure counts, source
coverage, unresolved blockers, independent-review result, and exact next state.
Never call the harness complete while a coding agent would still need to invent a
method, equation, URL, schema, threshold, business rule, or acceptance decision.
