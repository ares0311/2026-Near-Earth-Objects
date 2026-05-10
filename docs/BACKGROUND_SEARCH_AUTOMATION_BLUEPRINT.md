# Background Search Automation Blueprint

## Purpose

This blueprint defines a reusable architecture for scientific projects that need to run a conservative background search process, prioritize promising targets, log every run, bifurcate outcomes, perform follow-up testing, draft reports, and stop at a human approval gate before any external submission.

The pattern is intentionally generalizable. It can apply to technosignature searches, anomaly searches, catalog triage, validation pipelines, observational follow-up planning, or any project where automated screening must preserve uncertainty, provenance, and human review.

## Core Principle

Background automation may identify targets, run approved local tests, maintain logs, and draft reports. It must not claim discovery, confirmation, external validation, or submission approval without explicit human review.

False positives remain the default hypothesis. Negative evidence, missing evidence, blocking issues, and provenance must be first-class outputs.

## Recommended Execution Model

Use an external scheduler as the primary background mechanism.

The project should expose one authoritative command that performs exactly one bounded run, for example:

```bash
project-search background-run-once
```

An external scheduler such as cron, launchd, systemd timers, a job queue, or a controlled workflow runner should invoke that command at the desired cadence.

This model is preferred because each run is discrete, auditable, restartable, and easier to reproduce. Long-lived background loops may still be useful for local demos or development, but they should wrap the same single-run command rather than contain separate scientific logic.

## Required Boundaries

Automation must be constrained by explicit project policy.

| Boundary | Required Behavior |
| --- | --- |
| Data access | Use only approved data sources and committed fixtures unless live access is explicitly configured. |
| Network access | Default to no network access. Any live query mode must be opt-in and logged. |
| Claims | Do not claim discovery, confirmation, or external validation. |
| Provenance | Record input paths, fixture versions, schema versions, code version, run timestamp, and configuration. |
| Uncertainty | Preserve uncertainty in scores, classifications, and recommendations. |
| Negative evidence | Log non-detections, weak evidence, rejected hypotheses, and blockers. |
| Human review | Require explicit user approval before any external submission or contact. |

## State Model

Use three durable logs as the minimum operational state.

| Log | Purpose | Append Rule |
| --- | --- | --- |
| Durable run ledger | Records every scheduled or manual background run. | Every invocation writes exactly one ledger entry. |
| Reviewed log | Records targets that were searched and do not currently require follow-up. | Written when thresholds and rules do not justify follow-up. |
| Needs-follow-up log | Records targets requiring additional tests, human review, or report preparation. | Written when thresholds, rules, or blocking issues justify follow-up. |

The durable run ledger is the source of truth. The reviewed and needs-follow-up logs are outcome-specific audit trails derived from each run.

## Target Selection Logic

Target selection should use a composite priority score that balances scientific promise with operational discipline.

Recommended factors:

| Factor | Direction | Rationale |
| --- | --- | --- |
| Scientific interest score | Higher is better | Prioritizes promising targets. |
| Prior review penalty | Lower is better | Avoids repeatedly reviewing the same target without new evidence. |
| Never-reviewed boost | Higher is better | Encourages exploration of promising targets not yet searched. |
| Data completeness | Higher is better | Reduces false-positive risk from missing context. |
| False-positive risk | Lower is better | Treats mundane explanations as the default hypothesis. |
| Follow-up feasibility | Higher is better | Prefers targets with enough local evidence for additional testing. |
| Calibration confidence | Higher is better | Prefers targets in better-characterized score regimes. |
| Blocking issue penalty | Lower is better | Avoids advancing targets with unresolved methodological blockers. |

The selection output must expose the component factors, final score, selected target, skipped targets, and reason codes.

## Outcome Bifurcation

Each background run must end in one of two primary outcomes.

| Outcome | Meaning | Required Output |
| --- | --- | --- |
| Reviewed | The target was searched and does not currently warrant follow-up. | Reviewed-log entry with negative evidence and rationale. |
| Needs follow-up | The target has enough anomaly evidence, uncertainty, or blocking issues to require additional work. | Needs-follow-up entry with reason codes and required tests. |

Both outcomes must also write to the durable run ledger.

## Follow-Up Triggers

Follow-up should be triggered by both quantitative thresholds and qualitative rules.

Quantitative triggers may include:

- score above a configured threshold
- confidence interval crossing a review threshold
- anomaly score above a configured track-specific limit
- false-positive score below a configured rejection threshold
- reproducibility score below a required confidence level

Rule-based triggers may include:

- missing or incomplete provenance
- conflict between independent fixture checks
- incomplete false-positive analysis
- calibration uncertainty outside accepted bounds
- target never reviewed and composite score above exploration threshold
- methodology-specific warning signs
- reportable blocking issue that requires human judgment

