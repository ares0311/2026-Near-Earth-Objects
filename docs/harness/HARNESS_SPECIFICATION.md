# Canonical NEO Harness Specification

Status: `HARNESS_CONSOLIDATION_INCOMPLETE`

This is the canonical consolidation target for the NEO harness. The independently
accepted v3 specification in `reference/accepted-specification-v3/` is the
starting source, not a substitute for this completed document.

The controlling product scope is `OPERATOR_OBJECTIVE.md`. Scientific-processing
domains are method content inside that scope, not the definition of the harness.

## Objective-to-requirement traceability

`configs/harness/traceability.json` binds all 15 operator requirements, 48
accepted requirements, 16 incomplete requirements, and 16 open dependencies to
stable NeoHunter workflow IDs, canonical output sets, evidence prerequisites, and
acceptance-test families. `REQUIREMENT_TRACEABILITY.md` is the human-readable
interpretation.

The binding incorporates exact normative text, dependency fields, closure
evidence, and blocking scopes from the accepted registers rather than duplicating
or weakening them. A scientific-domain requirement is actionable only through a
mapped product workflow and only after its evidence prerequisites are
independently validated. The current HB-01 mapping is an orchestrator-produced
draft. It is not an author package and is not eligible for independent review;
a separate author must reconstruct or independently adopt every binding first.

## Required final content

The completed specification will contain one normative definition for each of
the following:

1. Spec Prompt file hierarchy, agent roles, context routing, and stop rules;
2. NeoHunter CLI commands, parameters, autocomplete, output grids, and dark-mode
   terminal UX;
3. search-result persistence, filtering, restartability, sharding, workers,
   storage ceilings, telemetry, and ETA behavior;
4. applicable astrometric data-source interfaces, verified URLs, product schemas,
   access conditions, and Keychain credential procedures;
5. applicable classical and frontier-AI quantitative methods, including the seven
   candidate scientific domains only where product traceability is established;
6. labels, splits, cutoff safety, and leakage prevention;
7. metrics, denominators, selection functions, uncertainty intervals, power,
    multiplicity, and decision thresholds;
8. record schemas, state transitions, reason codes, retention, and recovery;
9. equation, data-interface, method, implementation, and detection adversarial
   validation, including second-order validation and matched controls;
10. follow-up, rejection/reclassification, independent verification, and
    operator-gated submission/publication packaging;
11. future implementation, bounded evaluation, and production-selection gates;
12. authority and claim boundaries;
13. the topologically ordered Codex CLI implementation handoff.

## Normative completeness rule

Each method section must identify:

- requirement, equation, schema, source, and business-rule IDs;
- exact inputs, outputs, units, coordinate/time frames, ordering, and identity;
- equations and deterministic algorithm steps;
- numerical tolerances and invalid/missing-input behavior;
- uncertainty and covariance propagation;
- retained intermediate evidence and fail-closed reason codes;
- required attacks and matched legitimate controls;
- explicit branches that remain blocked.

Descriptive phrases from the accepted source—such as “PSF-aware,” “MOPS-style,”
“covariance-aware,” or “statistical ranging”—are requirements to specify, not
permission for the coding agent to choose an implementation.

## Current controlling gaps

The exact starting gaps are recorded in:

- `configs/harness/requirements.json`;
- `reference/accepted-specification-v3/requirements-register.csv`;
- `reference/accepted-specification-v3/incomplete-requirements.csv`;
- `reference/accepted-specification-v3/unresolved-dependencies.csv`.

Until those coding-relevant gaps are closed or explicitly block their affected
branch, this document is not a Codex CLI implementation assignment.
