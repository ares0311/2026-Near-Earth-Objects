# Production Loop Progress Tracker
<!-- Updated each iteration so compaction doesn't erase memory -->

## Session goal (UPDATED 2026-06-26)

Build a **defensible discovery paper** pipeline:
  1. Pipeline generates scored NEO candidates
  2. Adversarial review agent tries to REJECT each candidate (finds fatal flaws)
  3. Operator (Jerome) reviews survivors
  4. Survivors submitted to MPC → provisional designation → independent confirmation
  5. Journal paper documents the discovery with the MPC designation as proof

This replaces the original "citizen-science production" framing.  The pipeline is
NOT a citizen-science reporting tool — it is a candidate GENERATOR that feeds a
rigorous two-stage review process before any external submission.

## What is already DONE (do not repeat)

- All T1/T2 gap register items: CLOSED (see PRODUCTION_READINESS.md)
- PR #115: adversarial test fixes + ndet cap fix → merged 2026-06-22
- PR #116: docs update + console output ETA fix (run_pipeline.py) → OPEN, CI pending
- Console output: ALL stage prints now have elapsed + ETA (committed d69ed77)
- All session-start docs synced to v0.89.3 (originally done at v0.89.2, version bumped since)
- obs-code defaults standardized to `XXX` in all export Skills
- LOOP_PROGRESS.md created as persistent tracker
- **Adversarial review skill**: `Skills/adversarial_review.py` + `tests/test_adversarial_review_skill.py` ✓

## Remaining work (ordered by priority)

### A. Merge PR #116 and follow-on discovery-layer PRs ✓ DONE
- [x] PR #116 merged to main.
- [x] PR #117 merged to main.
- [x] PR #119 merged to main.
- [x] PR #123-#127 merged to main for WISE live-query diagnosis and fixes.
- [x] PR #131 merged to main for fail-closed discovery sweeps, WISE masked
      photometry cleanup, and durable Taurus WISE run evidence.
- Current local `main` is synchronized with `origin/main` at PR #131.

### H. Integrate adversarial review into the end-to-end workflow
- [ ] Wire `Skills/adversarial_review.py` output into `Skills/run_pipeline.py` (optional post-stage)
  OR document it as a separate post-processing step in `docs/PRODUCTION_READINESS.md`.
- Current decision: keep it as a **separate step** — run pipeline, then pipe the candidates JSON
  through adversarial_review.py before showing anything to the operator.
- Operator workflow:
  ```bash
  git pull origin main
  PYTHONPATH=src uv run python Skills/run_pipeline.py ... --output /tmp/candidates.json
  PYTHONPATH=src uv run python Skills/adversarial_review.py /tmp/candidates.json --json
  ```
  Keep alert actions in dry-run mode during discovery sweeps. Real archive
  fetching does not require `--no-dry-run`; MPC submission remains blocked until
  the observatory-code strategy is resolved and `NEO_MPC_SUBMISSION_APPROVED=1`
  is intentionally set with a real non-placeholder MPC code.

### I. Version bump to v0.89.3 ✓ DONE (2026-06-26)
- [x] `src/__init__.py`, `pyproject.toml` → 0.89.3
- [x] `CHANGELOG.md` v0.89.3 entry added
- [x] `README.md`, `AGENTS.md`, `CLAUDE.md`, `docs/PRODUCTION_READINESS.md` → v0.89.3
- All in PR #116 (same branch)

### J. Update docs to reflect discovery paper pathway ✓ DONE (2026-06-26)
- [x] `docs/MPC_SUBMISSION_POLICY.md`: §Two-Stage Review Process added with full challenge list
- [x] `CLAUDE.md` §Immediate Next Steps: discovery paper goal + 8-step roadmap
- [x] `AGENTS.md` §Handoff notes: discovery paper goal + two-step operator workflow
- [x] `docs/PRODUCTION_READINESS.md`: Discovery Paper Gates D1–D7 added as post-T1/T2 section

