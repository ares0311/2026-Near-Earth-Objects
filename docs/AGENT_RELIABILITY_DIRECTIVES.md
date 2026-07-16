# Agent Reliability Directives

Canonical, single source of truth for this project's coding-agent reliability
requirements. This file exists so that **repository state and reproducible
verification outrank agent claims** — a fresh developer or coding agent must
be able to inspect this repository, run the documented checks below, and
independently determine whether required behavior is implemented correctly,
without trusting any agent's unverified say-so.

**Authoritative for both agents used on this project:**
- **Claude Code** reads this file because it is item 10 of `CLAUDE.md`'s
  `MANDATORY SESSION-START PROTOCOL` (enforced via an explicit `Read` tool
  call every session — see `CLAUDE.md`).
- **Codex** reads this file's requirements inline, verbatim, in `AGENTS.md`'s
  `## Agent Reliability Directives (mirrors docs/AGENT_RELIABILITY_DIRECTIVES.md)`
  section, because Codex loads `AGENTS.md` as its working context directly and
  this project does not assume Codex will independently follow a
  read-this-other-file instruction the way Claude Code's tool-enforced
  protocol does (see `docs/AGENT_RELIABILITY_DIRECTIVES.md` §"Claude/Codex
  exposure mechanism" below for why the two differ).

Each requirement below has a stable ID (`REL-01`..`REL-10`) so it can be
traced: **Requirement -> Implementation -> Verification -> Result**. IDs are
never renumbered or reused once assigned; a superseded requirement is marked
superseded in place, not deleted, so history stays intact (see §"Change
discipline").

Every requirement block is delimited by an HTML-comment marker
(`<!-- REQ:REL-XX -->` / `<!-- /REQ:REL-XX -->`) so `Skills/check_directive_parity.py`
can machine-extract it and byte-compare it against the mirror copy in
`AGENTS.md`. Do not edit a requirement's text in one file without editing the
other identically, or `Skills/check_directive_parity.py` will fail loudly.

---

## Claude/Codex exposure mechanism

`CLAUDE.md` uses a numbered, explicitly-enforced `MANDATORY SESSION-START
PROTOCOL` where each step is a literal tool call the agent must make before
any planning happens. `AGENTS.md` (read by Codex) has no equivalent
tool-enforced protocol — it is Standing Rules text loaded wholesale as
context, with `**MANDATORY READ**:` annotations that name other files but
have no mechanical enforcement comparable to Claude Code's `Read`-call
requirement. Because these two mechanisms are not equivalent, this project
does not rely on a bare cross-reference to guarantee Codex exposure. Instead,
every `REL-XX` requirement's full normative text is mirrored verbatim into
`AGENTS.md` itself, and `Skills/check_directive_parity.py` is the drift
detector that keeps the mirror honest.

---

<!-- REQ:REL-01 -->
### REL-01: Fail Loudly

- Never silently swallow a material failure (an error that could change
  whether the operation actually succeeded).
- Never report success when a required operation failed.
- Missing required dependencies, configuration, credentials, inputs, or
  artifacts must produce an explicit, visible failure — not a quiet
  fallback that looks like success.
- Partial success must not be represented as complete success.
- Required CLI/automation entry points must return non-zero exit status on
  any mandatory failure.
- A fallback path must not conceal failure unless the fallback is explicitly
  intended, documented at the call site, and covered by a test proving it
  still surfaces the failure it's falling back from (e.g. logs it, degrades
  a reported status field, etc.) — silence is never acceptable, but a
  documented, tested, visible fallback is.

**Known limitation, explicitly disclosed rather than hidden**: this
codebase's `src/fetch.py` and `src/classify.py` contain pre-existing
`except Exception: pass` blocks (silent-swallow patterns) predating this
directive. Retroactively auditing and fixing each one is out of scope for
introducing this control (it would mean touching core, 100%-covered
production pipeline logic well beyond what was asked, with real regression
risk). Instead, `Skills/check_silent_exceptions.py` catalogues every
existing occurrence in a checked-in allowlist
(`data_selection/silent_exception_allowlist.json`) with a required
justification per entry, and hard-fails on any **new**, unallowlisted
occurrence. This is the "narrow, documented exception" this file requires
elsewhere (see REL-07) applied to REL-01 itself: existing debt is
acknowledged and gated against growing, not silently declared compliant.

**Verified by**: `Skills/check_silent_exceptions.py` (new-occurrence gate).
<!-- /REQ:REL-01 -->

<!-- REQ:REL-02 -->
### REL-02: No Fake Completion

Production code paths (`src/`, `Skills/*.py` used by the pipeline or
operator commands) must not silently contain unresolved:

- Stubs or placeholders standing in for required concrete behavior.
- Hard-coded fake results presented as computed output.
- Required unfinished `TODO`/`FIXME` work left in a path that is supposed to
  be complete.
- `pass` or `NotImplementedError` standing in for required behavior.
- Mocks replacing required production behavior (mocks belong in tests only).
- Functions that report success without performing the required operation.

Legitimate test doubles, abstract interfaces (e.g. `abc.abstractmethod`,
`typing.Protocol`), and intentional, documented extension points are
allowed and must be excluded from the scanner via its narrow allowlist
mechanism, not by weakening the scanner's default behavior.

**Verified by**: `Skills/check_incomplete_implementations.py`.
<!-- /REQ:REL-02 -->

<!-- REQ:REL-03 -->
### REL-03: No Unsupported Completion Claims

Do not claim work is implemented, fixed, working, tested, compliant, or
complete without supporting evidence. Every completion claim must state
which of these it actually is:

- **IMPLEMENTED BUT NOT VERIFIED** — code exists but has not been run
  against a passing check tied to the current repository state.
- **VERIFIED** — code exists AND the canonical verification workflow
  (`Skills/verify_reliability_controls.py`) has passed against the exact
  commit/working-tree state being claimed, per REL-05's freshness rule.

Unknown or unexecuted verification is not success. When in doubt, report
the lower of the two states.

**Verified by**: `Skills/verify_reliability_controls.py`'s freshness record
(REL-05) — a completion claim citing "VERIFIED" must be able to point at a
freshness record matching the current git state.
<!-- /REQ:REL-03 -->

<!-- REQ:REL-04 -->
### REL-04: Lossless Directive Factoring + Claude/Codex Parity

When persistent instructions are restructured (split into smaller files,
moved, or otherwise factored):

- No requirement may disappear.
- No requirement may be weakened.
- Meaning and precedence must be preserved.
- No competing source of truth may be created — exactly one file is
  canonical per requirement family; everywhere else either references it or
  carries an explicitly-labeled, drift-checked verbatim mirror (see
  "Claude/Codex exposure mechanism" above).
- Claude Code and Codex must receive equivalent authoritative requirements,
  verified mechanically, not assumed.

**Verified by**: `Skills/check_directive_parity.py` (mirror-text byte
comparison + presence checks in both `CLAUDE.md` and `AGENTS.md`).
<!-- /REQ:REL-04 -->

<!-- REQ:REL-05 -->
### REL-05: Traceable Implementation Claims + Verification Freshness

For material requirements, it must be possible to determine: **Requirement
-> Implementation -> Verification -> Result.** Use the `REL-XX` IDs in this
file (and analogous IDs for project-specific requirements, e.g. Production
Readiness gate IDs already used in `docs/PRODUCTION_READINESS.md`) as the
stable anchor.

Verification evidence must identify the repository state actually tested,
using the simplest reliable mechanism available: the exact `git rev-parse
HEAD` commit hash, plus whether the working tree was clean
(`git status --porcelain`) at verification time. A prior passing result is
**not** current evidence if:

- The current `HEAD` differs from the recorded commit, or
- The working tree has uncommitted changes to any file the verification
  covers (tracked via `git status --porcelain`), or
- The recorded result predates a change to a file the check covers.

A stale verification result must never be presented as current correctness.

**Verified by**: `Skills/verify_reliability_controls.py --check-freshness`,
reading the record written by a normal run
(`Logs/reports/reliability_verification.json`, local; a compact summary is
promoted to `docs/evidence/reliability/` per this repo's existing
`docs/evidence/` convention when a durable record is needed).
<!-- /REQ:REL-05 -->

<!-- REQ:REL-06 -->
### REL-06: Behavioral Verification, Not Presence

Tests and checks must verify actual behavior via an independent oracle, not
merely that code exists. The following, alone, are **not** sufficient
evidence that behavior works:

- A function exists.
- A module imports without error.
- Expected text appears in source code.
- A command exits successfully without validating its output.
- A mock reproduces the exact behavior supposedly being tested (a test that
  mocks the thing it claims to verify proves nothing about the real thing).
- A test duplicates the implementation's own logic without an independent
  oracle (e.g. a hand-computed expected value, a synthetic fixture with a
  known ground truth, or a round-trip through a real library).

This project's existing test suite already follows this discipline (e.g.
injection-recovery tests inject a *known* synthetic source and check it is
recovered, rather than mocking the detector). New checks introduced by this
directive set follow the same standard — see `tests/test_check_directive_parity.py`
and `tests/test_check_incomplete_implementations.py` for worked examples
(each includes an independent-oracle negative control, not just a
happy-path presence check).

