# ARTIFACT 2 — docs/CLI_UX_SPEC.md

# Hunter Shared CLI and UX Specification

**Specification version:** `HUNTER-CLI-UX-2026-07-30.3`  
**Applies to:** NEOHunter, EXOHunter, TechnoHunter

## 1. Objective

The three Hunters must share one logical interaction architecture while retaining project-specific terminology, scientific constraints, result fields, and animations.

Claude Code’s command discovery and guided optional-argument interaction are the minimum baseline.

The Hunters must exceed that baseline through stronger validation, scientific explanations, action previews, genuine progress, cleaner presentation, and richer domain-specific animation.

The normal user must not need to memorize raw `argparse` syntax.

## 2. Canonical Executables

Canonical interactive names:

- `NEOHunter`
- `EXOHunter`
- `TechnoHunter`

Compatibility aliases may remain, but each README must identify one canonical executable.

The shell remains active until `/Exit`.

## 3. Required Commands

- `/New-Search`
- `/Follow-Up-Search`
- `/Run-Search`
- `/Show-Follow-Ups`
- `/Inspect-Target`
- `/Help`
- `/Exit`

Mode is inherent:

- `/New-Search` → New
- `/Follow-Up-Search` → Follow-up

Do not require a redundant `--mode`.

Lower-level scriptable commands may remain, but they must use the same canonical pipeline and validation layer.

## 4. Startup Experience

### UX-START-01 — Immediate animation

Interactive startup begins immediately with a prominent animated identity.

A static logo or generic spinner alone is nonconforming.

### UX-START-02 — Project themes

**TechnoHunter**

Use one or more:

- alien intelligence emerging from encoded noise;
- first-contact sequence;
- array triangulation;
- signal waterfall resolving into structured information;
- decoded symbolic pattern;
- galactic communications network.

**EXOHunter**

Use one or more:

- animated star field;
- orbital system;
- transit across a stellar disk;
- light-curve formation;
- atmospheric spectrum;
- habitable-zone scan.

**NEOHunter**

Use one or more:

- orbital sweep;
- radar acquisition;
- trajectory projection;
- close-approach geometry;
- moving-object survey;
- telescope scan.

### UX-START-03 — Truthful presentation

Animation must not claim fabricated discoveries, targets, percentages, data states, or scientific conclusions.

### UX-START-04 — Degraded operation

Animation must disable or degrade cleanly for:

- non-TTY output;
- redirected output;
- logs;
- CI;
- explicit no-animation mode;
- accessibility or reduced-motion mode;
- machine-readable output.

## 5. Slash-Command Palette

### UX-CMD-01 — `/` opens the palette

Typing `/` immediately opens a searchable command palette.

The user must not need `/Help` to discover commands.

### UX-CMD-02 — Described commands

Every palette item shows:

- command name;
- concise operational description;
- required parameters;
- optional parameters;
- state-dependent availability.

Example:

    /New-Search
    Select and freeze the best available never-before-searched targets.
    Required: targets
    Optional: scientific constraints, resource limits

### UX-CMD-03 — Navigation

Support:

- live filtering while typing;
- Up/Down navigation;
- Enter to select;
- Escape to close;
- Tab completion;
- discoverable keyboard help.

## 6. Guided Parameter Entry

### UX-IN-01 — Inline editor

Selecting a normal command creates guided editable fields:

    /New-Search

    Targets                 [20]
    Maximum download        [optional]
    Scientific constraints  [Open…]

### UX-IN-02 — Field behavior

- Focus begins at the first required field.
- Tab moves forward.
- Shift-Tab moves backward.
- Enter executes only when all required fields are valid.
- Escape cancels.
- Focused fields show concise descriptions.
- Defaults are visible.
- Optional fields are clearly labeled.
- Enumerations use selectable choices.

### UX-IN-03 — Live validity sentinels

Validate input during entry.

Examples:

    Targets: twenty
    Invalid — enter a positive whole number.

    Targets: 0
    Invalid — targets must be greater than zero.

Validate:

- type;
- range;
- enumeration;
- identifier syntax;
- file or directory existence;
- permissions;
- schema compatibility;
- state prerequisites;
- incompatible combinations.

Invalid input cannot advance or execute.

### UX-IN-04 — Shared validators

Interactive and scriptable operation must use the same canonical validation functions.

Raw `argparse` usage dumps are not the normal interactive error response.

## 7. Advanced Constraints and Wizards

### UX-ADV-01 — Progressive disclosure

Normal top-`N` requests remain simple.

Advanced scientific constraints appear only when opened:

    Scientific constraints

    Target class             [Any]
    Maximum distance         [optional]
    Magnitude range          [optional]
    Maximum acquisition      [optional]
    Project-specific fields  [Open…]

### UX-ADV-02 — Wizard threshold

Use a multi-step wizard only for genuinely complex operations with dependent inputs, such as:

- importing reviewed evidence;
- selecting a credentialed data source;
- configuring many interdependent scientific filters;
- resolving an incompatible schema;
- resuming an ambiguous partial search.

