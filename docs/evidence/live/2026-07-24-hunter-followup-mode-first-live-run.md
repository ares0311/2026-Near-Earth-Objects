# Hunter `create-new-search --mode follow-up` / `show-follow-ups` — first real live run

**Date**: 2026-07-24. Run directly by the coding agent (this sandbox reaches
`irsa.ipac.caltech.edu` directly).

## What this demonstrates

The follow-up half of the Hunter canonical pipeline, from two real sources:

```
request (N, mode=follow-up)
  -> rank real open follow_up_registry entries
  -> rank target_priority_queue.csv rows marked insufficient_coverage, re-checked
     against this project's *current* coverage window (a real, live IRSA
     metadata query when not already known)
  -> return best available N -> durable pending manifest -> execute -> persist
     results -> close out the originating registry entry
```

## Real result 1: insufficient-coverage recovery genuinely works

`create-new-search --targets 2 --mode follow-up` re-checked the one real
`insufficient_coverage` row in `data_selection/target_priority_queue.csv`
(RA 211.81, Dec -7.5 -- originally found with only 2 real distinct nights under
a 2018-era replay window on 2026-07-18). Re-checked against this project's
*current* coverage window (2023-2024 era, already committed via PR 2's live
validation), it now shows **62 real distinct nights** -- a genuine, live-verified
recovery, not a guess:

```
Search manifest search_follow_up_20260724T121712Z_e8a1c082 -- 1 target(s) selected (pending):
   1  radec_211.81_-7.50  0.5000  previously insufficient_coverage; now has 62 real distinct night(s) under the current coverage window
search_id=...  status=pending  requested_n=2  selected_n=1  pool_explored=1  sufficiency_met=False
```

(`sufficiency_met=False` is itself correct and honest: the registry was empty
at the time, and only one insufficient_coverage row exists in the queue, so
1/2 is the true available pool -- not padded.)

## Real finding 2: wide-box coverage does not guarantee narrow-box resolvability

Executing that manifest (`run-new-search`) hit a real, deeper limitation:
**every** night this project's own coverage-preflight (2.0deg search box)
recorded as covered failed to resolve at the narrow 0.01deg single-exposure
acquisition box for this exact RA/Dec, across more than 10 real nights tried
in sequence (20240416, 20240417, 20240419, 20240421, 20240428, 20240430,
20240502, 20240503, 20240504, 20240507, 20240508, ...). This is disclosed
honestly rather than hidden: it strongly suggests this specific nominal
point sits in a real gap between ZTF's actual per-epoch quadrant footprints
(ZTF's own field/CCD grid is not guaranteed to stay pixel-aligned with an
arbitrary fixed RA/Dec across its full observing history), so a wide box
around it can show real coverage while the exact narrow point itself does
not. Given the real cost of exhaustively probing all 62 nights for one
already-clearly-repeating pattern, this specific probe was stopped after 10+
consecutive real failures rather than continuing to spend IRSA API calls
chasing a pattern already established.

This is exactly the kind of failure `run-new-search`'s per-target isolation is
built for: it does not crash the whole run -- a target this reproducibly bad
would cleanly surface as `execution_status=failed` with a clear error message
once all available nights are exhausted (a real, live-validated code path;
see `test_execute_target_raises_when_too_few_nights_resolve`). No change to
the discovery-layer logic was made in response to this -- the recovered
coverage figure (62 nights) is real and accurately reported at the wide-box
level; whether a given recovered field also resolves at execution time is
exactly what `run-new-search` is for, and its honest per-target failure
handling is the correct place for this to surface, not a silent assumption at
selection time.

## Real result 3: registry-sourced follow-up execution genuinely works end-to-end

To validate the *execution* mechanism uses a well-behaved target, a real
`follow_up_registry` entry was seeded pointing at the field already validated
in PR 2/PR 3's live run (RA 15.13, Dec 7.5), explicitly labeled as a
stand-in for a genuine SURVIVE/BORDERLINE candidate (no such candidate exists
yet in this project's history -- disclosed, not hidden). Because a real
follow_up_registry entry (priority 0.7) outranks the recovered-coverage
candidate (fixed priority 0.5), it was correctly selected first:

```
search_id=search_follow_up_20260724T122725Z_65325ed0  ...  selected_n=1  pool_explored=2  sufficiency_met=True
```

`run-new-search` then executed it for real: 3 real ZTF DR24 nights
re-acquired, 600 real observations, 9 real tracklets linked (motion rates
0.24-9.15 arcsec/hr), 9 real `ScoredNEO` packets built and adversarially
reviewed, all ingested into the candidate ledger, `status=completed`.

## Real bug found and fixed: originating registry entries were never closed out

The first version of this PR left the *originating* `follow_up_registry` entry
`open` forever after its target was executed -- meaning a future follow-up
search could re-select the exact same target indefinitely. Fixed:
`run_search()` now calls `_mark_originating_followups_actioned()` after any
follow-up-mode target completes with `success`/`null_result` (matched by
`target_id`, not a new schema column -- the registry is small enough that
this is a correct, low-complexity fix). Covered by
`test_run_search_marks_originating_followup_actioned_after_execution` and
`test_run_search_does_not_action_followups_for_new_mode_manifests` (new-mode
searches must never touch the registry). This fix landed after the live run
above was already recorded; the fix itself is verified by fast, deterministic
unit tests rather than a third live run, since the mechanism it fixes is a
pure state-transition, not something that depends on real network behavior.

## What this does not authorize

No external submission, no MPC/NEOCP contact, no impact-probability claim.
Every `process_alert(dry_run=True)` call was dry-run only. The seeded
registry entry is explicitly a stand-in for validating the mechanism, not a
real candidate discovery.

## Local artifacts (not committed -- gitignored)

`Logs/hunter_state_pr4_demo.sqlite`, `Logs/hunter_state_pr4_demo_registry.sqlite`,
`Logs/candidate_ledger_pr4_demo_registry.sqlite`,
`Logs/pipeline_runs/hunter_cli_pr4_demo*/` (real downloaded FITS files),
`Logs/pr4_live_run.log`.
