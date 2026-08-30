# NEO Harness Build Roadmap

This is the human-readable view of `configs/harness/roadmap.json`. The JSON file
is the machine authority for dependencies and status; this document explains the
same path for the operator. A mismatch is a blocking defect.

The roadmap is about constructing the harness. It is not the G1-G10 scientific
workflow that the completed harness may later specify for the coding agent.

## Durable baseline

- Repository: `2026-Near-Earth-Objects`
- Branch: `harness-rebuild`
- Clean rebuild base: `f915bba`
- Harness-builder control-plane tag: `harness-builder-control-v1`
- Tag policy: never move, delete, or reuse this tag

The tagged control plane fixes the objective, instruction hierarchy, completion
test, prohibited execution boundary, accepted reference identities, and this
dependency order. Future work records locations and status in ordinary commits,
so each claimed state is recoverable from Git. Agents update only
`configs/harness/roadmap-index.json`,
`docs/harness/HARNESS_INDEX.md`, and `docs/harness/HARNESS_STATUS.md`; they do not
edit this roadmap. Changes to the objective, dependency order, or completion test
require an explicit operator decision and a new versioned control tag. They may
not be introduced by an author or reviewer task.

## Roadmap

| ID | Work package | Depends on | Current state | What advances the harness |
|---|---|---|---|---|
| HB-00 | Control plane and accepted-reference intake | — | COMPLETE | Real repo, objective, authority, accepted inputs, and completion test anchored |
| HB-01 | Operator-objective and requirement traceability | HB-00 | IN PROGRESS | Every product and scientific requirement mapped to workflow, evidence, output, and test |
| HB-02 | Source registry and evidence admission | HB-01 | PENDING | All canonical claims independently source-validated with transfer limits and controls |
| HB-03 | Data, access, and credential interfaces | HB-01, HB-02 | PENDING | Exact provider interfaces, schemas, access limits, licensing, and Keychain contracts |
| HB-04 | Product CLI, UX, persistence, and business logic | HB-01 | PENDING | Deterministic commands, states, database, filtered views, UX, reason codes, and tests |
| HB-05 | Scientific methods and mathematics | HB-01, HB-02, HB-03 | PENDING | Exact applicable classical/AI methods or explicit blocked branches |
| HB-06 | Schemas, reason codes, and evidence dependencies | HB-03, HB-04, HB-05 | PENDING | Strict records plus evidence-before-use implementation DAG |
| HB-07 | Operations, resources, restartability, and telemetry | HB-03, HB-04, HB-05 | PENDING | Non-LLM runtime, workers, recovery, telemetry, ETA, and resource contracts |
| HB-08 | Adversarial validation and detection disposition | HB-02 through HB-07 | PENDING | Requirement-family attacks, controls, second-order review, and detection handling |
| HB-09 | Canonical reconciliation and independent acceptance | HB-01 through HB-08 | PENDING | Exact committed harness accepted by a fresh independent reviewer |
| HB-10 | Codex CLI implementation handoff | HB-09 | BLOCKED | Accepted evidence-complete implementation assignment bound to exact bytes |

## Current position

`HB-01` is the only active work package. The accepted v3 source is useful input,
but its seven scientific domains are content for HB-03, HB-05, HB-06, and HB-08;
they are not this roadmap and do not represent seven completed harness phases.

The next valid state transition is completion of objective-to-requirement
traceability. Starting implementation, acquiring scientific payloads, or running
the future G1-G10 workflow cannot advance this roadmap and remains prohibited.

## Completion condition

The roadmap ends only at `HARNESS_READY_FOR_CODEX_CLI_HANDOFF`: exact canonical
bytes independently accepted, every coding-relevant decision closed or its branch
blocked before implementation, and a handoff that requires the Codex CLI agent to
implement rather than research or redesign.