Do not turn a simple target-count request into a questionnaire.

## 8. Resolved-Action Preview

Before freezing a search, show:

    Mode:
    Requested targets:
    Scientific constraints:
    Primary sources:
    Source freshness:
    Cross-project history freshness:
    Estimated discovery universe:
    Estimated storage:
    Estimated compute:
    Output behavior:

The user can confirm, edit, or cancel.

## 9. Execution Experience

### UX-RUN-01 — Stage-aware animation

Animation and progress must correspond to actual pipeline stages.

**TechnoHunter stages may include:**

- array synchronization;
- frequency sweep;
- RFI rejection;
- cadence validation;
- signal scoring;
- intelligence-pattern analysis.

**EXOHunter stages may include:**

- catalog discovery;
- identity resolution;
- transit-product validation;
- light-curve analysis;
- atmospheric or habitability scoring;
- target ranking.

**NEOHunter stages may include:**

- survey discovery;
- orbit resolution;
- known-object exclusion;
- trajectory propagation;
- observability scoring;
- close-approach ranking.

### UX-RUN-02 — Genuine progress

Show measurable information where available:

- current stage;
- completed and total items;
- candidates found;
- candidates rejected;
- expansion round;
- current source;
- elapsed time;
- estimated remaining time only when defensible.

Never fabricate percentages or discoveries.

### UX-RUN-03 — Failure presentation

Show a concise operator-facing error, for example:

    TIC connection closed before the response completed.
    Attempt 2 of 3 failed.
    Search state remains resumable.
    Diagnostic ID: EXO-20260730-184211

Write detailed traceback and request metadata to logs.

## 10. Results Presentation

### UX-TABLE-01 — Width-aware summary

For `N <= 100`, render a clean terminal table containing decision-critical fields.

Requirements:

- detect terminal width;
- use stable column widths;
- truncate intentionally with a visible marker;
- avoid uncontrolled multi-line wrapping;
- preserve rank and identity visibility;
- paginate;
- support row selection.

### UX-TABLE-02 — Detail view

Long scientific explanations, provenance, and selection rationales belong in:

    /Inspect-Target <rank-or-id>

The detail view may include:

- canonical identity and aliases;
- scientific metrics;
- score components;
- selection reason;
- source and transformation provenance;
- prior-search evidence;
- estimated resource requirements;
- limitations.

### UX-TABLE-03 — Large requests

For `N > 100`:

- write a timestamped complete export;
- display a concise summary;
- report the output path;
- preserve a durable non-CSV system of record.

### UX-TABLE-04 — Machine output

Provide stable machine-readable output such as JSON or JSONL without animation, ANSI control sequences, or interactive prompts.

## 11. Accessibility and Terminal Integrity

Support:

- `NO_COLOR`;
- explicit no-color mode;
- explicit no-animation mode;
- reduced-motion mode;
- non-TTY operation;
- small terminal widths;
- interrupted input;
- redirected stdin and stdout;
- Unicode fallback where necessary.

The UI must restore terminal state after exceptions or cancellation.

## 12. Architectural Constraint

The CLI is a presentation and interaction layer.

It must not duplicate:

- candidate selection;
- scientific scoring;
- execution;
- persistence;
- provenance;
- business validation rules.

Prefer an established terminal interaction framework compatible with the repository over hand-written terminal escape-sequence handling.

## 13. Golden UX Tests

Create semantic golden tests or equivalent stable assertions for:

- `tests/golden/startup_neo.txt`
- `tests/golden/startup_exo.txt`
- `tests/golden/startup_techno.txt`
- `tests/golden/command_palette.txt`
- `tests/golden/new_search_fields.txt`
- `tests/golden/invalid_targets.txt`
- `tests/golden/action_preview.txt`
- `tests/golden/results_table_80_columns.txt`
- `tests/golden/results_table_140_columns.txt`
- `tests/golden/operator_error.txt`
- `tests/golden/non_tty_output.txt`

Do not require byte-identical timing-dependent animation frames.

Assert stable semantic elements:

- domain identity;
- command descriptions;
- required and optional fields;
- validation messages;
- stage names;
- table integrity;
- non-TTY behavior.

## 14. UX Acceptance Matrix

| ID | Requirement |
|---|---|
| UX-START-01 | Immediate domain-specific startup animation |
| UX-START-02 | Correct project theme |
| UX-CMD-01 | `/` immediately opens the palette |
| UX-CMD-02 | Commands include descriptions and parameter shapes |
| UX-IN-01 | Guided field entry |
| UX-IN-03 | Live validity sentinels |
| UX-IN-04 | Shared interactive/scriptable validators |
| UX-ADV-01 | Progressive disclosure |
| UX-RUN-01 | Stage-aware execution animation |
| UX-RUN-02 | Genuine progress only |
| UX-TABLE-01 | Width-aware clean table |
| UX-TABLE-02 | Separate target detail view |
| UX-TABLE-04 | Clean machine-readable mode |
| UX-A11Y-01 | Accessible degradation of animation and color |

