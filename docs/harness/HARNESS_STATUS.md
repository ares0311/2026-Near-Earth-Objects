# NEO Harness Status

Status: `HARNESS_CONSOLIDATION_INCOMPLETE`

Repository: `/Users/Rome/Library/CloudStorage/Dropbox/Rome's Stuff/Doc.Root/Personal Docs/Astrometrics/2026 Near Earth Objects`

Branch: `harness-rebuild`

Control-plane baseline tag: `harness-builder-control-v1` — immutable; never move,
delete, or reuse.

Current roadmap work package: `HB-01` — operator-objective and requirement
traceability.

HB-01 author status: `AUTHOR_COMPLETE_AWAITING_INDEPENDENT_REVIEW`. The exact
15 operator requirements, 48 accepted requirements, 16 incomplete requirements,
and 16 open dependencies are bound in `configs/harness/traceability.json` and
`docs/harness/REQUIREMENT_TRACEABILITY.md`. HB-02 has not started.

Roadmap authority: `configs/harness/roadmap.json`; operator view:
`docs/runbook/HARNESS_BUILD_ROADMAP.md`.

Mutable location/status index: `configs/harness/roadmap-index.json` and
`docs/harness/HARNESS_INDEX.md`. Agents update these indexes instead of editing
the immutable runbook or roadmap definition.

Operator decisions recorded 2026-08-30:

- fresh public primary-source research is allowed only when every canonical claim
  receives fresh independent adversarial validation and a matched legitimate
  control;
- evidence must be validated and packaged before the Codex CLI agent reaches the
  dependent implementation step;
- missing empirical evidence is a hard pre-work blocker, not a decision delegated
  to the coding agent.

Alignment correction recorded 2026-08-30:

- the harness is the complete Spec Prompt, product, data/access, scientific,
  operational, adversarial, disposition, and implementation-handoff system in
  `OPERATOR_OBJECTIVE.md`;
- the seven scientific domains from accepted v3 are subordinate method content,
  not seven harness phases and not the complete requested harness;
- each domain must be traced to an operator-facing NeoHunter workflow before it
  is included as a normative implementation requirement.

## What is accepted

The exact external NEO Harness Specification v3 package was independently
accepted as a bounded specification source:

- manifest SHA-256: `6825a1cce0c649ae7151f9dcda4a6725bc82ff7235a97f89f3212cff90d902fb`;
- digest-record SHA-256: `9ac8fa3c7e55ffc6f6364cb8a673de2a119be01880b3ad676e8920aa6c02570b`;
- independent-review manifest SHA-256:
  `c2d3de93f2df2b24b04bce60df8f39112e9d4fe3df001d09520a8853e2c57789`.

That acceptance established internal specification consistency and preserved
scope boundaries. It did not establish implementation readiness or harness
completion.

Immutable copies are under `reference/accepted-specification-v3/`.

## Reconciled starting counts

- Requirements: 48 total; 34 `SPECIFIED_COMPLETE`; 14
  `SPECIFIED_INCOMPLETE`.
- Open questions: OQ-01 through OQ-15 `UNRESOLVED`; OQ-16
  `UNRESOLVED_HISTORICAL_PROVENANCE_LIMITATION`.
- Incomplete requirements: IR-001 through IR-015 `INCOMPLETE`; IR-016
  `INTENTIONALLY_DEFERRED` at post-G10.
- Verified source-claim seed: 35 independently checked NEO-003 claims, including
  primary URLs and explicit transfer limits.

## Canonical deliverable state

| Deliverable | State | Completion condition |
|---|---|---|
| Repository directive hierarchy | COMPLETE | Root, docs, configs, and reference directives agree |
| Parent machine charter | COMPLETE | Strict JSON and repository identity verified |
| Accepted specification intake | COMPLETE | Exact source, review, checkpoint, and registers imported read-only |
| Canonical source registry | PARTIAL | Every normative factual claim has a verified source ID and transfer limit |
| Consolidated harness specification | PARTIAL | Accepted base reconciled and every coding decision made explicit |
| Exact mathematics and algorithms | OPEN_BLOCKER | Equations, symbols, units, domains, tolerances, and invalid behavior complete |
| Machine-readable schemas | OPEN_BLOCKER | Every required record/config/evidence schema complete and mutually consistent |
| Business logic and reason codes | PARTIAL | Every state transition, prohibition, recovery, and retained record explicit |
| Acceptance thresholds and power | OPEN_BLOCKER | Outcome-blind numerical criteria and uncertainty rules frozen |
| Adversarial-review contract | PARTIAL | Full requirement-family attacks and matched controls frozen |
| Independent review | NOT_STARTED | Fresh reviewer accepts exact canonical repository bytes |
| Codex CLI handoff | BLOCKED | Independent acceptance and all coding-relevant closure conditions met |

## Active blocking families

The current blocking families are the 15 incomplete requirements IR-001 through
IR-015. They cover exact benchmark identities, pixel and catalog schemas,
covariance and trail-error models, injection design, cutoff-safe labels,
time/observer normalization, denominators, cross-survey calibration, resource
budgets, rare regimes, precovery identity, uncertainty calibration, numerical
decision thresholds, and access/licensing.

IR-016 remains deferred because production architecture selection occurs only
after the future bounded benchmark evidence. The harness must specify that future
decision process; it must not select or implement the production architecture now.

## Progress rule

Do not change this status to `HARNESS_AWAITING_INDEPENDENT_REVIEW` until a coding
agent can follow only canonical repository files without inventing a materially
different method, equation, URL, schema, threshold, business rule, or acceptance
decision.

Every later status change must be committed in this repository and reconcile the
machine roadmap, this ledger, the requirements register, and affected canonical
files. Chat summaries and external packet labels do not move the roadmap.