**Verified by**: `Skills/verify_reliability_controls.py`'s `pytest`
stage (existing 100%-branch-coverage gate in `.github/workflows/ci.yml`)
plus the adversarial suite (REL-09).
<!-- /REQ:REL-06 -->

<!-- REQ:REL-07 -->
### REL-07: Lint/Static/Type Enforcement

Reuse this project's existing `ruff` (lint), `mypy` (type-check on `src/`),
and `pytest --cov=src --cov-fail-under=100` (test + coverage) gates exactly
as configured in `pyproject.toml` and `.github/workflows/ci.yml` — do not
add a competing or duplicate toolchain. Mandatory check failures must fail
the overall verification workflow. Do not obtain a passing result by
silently weakening rules, adding broad ignores, excluding failing code, or
suppressing diagnostics. Any necessary exception must be narrow (a single
rule, a single line, or a single file) and documented with a reason at the
point of exception.

**Verified by**: `Skills/verify_reliability_controls.py` (wraps the exact
CI commands) plus `.github/workflows/ci.yml` itself.
<!-- /REQ:REL-07 -->

<!-- REQ:REL-08 -->
### REL-08: Incomplete-Implementation Detection

Use the lightest practical mechanism to detect suspicious incomplete
production code: `NotImplementedError`, production (non-test, non-docstring)
`# TODO`/`# FIXME`/`# XXX` comment markers, and AST-detected
function/method bodies whose entire body is a bare `pass` (excluding
`@abstractmethod`-decorated methods and `typing.Protocol` bodies). Avoid
excessive false positives: test files (`tests/`), `except: pass` handlers
(covered separately by REL-01's `Skills/check_silent_exceptions.py`, a
different failure mode), and explicitly allowlisted extension points are
excluded. Static text/AST scanning supplements behavioral testing (REL-06)
— it does not replace it.

