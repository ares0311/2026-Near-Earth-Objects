# Phase 0 gate authority, Phase 1 closure, and the Phase 2 PTY blocker

**Date (UTC):** 2026-08-01
**Repository:** NEOHunter (`2026-Near-Earth-Objects`)
**Commit at session start:** `000e0c2421c8ca15807fe46d3426bc02654573b5`
**Contract:** `HUNTER-PROD-2026-07-30.3` · **CLI/UX spec:** `HUNTER-CLI-UX-2026-07-30.3`

---

## 1. Headline

**PRIMARY PHASE GATE (Phase 2): PASS.**

The Phase 2 primary gate did not exist at session start. It was built
(`Skills/hunter_pty_gate.py`) and initially reported `NOT_EXECUTED` because PTY
allocation was denied. That turned out **not** to be a missing capability — see
§3. Once the real cause was found, the gate passed **57 assertions across 3 fresh
processes**, and `LAUNCH-04`, `CLI-01`, and `CLI-02` are now VERIFIED against a
bound gate execution.

Phases 0, 1, and 2 are closed. Four real implementation defects were found and
repaired — three by static evidence, one by the gate itself.

---

## 2. Governance findings (Phase 0)

### 2.1 The PROD gate could not finish

Running `Skills/hunter_prod_check.py` timed out repeatedly. Timing each check
individually located the cause precisely:

```
sibling-write-isolation            PASS            321.86s
```

`check_sibling_write_isolation` used `Path.rglob("*")` over the repository root.
`rglob` cannot skip a subtree — it descended fully into `.venv`, `.git`,
`.uv-cache`, and the data directories on a cloud-synced volume, then discarded
those results afterwards.

Repaired with `os.walk` and in-place pruning of `dirnames`. **This changes which
paths are visited, never which paths are reported** — every pruned directory was
already excluded from the result set.

| | before | after |
|---|---|---|
| elapsed | 321.86 s | 3.46 s |
| status | PASS | PASS |
| `offender_count` | 0 | 0 |

Raw evidence: `Logs/prod_closure/check_timing.log`, `Logs/prod_closure/sibling_fix.log`.

### 2.2 `VERIFIED` was agent-authored

`Skills/hunter_prod_state.py::record_evidence` accepted `status="VERIFIED"` with
hand-written strings. Nothing bound the claim to an executed gate. The Hunter
execution directive requires the opposite: only a deterministic gate runner may
produce `VERIFIED`.

Repair — `VERIFIED` is now **gate-authored only**:

- `run_gate()` executes a command and returns an unforgeable record: gate
  command, gate file path, gate SHA-256, real exit status, code identity
  (commit + `+dirty` marker), timestamp.
- `record_evidence()` raises unless `VERIFIED` carries such a record with
  `exit_status == 0` **and** every `raw_evidence_path` exists on disk.
- `validate_state()` re-checks all of the above on every load, and additionally
  re-hashes each gate file: **if a gate changed after it passed, the stale PASS
  is reported rather than inherited.**

Agent-authored statuses are limited to `UNVERIFIED`, `BLOCKING`, `IN_PROGRESS`,
`IMPLEMENTED_NOT_VERIFIED`, `NOT_APPLICABLE`.

**The repair immediately caught five pre-existing violations:**

```
LAUNCH-01: VERIFIED without a bound gate result.
LAUNCH-02: VERIFIED without a bound gate result.
LAUNCH-03: VERIFIED without a bound gate result.
WS-01:     VERIFIED without a bound gate result.
WS-02:     VERIFIED without a bound gate result.
```

All five were demoted to `IMPLEMENTED_NOT_VERIFIED` with their original evidence
text preserved. Raw evidence: `Logs/prod_closure/ledger_validate.log`.

---

## 3. Phase 2: the PTY block, and what it actually was

### 3.1 Resolution

**The wrapper script the sandbox exclusion names did not exist in this
repository.** `~/.claude/settings.json` already contained:

```json
"excludedCommands": [
  "bash scripts/run_pty_gate.sh*",
  "bash scripts/run_acceptance.sh*"
]
```

`sandbox.excludedCommands` runs a command outside the sandbox. The sibling
Hunters have `scripts/run_pty_gate.sh`; this repository had no `scripts/`
directory at all, so the exclusion matched nothing and every attempt ran
sandboxed, where PTY allocation is denied.

Adding `scripts/run_pty_gate.sh` — same path, same convention as the siblings —
resolved it with **no settings change**. This is the "one solution across all
three repositories" the operator asked for.

Result:

```
bash scripts/run_pty_gate.sh --runs 3
GATE STATUS: PASS          57 assertions, 3 fresh processes
```