### K. Discovery paper prerequisite work (no code, human decisions needed)
- [ ] Jerome must resolve MPC observatory code strategy (still pending — see §TODO in MPC_SUBMISSION_POLICY.md)
- [ ] At least 1 candidate must survive adversarial review + operator review
- [ ] MPC must assign a provisional designation after submission
- [ ] Independent confirmation from NEOCP follow-up observatories
- [ ] Only THEN can a discovery paper be written

## Standing rules reminder (operator commands)
- **OPERATOR ALWAYS RUNS FROM MAIN**: Never give Jerome a command until the relevant PR
  is merged to main and `git pull origin main` is confirmed. This applies even if code
  exists on the feature branch. Commands are blocked until merge.

## One remaining human-gated blocker (no code can resolve this)
- **MPC observatory code**: Jerome must contact MPC to determine how a
  data-analysis pipeline (not an observing telescope) can submit observation
  reports. See `docs/MPC_SUBMISSION_POLICY.md §TODO for Future Agents`.

## Iteration log
| # | Date | What was done | Next action |
|---|------|--------------|-------------|
| 1 | 2026-06-26 | Created tracker; awaiting PR #116 CI | Check CI, merge, sync docs |
| 2 | 2026-06-26 | CHANGELOG v0.89.2 + CONSOLE_OUTPUT_SPEC updated; committed | Merge PR #116; sync CLAUDE.md/AGENTS.md/PRODUCTION_READINESS.md |
| 3 | 2026-06-26 | All doc sync complete; obs-code defaults fixed; versions bumped | Merge PR #116 (waiting for GitHub write rate limit to clear) |
| 4 | 2026-06-26 | Adversarial review skill implemented; discovery paper goal established | Merge PR #116, then open PR #117 for adversarial review; update docs |
| 5 | 2026-06-26 | Discovery Paper Gates D1–D7 added to PRODUCTION_READINESS.md; all J items complete | Merge PR #116 (waiting for GitHub write rate limit to clear) |
| 6 | 2026-06-27 | PR #116-#127 are merged; stale loop item corrected; MPC live submission fail-closed gate added | Run WISE archive discovery sweep from main in alert dry-run mode |
| 7 | 2026-06-27 | Operator WISE sweep `756e0dc7b6be` recorded: 111913 IRSA rows, 85335 observations, 535 candidates, 0 tracklets | Do not rerun same WISE command; fix masked WISE photometry handling and diagnose 0-tracklet linking |
| 8 | 2026-06-28 | PR #131 merged: discovery sweeps fail closed for MPC submission and WISE masked photometry is handled without `nan` conversion | Diagnose why the recorded WISE sweep produced 535 candidates but 0 linked tracklets before asking for another operator run |
| 9 | 2026-06-28 | PR #133 merged: WISE moving-source prefilter + discovery-archive singleton linking; full local pytest after CI coverage fix `1586 passed, 2 deselected`; GitHub CI passed before merge | Run smaller WISE dry-run diagnostic from `main` and record row/candidate/tracklet counts |
| 10 | 2026-06-28 | Smaller WISE diagnostic from `main` at `2a786e18` failed before result retrieval: pyvo 1.9.0 `AsyncTAPJob` has no public `update()` method | Merge pyvo polling compatibility PR, then rerun the smaller WISE dry-run diagnostic from `main`; do not give feature-branch commands |
| 11 | 2026-06-28 | PR #135 merged; post-merge WISE diagnostic completed from `main`: 5206 rows, 5200 candidates, 0 tracklets, dry-run safety intact | Diagnose WISE singleton-candidate linking failure before any repeat live run |
| 12 | 2026-06-28 | Linker rejection diagnostics added and operator-validated locally: targeted pytest `80 passed`, ruff clean, mypy clean | Publish diagnostics PR, wait for CI, merge, then rerun the bounded WISE diagnostic from `main` |
