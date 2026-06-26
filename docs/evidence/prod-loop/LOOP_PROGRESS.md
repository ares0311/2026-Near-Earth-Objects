# Production Loop Progress Tracker
<!-- Updated each iteration so compaction doesn't erase memory -->

## Session goal
Drive the project from its current citizen-science production state to the
point where no further autonomous code work remains — then exit and hand off
to Jerome for the one human-gated decision (MPC observatory code / escalation path).

## What is already DONE (do not repeat)
- All T1/T2 gap register items: CLOSED (see PRODUCTION_READINESS.md)
- PR #115: adversarial test fixes + ndet cap fix → merged 2026-06-22
- PR #116: docs update + console output ETA fix (run_pipeline.py) → OPEN, CI pending
- Console output: ALL stage prints now have elapsed + ETA (committed d69ed77)

## Remaining work (ordered by priority)

### A. CI / PR #116
- [ ] Wait for CI on PR #116; merge if green; fix if red
- Status: CI running as of session start

### B. CLAUDE.md + AGENTS.md sync
- [ ] Update handoff state to reflect console output fix (PR #116 scope changed)
- [ ] Bump version to v0.89.2 after merge
- [ ] Add console output fix to key changes block

### C. PRODUCTION_READINESS.md
- [ ] Add dated note that all console prints now include elapsed+ETA (system directive)
- [ ] Confirm T2-B section mentions console output compliance

### D. MPC escalation path
- [ ] Review docs/MPC_SUBMISSION_POLICY.md §TODO section
- [ ] Assess whether any CODE work can advance this (e.g. better escalation notice,
      observatory-code application instructions, alternative submission flows)
- Human decision required: Jerome must decide observatory code strategy

### E. CHANGELOG.md
- [x] Add v0.89.2 entry for console output fix — DONE

### F. README.md
- [ ] Check if README is stale vs current v0.89.x state

### G. CONSOLE_OUTPUT_SPEC.md
- [x] Updated to document per-stage elapsed format, per-survey fetch loop, per-tracklet ETA — DONE

## Iteration log
| # | Date | What was done | Next action |
|---|------|--------------|-------------|
| 1 | 2026-06-26 | Created tracker; awaiting PR #116 CI | Check CI, merge, sync docs |
| 2 | 2026-06-26 | CHANGELOG v0.89.2 + CONSOLE_OUTPUT_SPEC updated; committed | Merge PR #116; sync CLAUDE.md/AGENTS.md/PRODUCTION_READINESS.md |