Every assertion, from real key bytes only: startup reaches a prompt; 33 distinct
animation frames; all six NEO motifs; product name **and** version; prompt
follows the animation; a bare `/` offers all seven commands **with no Enter**;
palette items carry descriptions; arrow keys repaint the selection;
`/New-Search` opens guided fields; an invalid target count is rejected inline
without executing; corrected input yields the resolved-action preview;
cancellation returns to the shell; `/Help` lists the commands; `/Exit` exits 0;
no overflow at 40, 100, or 200 columns; no ANSI in redirected or machine mode.

### 3.2 A second sandbox property, measured

`hunter_prod_check` cannot run the gate itself. The exclusion applies to the
command Claude Code launches; a subprocess spawned by an already-sandboxed
process **inherits the sandbox**. Measured directly: the identical command exits
0 launched on its own, and reports PTY-denied when spawned from `prod_check`.

So `prod_check` consumes the gate's report and fails closed on staleness — if any
exercised source file (`hunter_shell.py`, `hunter_ux/*.py`, `hunter_commands.py`,
`hunter_pty_gate.py`) is newer than the report, the check reports `NOT_EXECUTED`
rather than inheriting a PASS for code that has since changed.

### 3.3 The original diagnosis, retained

This is what was observed before the cause was found. It was accurate about the
symptom and wrong about the conclusion — the capability was never missing.

The gate must spawn the installed console script in a **real PTY** and drive it
with real keystrokes. Every route to a PTY is denied here:

```
DENIED  os.openpty()                 -> PermissionError: [Errno 1] Operation not permitted
DENIED  os.posix_openpt(os.O_RDWR)   -> PermissionError: [Errno 1] Operation not permitted
DENIED  open('/dev/ptmx')            -> PermissionError: [Errno 1] Operation not permitted

/dev/ptmx exists: True
```

`/dev/ptmx` exists, so this is a sandbox policy denial, not a missing device.
Raw evidence: `Logs/prod_closure/pty_capability.log`.

**No substitute was ever used.** The directive names *"mocked terminal for a real
PTY"* and *`"/"` followed by Enter for `"/"` without Enter* as forbidden
substitutions, and UX-CMD-01 is specifically about what the terminal does with a
single `/` byte **before** Enter. A pipe cannot demonstrate it. The gate detected
the denial and reported `NOT_EXECUTED` with a nonzero exit rather than degrading —
which is what kept the question open until the real cause was found.

---

## 4. Implementation defects found and repaired

These were found by static evidence, are unrelated to the sandbox, and are
repaired. The PTY gate is what will verify them end to end.

### 4.1 Guided entry and the action preview had no production caller

```
$ grep -rn "run_guided_entry" Skills src tests
Skills/hunter_ux/palette.py:233:def run_guided_entry(        <- definition
tests/test_hunter_ux_units.py:431,444,454,464                <- tests only

$ grep -rn "render_preview\|ResolvedAction" Skills src tests
Skills/hunter_ux/preview.py:45,83                            <- definitions
tests/test_hunter_shell.py:627,640                           <- tests only
tests/test_hunter_ux_golden.py:138,150                       <- tests only
```

