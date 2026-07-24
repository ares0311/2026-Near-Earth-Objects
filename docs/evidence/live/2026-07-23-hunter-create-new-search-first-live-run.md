# Hunter `create-new-search --mode new` — first real live end-to-end run

**Date**: 2026-07-23/24. **Command**: `Skills/hunter_cli.py create-new-search --targets 5
--mode new --neo-class all`. Run directly by the coding agent (this sandbox has direct
network access to `irsa.ipac.caltech.edu`), not handed off to the operator.

## What this demonstrates

This is the first real, live exercise of the Hunter PROD closure directive's adaptive
discovery loop end-to-end:

```
request (N=5, mode=new) -> score full planning grid -> check known coverage ->
insufficient -> adaptively expand (real live IRSA coverage-preflight calls) ->
re-score with grown coverage -> sufficiency met -> persist durable pending manifest
```

## Real result

First invocation (`--db "$TMPDIR/..."`) triggered real adaptive expansion because the
combined known coverage (6 fields from the pre-existing `ztf_dr24_new_field_coverage_preflight_v1`
inventory) was insufficient for 5 eligible "new" (never-searched) targets. The CLI:

1. Ranked the full ~580-field planning grid for `--neo-class all` at the current JD.
2. Selected the next 15 top-ranked, not-yet-coverage-checked fields.
3. Wrote a real batch manifest (`data_selection/batch_manifests/hunter_expand_all_r1_766ba194.json`,
   `data_role: metadata_only_coverage_preflight`, bounded to the already-authorized
   2024-09-21 replay-cutoff window).
4. Ran real, live IRSA metadata queries for all 15 fields (6 workers, within the
   documented `MAX_AGGREGATE_IRSA_REQUESTS` ceiling), each returning real distinct-night
   counts (e.g. field `hx1_015p13_p07p50`: 111 real distinct nights; field
   `hx1_022p69_p07p50`: 100 real distinct nights).
5. Merged and committed a real coverage inventory
   (`data_selection/coverage_inventories/hunter_expand_all_r1_766ba194.json`) — 15/15
   fields passed the >=3-distinct-night minimum.
6. Re-scored with the grown combined inventory: 13 eligible "new" candidates found from
   a total explored pool of 21 fields (6 pre-existing + 15 newly checked) — sufficiency
   met (13 >= 5 requested).

The first invocation's only failure was a trivial local path issue (`sqlite3.OperationalError:
unable to open database file` for a `$TMPDIR`-based `--db` path) — unrelated to the
discovery/expansion logic, which had already completed and committed its real evidence
before that final step. Re-running immediately after with a repo-local `--db` path
completed cleanly (no new network calls needed — the just-committed coverage inventory
already sufficed):

```
Search manifest search_new_20260724T023149Z_6372639a -- 5 target(s) selected (pending):

rank  target_id                 score  reason
---------------------------------------------
   1  radec_15.13_7.50         0.7915  measured coverage 111 nights; survey scarcity prior 0.81; pop density 0.53; geometry 0.99 (8.7h vis)
   2  radec_22.69_7.50         0.7888  measured coverage 100 nights; survey scarcity prior 0.84; pop density 0.51; geometry 0.95 (8.7h vis)
   3  radec_225.17_-15.00      0.7826  measured coverage 81 nights; survey scarcity prior 0.80; pop density 0.51; geometry 1.00 (6.1h vis)
   4  radec_209.64_-15.00      0.7790  measured coverage 67 nights; survey scarcity prior 0.85; pop density 0.50; geometry 0.91 (6.1h vis)
   5  radec_31.06_15.00        0.7708  measured coverage 93 nights; survey scarcity prior 0.85; pop density 0.51; geometry 0.86 (9.3h vis)

search_id=search_new_20260724T023149Z_6372639a  status=pending  requested_n=5  selected_n=5  pool_explored=21  sufficiency_met=True
```

The manifest was verified durably persisted (`hunter_state.get_latest_pending_manifest`)
with full provenance: `ranking_policy_digest`, `discovery_pool_size_explored=21`,
`sufficiency_met=true`, and per-target `coverage_inventory_id` linking each selected
target back to its real measured-coverage record.

## What this does not authorize

No data acquisition beyond metadata (no alert archives, no pixel/cutout downloads), no
candidate scoring, no external submission. This is field-selection/manifest-creation
only — `run-new-search` (PR 3) is what will acquire and score real pixel data for these
5 selected targets.

## Committed artifacts from this run

- `data_selection/batch_manifests/hunter_expand_all_r1_766ba194.json`
- `data_selection/coverage_inventories/hunter_expand_all_r1_766ba194.json`

The demo SQLite manifest (`Logs/hunter_state_live_demo.sqlite`) is intentionally not
committed (gitignored `Logs/**`, local-only) — this file documents the real console
output and committed durable artifacts instead.