**Verified by**: `Skills/check_incomplete_implementations.py`.
<!-- /REQ:REL-08 -->

<!-- REQ:REL-09 -->
### REL-09: Verification-of-Verification (Negative Controls)

Every critical check introduced by this directive set must demonstrate it
can actually detect failure, not just pass on the current clean repository.
For each critical check, a negative control proves:

- known-good case -> PASS
- known-bad case -> FAIL
- malformed case -> FAIL LOUDLY (clear error, not a silent pass or an
  unhelpful crash)

Negative controls use `tmp_path`-isolated fixtures (real, throwaway
filesystem state created and destroyed by pytest) so they never mutate or
risk this repository's actual tracked files. The directive-parity and
incomplete/silent-implementation controls exercise real files under
`tmp_path` end to end. The verification-freshness controls stub only the
`subprocess.run` git I/O boundary with controlled, exact `rev-parse`/
`status --porcelain` output rather than spinning up a real throwaway git
repository, because this project's sandboxed execution environment was
found, live, to deny `.git/config`/`.git/hooks` writes both outside the
repository root and under pytest's own tmp_path fallback -- a confirmed
environment constraint, not a design preference. The freshness *comparison
logic* itself (`check_freshness`/`_current_git_state`) is still exercised
for real against that controlled input; only the external git process is
stubbed, matching REL-06's "stub the I/O boundary, not the logic under
test" standard.

**Verified by**: `Skills/run_adversarial_verification.py`, which runs the
negative-control test modules and reports a clear PASS/FAIL summary per
control.
<!-- /REQ:REL-09 -->

<!-- REQ:REL-10 -->
### REL-10: Canonical Verification Workflow

Provide one documented, normal-path verification entry point that runs all
applicable mandatory checks and exits non-zero on any mandatory failure:

```bash
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python Skills/verify_reliability_controls.py
```

It covers, in order: directive integrity + Claude/Codex parity (REL-04),
new-silent-exception gate (REL-01), incomplete-implementation scan
(REL-02/REL-08), `ruff check .` (REL-07), `mypy src` (REL-07), the full
`pytest` suite with 100% coverage (REL-06/REL-07), then writes the
freshness record (REL-05/REL-03). A separate adversarial entry point proves
the controls themselves work:

```bash
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python Skills/run_adversarial_verification.py
```

Do not introduce a new task runner for this beyond these two scripts —
they call this project's existing tools (`ruff`, `mypy`, `pytest`,
`git`) directly.

**Verified by**: running both commands above; see
`docs/evidence/reliability/` for the dated record of the first real run.
<!-- /REQ:REL-10 -->

---

## Change discipline

- Adding a new requirement: append the next `REL-XX` ID; never renumber.
- Changing a requirement's text: edit both this file and `AGENTS.md`'s
  mirror in the same commit, identically, then re-run
  `Skills/check_directive_parity.py` before committing.
- Superseding a requirement: mark it `(SUPERSEDED by REL-YY, <date>)` in
  its heading rather than deleting it, matching this project's existing
  "never delete, mark superseded" convention (see `docs/PRODUCTION_READINESS.md`'s
  `DECISION-001` handling in `CLAUDE.md`).
