# Production Loop Progress Tracker
<!-- Updated each iteration so compaction doesn't erase memory -->

## Session goal (UPDATED 2026-07-01)

Build a **production-capable discovery-paper pipeline**. Production capability
means the software can find, score, reject, review, and package candidate moving
objects from unreviewed archival discovery data with defensible,
industry-standard confidence controls. It does **not** require that the project
has already found a genuinely new NEO.

When a real candidate appears, the separate discovery-event sequence begins:
  1. Pipeline generates full `ScoredNEO` review packets from discovery data.
  2. Adversarial review tries to REJECT each candidate.
  3. Operator (Jerome W. Lindsey III) reviews SURVIVE/BORDERLINE packets.
  4. Approved survivors are packaged for MPC using the documented submission
     protocol.
  5. MPC/NEOCP/Scout provide the external expert review and confirmation path.
  6. A journal paper can document confirmed MPC-designated outcomes.

This tracker must not treat "actually found a new NEO" as a production
readiness prerequisite. A real discovery is an event gate, not the readiness
definition.

## What is already DONE (do not repeat)

- All T1/T2 gap register items: CLOSED (see PRODUCTION_READINESS.md)
- PR #115: adversarial test fixes + ndet cap fix → merged 2026-06-22
- PR #116 and all follow-on WISE diagnostic PRs through v0.90.5 are merged.
- Console output: ALL stage prints now have elapsed + ETA.
- All session-start docs synced through v0.90.5.
- obs-code defaults standardized to `XXX` in all export Skills
- LOOP_PROGRESS.md created as persistent tracker
- **Adversarial review skill**: `Skills/adversarial_review.py` + `tests/test_adversarial_review_skill.py` ✓
- **Production definition**: capability-based P1-P5 gates added to
  `docs/PRODUCTION_READINESS.md`; actual discovery is no longer a readiness
  prerequisite.

## Remaining work (ordered by priority)

### A. Merge PR #116 and follow-on discovery-layer PRs ✓ DONE
- [x] PR #116 merged to main.
- [x] PR #117 merged to main.
- [x] PR #119 merged to main.
- [x] PR #123-#127 merged to main for WISE live-query diagnosis and fixes.
- [x] PR #131 merged to main for fail-closed discovery sweeps, WISE masked
      photometry cleanup, and durable Taurus WISE run evidence.
- Current local `main` is synchronized with `origin/main` at PR #145 before
  the production-capability runbook sync branch.

### H. Integrate adversarial review into the end-to-end workflow ✓ DONE
- Current decision: keep adversarial review as a **separate step**. Run the
  pipeline with `--review-packet-out`, then run `Skills/adversarial_review.py`
  only if the pipeline reports a non-zero full `ScoredNEO` packet count.
- Operator workflow template:
  ```bash
  git pull origin main

  # Bound native numerical libraries to avoid oversubscription on the local Mac.
  export OMP_NUM_THREADS=1
  export OPENBLAS_NUM_THREADS=1
  export VECLIB_MAXIMUM_THREADS=1
  export NUMEXPR_MAX_THREADS=1
  export PYTHONPATH=src

  # Dry-run by default; writes full review packets when tracklets are produced.
  caffeinate -i uv run --python 3.14 python Skills/run_pipeline.py \
    --ra <RA> --dec <Dec> --radius <radius> \
    --start-jd <start_jd> --end-jd <end_jd> \
    --surveys WISE \
    --review-packet-out Logs/reports/<slug>_review_packets.json \
    --output Logs/reports/<slug>_candidates.json

  # Run only if run_pipeline.py reports non-zero full ScoredNEO packets.
  PYTHONPATH=src uv run --python 3.14 python Skills/adversarial_review.py \
    Logs/reports/<slug>_review_packets.json --offline --json
  ```
  Keep alert actions in dry-run mode during discovery sweeps. Real archive
  fetching does not require `--no-dry-run`; MPC submission remains blocked until
  the observatory-code strategy is resolved and `NEO_MPC_SUBMISSION_APPROVED=1`
  is intentionally set with a real non-placeholder MPC code.

### I. Version coherence ✓ DONE (current v0.90.5)
- [x] `src/__init__.py`, `pyproject.toml` → 0.90.5
- [x] `README.md`, `AGENTS.md`, `CLAUDE.md`, `docs/PRODUCTION_READINESS.md`
      describe v0.90.5 state and current production-capability gates.
