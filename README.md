# NeoHunter

Clean pre-harness rebuild baseline.

The previous implementation is preserved in the remote Git repository
at the tag `pre-harness-archive`.

This branch intentionally inherits no scientific, implementation,
agent-control, or UX assumptions from the previous implementation.

## Current objective

This branch now contains the canonical NEO specification-harness build. The
harness must fully specify verified mathematics, source URLs, schemas, business
logic, acceptance tests, adversarial review, and the later Codex CLI handoff
before implementation begins.

Current status: `HARNESS_CONSOLIDATION_INCOMPLETE`.

Start with:

1. `AGENTS.md`
2. `configs/harness/harness-charter.json`
3. `configs/harness/roadmap.json`
4. `configs/harness/roadmap-index.json`
5. `docs/harness/OPERATOR_OBJECTIVE.md`
6. `docs/runbook/HARNESS_BUILD_RUNBOOK.md`
7. `docs/runbook/HARNESS_BUILD_ROADMAP.md`
8. `docs/harness/HARNESS_INDEX.md`
9. `docs/harness/HARNESS_STATUS.md`

No implementation, data acquisition, benchmark, pipeline execution, or
scientific claim is authorized by the current branch state.