Both were fully implemented, fully unit-tested, and **unreachable by an
operator**. `hunter_shell.execute_slash_command` never called either. This is
exactly the condition contract PIPE-02 forbids ("code reachable only through
tests or direct imports"), and the golden tests covering them were the forbidden
substitution of a renderer test for an operator-reachable path.

Repaired: `execute_slash_command` gained interactive `read_field` and `confirm`
hooks, supplied by `run_interactive`. A command invoked without its required
argument now opens guided entry (UX-IN-01/02/03); a manifest-freezing command now
renders the resolved-action preview and waits for confirmation (spec §8). The
scripted `--command` surface is unchanged and still answers with an actionable
message rather than blocking on a prompt.

### 4.2 The startup banner reported no product version

`identity_lines()` rendered only a subtitle. Phase 2 requires product name *and*
version. Repaired to read the running version from installed distribution
metadata (`importlib.metadata`), reporting `unknown` for an uninstalled checkout
rather than guessing. Both affected goldens were made version-stable so a routine
release does not break them.

### 4.3 Regression coverage

`tests/test_hunter_shell_interaction_wiring.py` — 16 tests, all driving
`hunter_shell` rather than the UX modules, because a test importing `palette`
directly would have passed against the broken code and proved nothing.

---

## 5. Coverage denominator (NEO-FIELD-02, CLAIM-02)

CI measured `--cov=src` alone while the canonical orchestrator
(`Skills/hunter_cli.py`) and operator shell (`Skills/hunter_shell.py`) ran
unmeasured — the exact omission CLAIM-02 forbids.

Measured production runtime denominator (`.coveragerc.production`):

```
measured files      32
statements        7663
covered           7521
missing            142
aggregate        98.00%

below 100%:
  Skills/hunter_cli.py            87.06%   95 uncovered
  Skills/hunter_shell.py          86.36%   30 uncovered
  Skills/hunter_ux/palette.py     93.08%   11 uncovered
  Skills/hunter_ux/registry.py    97.52%    3 uncovered
  Skills/hunter_ux/animation.py   97.96%    2 uncovered
  Skills/hunter_ux/theme.py       97.87%    1 uncovered
```

**Every `src/` module is at 100%.** The residual gap is entirely in the `Skills/`
production runtime, and a substantial part of it is TTY-only code that the PTY
gate is what would exercise.

CI now measures the real denominator with a floor of 98 — the measured value, not
a round number — plus `Skills/check_coverage_denominator.py`, which fails if any
`src/` module drops below 100%, so the broader floor cannot mask a regression
there.

**Claim, stated precisely:** *98.00% statement coverage of the production runtime
denominator (src/ plus the orchestrator, shell, and interaction layer); 100% of
`src/`.* The previously implied "100% production coverage" was not true.

---

## 6. Repository-native PROD gate

```
executed 17  passed 14  failed 3  NOT EXECUTED 1
```

| Status | Check |
|---|---|
| NOT_EXECUTED | `interactive-pty-operator` — PTY allocation denied |
| FAIL | `readme-conformance` — Phase 7, correctly not started (gated behind a zero-exit Phase 6) |
| FAIL | `real-data-evidence-freshness` — Phase 5 not reached |
| FAIL → PASS | `coverage-denominator` — closed in §5 |
| PASS | the remaining 14, including `execution-surfaces` and `installed-launch` |

Raw evidence: `Logs/prod_closure/prod_check_final.json`.

---

## 7. A fourth defect, found by the gate

At 40 columns the startup banner and `/Help` overflowed — 19 lines exceeded the
terminal width. The block-letter banner is 47 columns wide and command summaries
are full sentences, so both wrapped, and a wrapped palette entry visually merges
with the next one.

Repaired: `theme.fit()` truncates with a visible marker (spec §11, UX-TABLE-01);
`identity_lines()` drops the block banner entirely below its own width in favour
of a one-line identity, because half a letterform is noise rather than identity;
`registry.describe()` and `help_text()` take a width and are given it by the
shell and the palette.

This is what the gate is for. Three of this session's four defects were invisible
to the test suite, which passed throughout.

---

## 8. Requirement status after this session

| Requirement | Status | Gate |
|---|---|---|
| WS-01, WS-02 | IMPLEMENTED_NOT_VERIFIED | demoted in §2.2; no gate isolates them |
| LAUNCH-01/02/03 | VERIFIED | `verify_hunter_distribution.py --surface both`, exit 0 |
| LAUNCH-04, CLI-01, CLI-02 | VERIFIED | `scripts/run_pty_gate.sh --runs 3`, 57 assertions |
| CLAIM-02 | VERIFIED | `check_coverage_denominator.py`, exit 0 |
| PIPE, IDENT, DISC, RANK, DUR, E2E, README | UNVERIFIED | gates not yet built |

`prod-check`: **executed 18, passed 16, failed 2, NOT EXECUTED 0.**

The two failures are `readme-conformance` (Phase 7, which by directive may not
begin until Phase 6 exits zero) and `real-data-evidence-freshness` (Phase 5, not
reached). Both are correctly open, not overlooked.

Full suite: **2478 passed**. Production coverage 98.07%, every `src/` module at
100%.

---

## 9. Honest limitations

- No requirement was marked `VERIFIED` on the strength of anything written in
  this document. The ledger accepts `VERIFIED` only from a bound gate execution
  that exited zero, with the gate's content hash and the code identity recorded.
- `WS-01` and `WS-02` remain `IMPLEMENTED_NOT_VERIFIED`. They were demoted in
  §2.2 and no gate isolates them, so they were not re-established.
- Phases 3, 4, 5, 6, and 7 were not entered. Their gates do not exist and are
  listed in the ledger's `gate_lock.not_yet_created`.
- **The sibling repositories were never read.** Filesystem access to them is
  still denied, so nothing here has been checked against them. Contract
  IDENT-01/02/03 and README §4 depend on that comparison and cannot be verified
  until it is possible.
- No commit, push, branch, or PR was made. No sibling repository was written.
