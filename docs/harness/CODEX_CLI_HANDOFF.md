# Codex CLI Handoff

Status: `BLOCKED_HARNESS_CONSOLIDATION_INCOMPLETE`

No coding-agent implementation prompt is authorized yet.

This file becomes the implementation handoff only after:

1. the canonical harness specification is complete;
2. every coding-relevant requirement is closed or explicitly blocks its branch;
3. the source registry, schemas, equations, business rules, and adversarial tests
   reconcile;
4. a fresh independent reviewer issues
   `HARNESS_READY_FOR_CODEX_CLI_HANDOFF` against the exact repository bytes.

Every future implementation step must receive its complete validated evidence
prerequisites before it starts. The CLI agent will not be authorized to fill a
missing source, equation, schema, threshold, or business rule through research,
assumption, or invention.

The future prompt must tell Codex CLI to implement the accepted specification,
not redesign it, and must map every implementation module and test to stable
requirement, equation, schema, business-rule, source, and review IDs.