Every trigger should be recorded with a stable reason code.

## Mandatory Follow-Up Tests

Before a report can be drafted, the system should run or explicitly block each mandatory follow-up test.

| Test | Purpose | Allowed Status |
| --- | --- | --- |
| Provenance check | Confirms inputs, schemas, versions, and configuration are traceable. | pass, fail, blocked |
| False-positive class check | Tests mundane explanations before escalating interest. | pass, fail, blocked, uncertain |
| Cross-source consistency check | Compares approved local sources or fixtures for contradictions. | pass, fail, blocked, uncertain |
| Calibration confidence check | Confirms the score lies in a characterized regime. | pass, fail, blocked, uncertain |
| Reproducibility check | Confirms deterministic rerun or independent local reproduction. | pass, fail, blocked, uncertain |
| Human-review checklist | Ensures a reviewer can inspect evidence and limitations. | ready, blocked |

Reports may proceed only when mandatory tests are complete or when blocked tests are documented with explicit rationale.

## Report Drafting Gate

A report draft is allowed only after follow-up testing reaches a reportable state.

The report should include:

- abstract
- target context
- data provenance
- methodology
- scoring and thresholds
- follow-up tests performed
- evidence supporting follow-up
- negative evidence
- false-positive analysis
- uncertainty and limitations
- blocking issues
- recommended next steps
- submission or review destination recommendations

The report must use conservative language. It may describe an anomaly, candidate signal, follow-up target, or project-specific candidate. It must not describe a confirmed discovery without external validation.

## Submission Recommendations

The system may recommend a ranked top-three list of review or submission destinations.

Each recommendation should include:

| Field | Description |
| --- | --- |
| destination | Name of the review venue, collaborator group, issue tracker, archive, observing program, or internal review path. |
| rank | 1 through 3. |
| suitability rationale | Why this destination fits the evidence and project maturity. |
| risks | Reasons submission may be premature or inappropriate. |
| prerequisites | Additional tests, approvals, or formatting requirements. |
| recommended action | submit, internal review, request more tests, or do not submit yet. |

“Do not submit yet” must remain an allowed recommendation.

## Human Approval Gate

External submission must always require explicit human approval.

The system may:

- draft a report
- summarize evidence
- recommend destinations
- identify missing tests
- prepare submission materials

The system must not:

- submit externally without approval
- contact outside parties without approval
- claim endorsement from a destination
- convert an internal candidate into a discovery claim

## Scheduler Contract

The scheduler should call the single-run command at a fixed cadence and preserve logs.

Recommended scheduler responsibilities:

- invoke the run command
- capture stdout and stderr
- enforce runtime limits
- set environment variables or config paths
- avoid overlapping runs unless explicitly supported
- notify the user only on failures or needs-follow-up events

Recommended project responsibilities:

- choose one target per run unless configured otherwise
- write exactly one durable ledger entry per run
- write exactly one outcome entry per run
- avoid network access unless explicitly configured
- expose machine-readable summaries
- remain deterministic for committed fixtures

## Suggested CLI Surface

Projects following this pattern should expose commands like:

```bash
project-search background-run-once
project-search target-priority-summary
project-search background-ledger-summary
project-search reviewed-log-summary
project-search needs-follow-up-summary
project-search follow-up-test-summary
project-search draft-report-summary
project-search submission-recommendation-summary
project-search validation-summary
```

The CLI should produce structured JSON by default or offer a JSON mode so that schedulers and downstream review tools can consume outputs reliably.

## Suggested Build Sequence

1. Define schemas for the durable run ledger, reviewed log, and needs-follow-up log.
2. Implement composite target prioritization with never-reviewed target preference.
3. Implement one-run background execution with fixture-only inputs.
4. Write one ledger entry for every run.
5. Bifurcate each run into reviewed or needs-follow-up.
6. Add threshold-based and rule-based follow-up triggers.
7. Define mandatory follow-up test schemas.
8. Implement deterministic local follow-up tests.
9. Add report-readiness checks.
10. Draft conservative reports from completed follow-up records.
11. Generate ranked top-three submission recommendations.
12. Add the human approval gate.
13. Add scheduler documentation for cron, launchd, or the project’s preferred scheduler.
14. Add validation-summary integration.
15. Add tests for schemas, CLI outputs, log invariants, and guardrail language.

## Definition of Done

A project has implemented this blueprint when:

- every background run writes a durable ledger entry
- every run writes exactly one outcome entry
- target selection exposes its composite factors
- never-reviewed promising targets are prioritized
- needs-follow-up records trigger mandatory tests
- reports include evidence, negative evidence, uncertainty, and limitations
- top-three submission recommendations are generated conservatively
- external submission requires human approval
- tests validate schemas, logs, CLI behavior, and guardrails
- documentation explains scheduler setup and operational safety

