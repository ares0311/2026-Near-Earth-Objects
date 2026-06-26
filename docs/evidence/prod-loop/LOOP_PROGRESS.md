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
- All session-start docs synced to v0.89.2
- obs-code defaults standardized to `XXX` in all export Skills
- LOOP_PROGRESS.md created as persistent tracker
- **Adversarial review skill**: `Skills/adversarial_review.py` + `tests/test_adversarial_review_skill.py` ✓

## Remaining work (ordered by priority)

### A. Merge PR #116
- [ ] Un-draft PR #116 and merge to main (still blocked by GitHub write rate limit)
- Status: write rate limit still active as of latest check.
- Branch `claude/general-session-rvaEE` has 13 commits ahead of main.
- DO NOT give any operator commands until PR #116 is merged.

### H. Integrate adversarial review into the end-to-end workflow
- [ ] Wire `Skills/adversarial_review.py` output into `Skills/run_pipeline.py` (optional post-stage)
  OR document it as a separate post-processing step in `docs/PRODUCTION_READINESS.md`.
- Current decision: keep it as a **separate step** — run pipeline, then pipe the candidates JSON
  through adversarial_review.py before showing anything to the operator.
- Operator workflow:
  ```bash
  git pull origin main
  PYTHONPATH=src uv run python Skills/run_pipeline.py ... --no-dry-run > /tmp/candidates.json
  PYTHONPATH=src uv run python Skills/adversarial_review.py /tmp/candidates.json --json
  ```

### I. Version bump to v0.89.3 after adversarial review merges
- [ ] Bump `src/__init__.py`, `pyproject.toml`, and all doc version headers
- [ ] Add CHANGELOG.md entry for v0.89.3 (adversarial review)
- [ ] Open new PR for adversarial review + version bump

### J. Update docs to reflect discovery paper pathway
- [ ] `docs/MPC_SUBMISSION_POLICY.md`: add §Adversarial Review section describing two-stage process
- [ ] `CLAUDE.md` + `AGENTS.md`: update "Immediate Next Steps" to reflect discovery paper goal
- [ ] `docs/PRODUCTION_READINESS.md`: add adversarial review as a new production gate

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
