# Hunter `run-new-search` — first real live end-to-end run

**Date**: 2026-07-24. Run directly by the coding agent (this sandbox reaches
`irsa.ipac.caltech.edu` directly — no operator hand-off needed).

## What this demonstrates

The full Hunter canonical pipeline, executed for real against a durable, previously
created pending manifest (see `2026-07-23-hunter-create-new-search-first-live-run.md`):

```
load exact pending manifest -> per target: acquire 3 real nights -> convert -> real
link() -> real classify()/fit_orbit()/score() -> real adversarial_review(offline=True)
-> candidate-ledger ingestion -> durable search_run/search_run_targets -> manifest
marked executed
```

## A real bug found and fixed by this live run

The first attempt failed with `could not isolate a single exposure ... after 4
narrowing attempts`. Root cause: the per-night acquisition window used the
coverage-preflight's `size_deg=2.0` search box, which spans multiple ZTF CCD/quadrant
footprints — each quadrant produces its own metadata row at a near-identical `obsjd`,
so no amount of *time* narrowing can isolate "one exposure" when the *sky area* itself
contains several. This project's own prior successful single-exposure pixel-extraction
pilots used `--size-deg 0.01` (see
`docs/evidence/live/2026-07-16-ztf-dr24-pixel-extraction-pilot-first-live-run.md:58`),
not the coverage box size. Fixed by giving `run-new-search`'s acquisition its own
`_DEFAULT_SIZE_DEG = 0.01` constant, distinct from the coverage-preflight's `size_deg`.

## A second real bug found and fixed by this live run

The first (failed) attempt's manifest got permanently marked `executed` even though
the run's `status` was `failed` — because `run_search()` called
`mark_manifest_status(..., "executed")` unconditionally, regardless of outcome. This
violates the Hunter directive's "restart/resume does not corrupt or lose state" and
"failures must be loud and resumable" requirements: a fully/partially failed run would
have been permanently locked out of retry. Fixed: the manifest is only marked
`executed` when the run's `final_status == "completed"`; a `partial`/`failed` run
leaves the manifest `pending`, and re-invoking `run-new-search` on the same
`search_id` resumes the *same* `run_id` (not just for `status="running"` mid-crash,
but also for a completed-but-imperfect `partial`/`failed` pass), retrying only the
targets that were not yet `success`/`null_result`. Covered by new tests
(`test_run_search_resumes_and_completes_after_a_prior_partial_failure`, and the
`partial`/`all_failed` tests now also assert the manifest stays `pending`).

## Real result (corrected run)

```
[run-new-search] executing target radec_15.13_7.50 (15.13, 7.5)
... [real IRSA metadata + preflight + download for 3 real nights: 20230922, 20230924, 20230925] ...
[control] Loaded 600 real observation(s) across 3 real night(s)
[control] preprocess: 600/600 sources passed
[control] link: 9 tracklet(s) formed (min_observations=3)
[control]   tracklet bce73009-...: 3 obs across 3 night(s), arc=2.98d, rate=0.24 arcsec/hr
[control]   tracklet 89f99358-...: 3 obs across 3 night(s), arc=2.98d, rate=9.15 arcsec/hr
  ... (9 tracklets total, motion rates 0.24-9.15 arcsec/hr, all within the accepted window)
[control] Built 9 real ScoredNEO review packet(s) from real pixel-extracted tracklets
[run-new-search] target radec_15.13_7.50: success (9 candidate(s))
search_id=search_new_20260724T064003Z_02d53e70  run_id=run_search_new_20260724T064003Z_02d53e70_9043dde2  status=completed  targets=1  failed=0
```

Verified durable state after the run:
- `search_runs`: `status=completed`, real `git_sha`, real `started_at`/`completed_at`.
- `search_run_targets`: `execution_status=success`, all 9 real candidate IDs, all 3 real acquired nights.
- Candidate ledger: 9 real rows, each `review_status=reject` (adversarial review, offline mode, correctly and conservatively fails the `known_object_epoch_association` challenge for every candidate when no live cached association evidence is supplied — this project's own intentional, existing gate; not something this PR changed).
- Follow-up registry: 0 entries (correct — none of the 9 candidates survived review, so none should be flagged for follow-up).
- Manifest: `status=executed` (correctly retired after a fully `completed` pass).

This matches this project's entire historical evidence trail exactly: every real field
test to date has produced tracklets that fail adversarial review, and this run is
consistent with that well-supported null-result pattern — it is not a discovery, and
does not change this repo's no-discovery-yet status. What it does confirm is that the
full mechanism — acquisition through durable candidate-ledger provenance — now runs
end-to-end automatically via one CLI command, with no manual per-step intervention.

## What this does not authorize

No external submission, no MPC/NEOCP contact, no impact-probability claim. Every
`process_alert(dry_run=True)` call in this run was dry-run only.

## Local artifacts (not committed — gitignored)

`Logs/hunter_state_pr3_demo2.sqlite`, `Logs/candidate_ledger_pr3_demo2.sqlite`,
`Logs/pipeline_runs/hunter_cli_pr3_demo3/` (real downloaded FITS files, ~100MB
aggregate). This file documents the real console output and verified durable-state
contents in their place.