- [x] Recent PR history through #145 confirms clear forward progress rather
      than repeated reruns of exhausted Taurus diagnostics.

### J. Update docs to reflect discovery paper pathway ✓ DONE
- [x] `docs/MPC_SUBMISSION_POLICY.md`: §Two-Stage Review Process added with full challenge list
- [x] `CLAUDE.md` §Immediate Next Steps: discovery paper goal + 8-step roadmap
- [x] `AGENTS.md` §Handoff notes: discovery paper goal + two-step operator workflow
- [x] `docs/PRODUCTION_READINESS.md`: Production Capability Gates P1-P5 added
      ahead of event-driven Discovery Gates D1-D7.

### K. Production capability prerequisite work
- [x] P1: prove a WISE/NEOWISE, DECam, or TESS discovery path can produce a
      full `ScoredNEO` packet when a valid moving-object signal is present.
      Known-object recovery through the discovery path or a documented
      source-native injection/recovery harness is acceptable.
      **CLOSED 2026-07-02**: `Skills/injection_recovery.py --survey WISE`
      injection/recovery harness through the real detect/link/classify/score
      path, 100% recovery (n=50), new CI job `wise-injection`. Evidence:
      `docs/evidence/prod-loop/2026-07-02-gate-p1-wise-injection-recovery.md`.
- [ ] P2: document quantitative source-native confidence gates for discovery
      data. WISE/DECam/TESS candidates must not rely solely on ZTF-style
      real/bogus evidence.
- [ ] P3: run a no-submission package drill from a P1 packet through
      adversarial review, operator packet generation, and MPC-compatible export.
- [ ] P4: resolve archival WISE/NEOWISE MPC submission authority before any
      live WISE/NEOWISE MPC submission.
- [ ] P5: maintain a compact operator go/no-go flow for the day a real
      candidate appears.

### L. Discovery-event prerequisite work (not required for production readiness)
- [ ] At least 1 real candidate survives adversarial review + operator review.
- [ ] MPC submission is authorized under the recorded source/observatory-code
      protocol.
- [ ] MPC assigns a provisional designation after submission.
- [ ] Independent confirmation from NEOCP follow-up observatories occurs.
- [ ] Only then can a discovery paper claim a confirmed MPC-designated outcome.

## Standing rules reminder (operator commands)
- **OPERATOR ALWAYS RUNS FROM MAIN**: Never give Jerome a command until the relevant PR
  is merged to main and `git pull origin main` is confirmed. This applies even if code
  exists on the feature branch. Commands are blocked until merge.

