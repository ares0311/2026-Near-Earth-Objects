# Canonical README Specification for the Sibling Astronomy Repositories

## Purpose and authority

This file defines the mandatory structure and evidence standard for each sibling repository's root `README.md`. The README is the repository's authoritative operational and scientific specification. Supporting documents may add detail but must not contradict it.

The governing rule is:

> **Identical information architecture; repository-specific verified content.**

Current code, tests, schemas, executable commands, and generated-artifact contracts outrank historical prompts, runbooks, roadmaps, and sibling documentation.

## Required root structure

Use these headings exactly, once each, and in this order:

```markdown
# <Project Name>

<Project identity table>

## Table of Contents

## 1. Executive Summary
### 1.1 Research Objective and Scientific Context
### 1.2 Scope, Boundaries, and Exclusions
### 1.3 System and Workflow Overview
### 1.4 Verified Capability Status
### 1.5 Evidence and Reproducibility

## 2. CLI Tool Usage
### 2.1 Prerequisites
### 2.2 Installation
### 2.3 Environment Setup
### 2.4 Command Structure
### 2.5 End-to-End Workflow
### 2.6 Command Reference
### 2.7 Outputs and Artifacts
### 2.8 Exit Codes and Failure Behavior
### 2.9 Troubleshooting

## 3. Analytics, Mathematics, and Theoretical Foundation
### 3.1 Problem Formulation
### 3.2 Inputs, Outputs, Labels, Units, and Provenance
### 3.3 Mathematical Notation
### 3.4 Models, Algorithms, and Scores
### 3.5 Assumptions, Objectives, and Statistical Methods
### 3.6 Thresholds, Calibration, and Uncertainty
### 3.7 Evaluation and Validation
### 3.8 Limitations and Failure Modes
### 3.9 Implementation and Test Traceability

## 4. Sibling Repositories and Shared Data
### 4.1 Research Program and Repository Responsibilities
### 4.2 Local Discovery and Configuration
### 4.3 Shared Artifacts, Ownership, and Access
### 4.4 Schemas, Provenance, Versioning, and Compatibility
### 4.5 Availability, Failure Behavior, and Regeneration
### 4.6 Cross-Repository Safety Boundaries
```

The identity table must state the research domain, primary task, validated status, actual CLI entry point, data-contract/schema version when one exists, sibling repositories, and canonical documentation location. Use `Not applicable` only when verified; never guess a value.

## Content requirements

### 1. Executive Summary

Give a compact academic overview of the research question, scientific motivation, hypotheses where applicable, supported workflow, scope, exclusions, and evidence-backed system status. The capability table must pair each claim with a code, test, schema, command, or reproducible artifact reference.

### 2. CLI Tool Usage

Make this section sufficient for a new operator to install and run the supported workflow without reading Section 3. Document only registered commands and options verified from current source and help output. Include copy-paste-safe commands, required inputs, configuration precedence, expected outputs, exit behavior, bounded examples, and recovery guidance. Never fabricate a common CLI to create sibling symmetry.

### 3. Analytics, Mathematics, and Theoretical Foundation

Describe only analytics used by the current implementation. For every material equation or score, define symbols, dimensions or units, domain, assumptions, and interpretation; identify its implementation path and validation test. Cover applicable preprocessing, models, objectives, statistical methods, thresholds, calibration, uncertainty, evaluation metrics, baselines, and injection-recovery. State scientific and operational limitations plainly.

### 4. Sibling Repositories and Shared Data

Name all three siblings and distinguish their scientific responsibilities. Describe the verified same-machine sharing contract, not a proposed layout. For each shared artifact, state its owner/producer, permitted readers, discovery or configuration method, schema/version, provenance, compatibility checks, stale or unavailable behavior, and regeneration procedure. Use portable configuration or repository-relative discovery; do not publish personal absolute paths. A repository must not silently edit a sibling's working files.

## Status vocabulary

Only these labels are permitted:

| Status | Required meaning |
|---|---|
| **Implemented** | Present, executable, tested, and documented. |
| **Experimental** | Present and executable, but intentionally outside the primary validated workflow. |
| **Deprecated** | Retained only for compatibility or reproducibility. |
| **Nonconforming** | Required by the completed architecture but missing, broken, inconsistent, or not verifiable. |
| **Not applicable** | Verified to be outside this repository's scientific responsibility. |

Do not use **Planned**, **Partial**, roadmap, backlog, or future-work language. Missing completed-system behavior is a nonconformity, not a plan.

## Verification rules

Before claiming conformance, the editing agent must:

1. Identify the current Git root and obey repository-local directives.
2. Derive claims from current code, tests, schemas, CLI registration, help output, and reproducible artifacts.
3. Run safe, bounded help commands and representative workflows where local fixtures permit.
4. Run the repository-native test and quality-gate commands and record exact results.
5. Confirm every referenced command, path, configuration name, schema, output, sibling link, implementation location, and test exists.
6. Treat skipped, truncated, timed-out, or missing final validator output as inconclusive.
7. Mark unverified required behavior **Nonconforming** and state the missing evidence.
8. Avoid changing implementation merely to make documentation symmetrical; such changes require a separate tested change.

Historical material may explain provenance but cannot establish current status.

## Automated conformance checks

Each repository should enforce a documentation test that verifies:

- Required headings occur once and in the exact order above.
- Heading numbering and the table of contents agree.
- The identity and capability tables contain no blank required fields.
- Placeholder, roadmap, planned, partial, backlog, and future-work language is absent.
- Referenced repository paths and CLI entry points exist.
- Required sibling names and links are present.
- Local absolute personal paths and unsupported status labels are absent.
- Material scientific claims include implementation and validation references.

The check must run in the repository's normal validation or CI suite. A structural pass does not prove scientific correctness; manual evidence review remains required.

## Sibling symmetry rule

The siblings must share the title pattern, numbered hierarchy, table shapes, terminology, status vocabulary, evidence standard, and cross-repository contract format. They need not share commands, algorithms, datasets, results, or maturity labels. Differences must reflect verified implementation, never cosmetic pressure for uniformity.
