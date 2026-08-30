# NEO Harness Location and Status Index

This is the mutable operator-facing index for the immutable harness-builder
runbook. Agents may update locations, evidence references, blockers, and status
here and in `configs/harness/roadmap-index.json`. They may not edit the immutable
runbook to record ordinary progress.

Current state: `HARNESS_CONSOLIDATION_INCOMPLETE`

Current work package: `HB-01`

| Work package | Status | Canonical location | Evidence or blocker location |
|---|---|---|---|
| HB-00 | COMPLETE | `AGENTS.md`; `configs/harness/harness-charter.json`; `configs/harness/roadmap.json`; `docs/runbook/` | `docs/harness/reference/accepted-specification-v3/PROVENANCE.md` |
| HB-01 | AUTHOR COMPLETE; AWAITING INDEPENDENT REVIEW | `configs/harness/requirements.json`; `configs/harness/traceability.json`; `docs/harness/REQUIREMENT_TRACEABILITY.md`; `docs/harness/HARNESS_STATUS.md`; `docs/harness/HARNESS_SPECIFICATION.md` | accepted v3 registers under `docs/harness/reference/accepted-specification-v3/`; fresh HB-01 review not started |
| HB-02 | PENDING | `docs/harness/SOURCE_REGISTRY.csv` | accepted source-check seed; remaining claims not yet indexed |
| HB-03 | PENDING | `docs/harness/HARNESS_SPECIFICATION.md`; `configs/harness/schemas/` | not yet indexed |
| HB-04 | PENDING | `docs/harness/HARNESS_SPECIFICATION.md`; `configs/harness/schemas/` | not yet indexed |
| HB-05 | PENDING | `docs/harness/HARNESS_SPECIFICATION.md`; `docs/harness/SOURCE_REGISTRY.csv`; `configs/harness/schemas/` | not yet indexed |
| HB-06 | PENDING | `configs/harness/schemas/`; `configs/harness/requirements.json` | not yet indexed |
| HB-07 | PENDING | `docs/harness/HARNESS_SPECIFICATION.md`; `configs/harness/schemas/` | not yet indexed |
| HB-08 | PENDING | `docs/harness/ADVERSARIAL_REVIEW.md`; `configs/harness/requirements.json`; `configs/harness/schemas/` | not yet indexed |
| HB-09 | PENDING | canonical harness tree | fresh independent review not started |
| HB-10 | BLOCKED | `docs/harness/CODEX_CLI_HANDOFF.md` | blocked on HB-09 acceptance |

Each status change must reconcile with `configs/harness/roadmap-index.json` and
be committed. The commit containing this file is the durable historical state;
chat and external output directories are not.