## One remaining human-gated submission blocker (no code can resolve this)
- **MPC archival WISE authority**: MPC sources document `C51` as the WISE station
  code, ADES as the current submission format, and ADES note `Z` for
  non-survey measurer/pipeline survey astrometry. They do not explicitly
  authorize this independent archival pipeline to submit WISE/NEOWISE
  remeasurements under `C51`. Jerome must obtain written MPC confirmation before
  any live WISE/NEOWISE submission. See `docs/MPC_SUBMISSION_POLICY.md` and
  `docs/mpc_wise_neowise_archival_astrometry_submission.md`.

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
| 13 | 2026-06-28 | PR #136 merged; bounded WISE rerun produced 5200 candidates on only 1 integer-JD night, so seed_pairs=0 and tracklets=0 | Select or probe a WISE field/window that spans at least 2 integer-JD nights after preprocessing |
| 14 | 2026-06-28 | Same Taurus field expanded to 30 days still produced 5206 WISE observations on only night `2458883` | Use WISE cadence-aware probing rather than blindly expanding the same month |
| 15 | 2026-06-28 | Same Taurus field expanded to 195 days still produced only night `2458883` | Probe full-year/mission-era interval or switch to a field/window with known repeated WISE coverage |
| 16 | 2026-06-28 | Same Taurus field expanded to 370 days produced 328022 observations on 8 nights | Shrink radius or select a smaller field while preserving multi-night WISE coverage |
| 17 | 2026-06-28 | Taurus 370-day window at 0.2° produced 12061 observations on 6 nights | Run bounded WISE dry-run pipeline on the 0.2° full-year window from `main` |
| 18 | 2026-06-29 | Bounded 0.2° WISE dry run with `--max-candidates 2000` completed: 12061 rows, 12042 valid sources, 19 tracklets, 0 submission-ready, 35.32s | Export/preserve full `ScoredNEO` review packets and avoid uncapped 12042-candidate all-pairs linking until a scale-aware strategy exists |
| 19 | 2026-06-29 | Offline adversarial review now fails closed on compact pipeline summaries; the WISE cap-2000 report produced 19/19 `REJECT` verdicts for incomplete review packets | Make `run_pipeline.py` write a full adversarial-review input artifact for candidate survivors |
| 20 | 2026-06-29 | `run_pipeline.py --review-packet-out` added and live-validated: rerun produced 21 full `ScoredNEO` packets, 21/21 adversarial `REJECT`, 0 operator-review survivors | Focus D1 on scalable WISE linking and field/tiling strategy; do not rerun uncapped 12042-candidate all-pairs linking |
| 21 | 2026-06-29 | `run_pipeline.py --max-link-seed-pairs` added: default seed-pair budget fails closed before unbounded all-pairs linking; `0` disables only for documented overrides | Implement the actual scale-aware WISE linking/tiling strategy rather than overriding the guard for broad fields |
| 22 | 2026-06-29 | MPC WISE standards note converted into code policy: ADES defaults to `A22`; WISE archival ADES export requires `stn=C51`, ADES note `Z`, and explicit recorded MPC confirmation | Continue D1 scale-aware WISE linking/tiling; submission remains blocked until MPC confirms third-party archival WISE C51 authority |
| 23 | 2026-06-29 | Added `--link-scale-plan-out` so seed-pair budget stops can write top night-pair and sky-cell diagnostics before failing closed | Use the scale plan from the next bounded WISE diagnostic to choose smaller field/window runs; do not override the budget blindly |
| 24 | 2026-06-29 | Operator scale-plan probe produced `11786731` seed pairs over the `1000000` budget; CLI budget stops now exit cleanly with audit/output artifacts instead of an unhandled traceback | Use top night pairs `2459084/2459085` and `2459243/2459244` to choose the next smaller WISE diagnostic |
| 25 | 2026-06-30 | v0.90.3 Taurus support-positive subfields produced review packets but all adversarial results were `REJECT`; root cause was near-stationary/artifact-dominated internal candidates | Do not rerun exhausted Taurus subfields; use non-Taurus WISE field selection or WISE-native filtering/linking improvements |
| 26 | 2026-06-30 | v0.90.4 aligned `detect.py`, `link.py`, and audit motion floors with adversarial review at `0.05 arcsec/hr` | Prevent guaranteed-reject near-stationary packets before review |
| 27 | 2026-06-30 | v0.90.5 selector-generated non-Taurus parent field at RA `209.64`, Dec `-15.0`, radius `0.2` fetched `16582` WISE rows and stopped fail-closed at `27845455` seed pairs | Run support-positive diagnostic subfields from the scale plan, then review packets only if non-empty |
| 28 | 2026-06-30 | Rank 1 v0.90.5 support-positive subfield RA `209.5`, Dec `-14.9`, radius `0.0303` fetched `690` rows, linked `58596` seed pairs, produced `0` tracklets and `0` review packets | Treat this as a valid diagnostic, not a crash; v0.90.6 later closed P1 with a WISE source-native positive-control harness |
| 29 | 2026-07-01 | Production definition updated: readiness means demonstrated capability to find, score, review, reject, and package candidates; an actual new NEO is a discovery event, not a production prerequisite | Close P1/P2 next: discovery-source positive control and source-native confidence policy |
| 30 | 2026-07-02 | Gate P1 CLOSED: WISE-cadence injection/recovery harness added to `Skills/injection_recovery.py` (`--survey WISE`), 100% recovery through the real detect/link/classify/score path, new `wise-injection` CI job, evidence recorded | Work Gate P2: document WISE/DECam/TESS source-native confidence thresholds since archive candidates have no ZTF-style real/bogus score |
| 31 | 2026-07-02 | v0.90.7 handoff prepared: `docs/neo_discovery_agent_brief.md` is authoritative workflow guidance and is reconciled with `docs/MISSION.md`; mandatory reads and Gate P2 now require source verification, no future-catalog leakage, historical replay discipline, pretrained-model audits, and auditable ranker design | Next agent should work Gate P2 first; do not run another live WISE diagnostic or add ZTF/Fink discovery-submission code until the source-native confidence policy exists |
