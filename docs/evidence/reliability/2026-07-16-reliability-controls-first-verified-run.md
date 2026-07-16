# Agent Reliability Controls — First Verified Run

Date: 2026-07-16

Scope: introduces the REL-01..REL-10 reliability directives
(`docs/AGENT_RELIABILITY_DIRECTIVES.md`) and their mechanical verification
(`Skills/check_directive_parity.py`, `Skills/check_silent_exceptions.py`,
`Skills/check_incomplete_implementations.py`,
`Skills/verify_reliability_controls.py`,
`Skills/run_adversarial_verification.py`), per an explicit operator request
to implement verifiable agent reliability controls for both Claude Code and
Codex.

## Normal verification — real, live run

Command:

```bash
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python Skills/verify_reliability_controls.py
```

| Check | Result |
|---|---|
| directive_parity (REL-04) | PASS |
| silent_exceptions (REL-01) | PASS — 22 pre-existing findings, all catalogued in `data_selection/silent_exception_allowlist.json` with individual justifications; 0 new/unallowlisted |
| incomplete_implementations (REL-02/REL-08) | PASS — 0 findings |
| ruff | PASS |
| mypy (src, 18 files) | PASS |
| pytest | PASS — 2021 passed, 2 deselected, 100% coverage (5,447 statements) |

## Adversarial verification — real, live run

Command:

```bash
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python Skills/run_adversarial_verification.py
```

Result: 46/46 negative-control tests passed across all four check modules,
covering known-good/known-bad/malformed cases for every critical control,
plus a live confirmation that the run left the real repository's working
tree unchanged (all fixtures are `tmp_path`-isolated).

## Real bugs found and fixed during this session's own dogfooding

Both caught by the tools verifying themselves, before any evidence was
recorded — not hypothetical:

1. **ruff**: 4 line-too-long violations in the new scripts themselves,
   caught by the first live `verify_reliability_controls.py` run.
2. **pytest segfault (root-caused, not papered over)**: the orchestrator's
   first live run segfaulted partway through the real pytest suite. Root
   cause: missing `PYTHONPATH=src` and native-library thread isolation
   (`OMP_NUM_THREADS=1` etc.) for the pytest subprocess on this macOS
   machine — a failure mode this project's own `CLAUDE.md`/`SYSTEM_PROFILE.md`
   already document for XGBoost/OpenMP. Fixed by passing the documented env
   overrides to the pytest subprocess specifically.
3. **Sandbox constraint discovered live**: this session's sandboxed
   execution environment denies `.git/config`/`.git/hooks` writes both
   outside the repository root and under pytest's own `tmp_path` fallback,
   making real throwaway `git init` fixtures impossible here. The
   freshness/git-state negative controls were redesigned to stub only the
   `subprocess.run` git I/O boundary (not the comparison logic under test),
   and `docs/AGENT_RELIABILITY_DIRECTIVES.md` REL-09 plus its `AGENTS.md`
   mirror were both updated to disclose this honestly rather than leave an
   inaccurate "real git state" claim in place.

## Known limitations, disclosed rather than hidden

- The 22 pre-existing `except Exception: pass` occurrences in
  `src/fetch.py`, `src/classify.py`, and several `Skills/*.py` files are
  catalogued, not fixed. Retroactively auditing/fixing each one was judged
  out of scope for introducing this control (real regression risk against
  100%-covered production pipeline code well beyond what was asked). REL-01
  discloses this explicitly rather than silently declaring the codebase
  compliant.
- `mypy` does not cover `Skills/*.py` (matches this project's existing CI
  scope — `.github/workflows/ci.yml` only runs `mypy src`); the new
  `Skills/check_*.py` scripts are consequently not mypy-gated, consistent
  with every other Skills/ script in this repository.
- The incomplete-implementation and silent-exception scanners are
  AST/tokenize-based static checks (REL-08's "lightest practical
  mechanism"), not a full type-checker or formal-methods tool — they
  supplement, not replace, behavioral testing (REL-06).

## Status

VERIFIED COMPLETE for the scope described above. See the completion report
delivered in-session for the full requirement-by-requirement breakdown.
