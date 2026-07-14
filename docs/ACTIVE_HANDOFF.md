# Active Handoff — ZTF DR24 Sharded Portfolio Search

Updated: 2026-07-14
Repository identity: `2026 Near Earth Objects`
Branch: `main`
Merged batch selection: `d81af0a0` (PR #235)
Execution manifest: `b048be9c`
App version: `v0.90.95`

## Completed acquisition and association

Coverage-qualified run `017eb50381badb75` completed through
`Skills/run_sharded_download.py` as four disjoint archive-night shards with one
worker each. All shard records merged successfully and the shared manifest was
automatically committed and pushed in `b048be9c`.

- Batch: `data_selection/batch_manifests/ztf_dr24_coverage_selected_2024_v1.json`
- Nights: `20240321`, `20240422`, `20240504`, `20240603`
- Verified transfer: 26.670482707 GB; raw archives were never persisted
- Runtime: 10m36s with no service error or rate limiting
- Alerts scanned: 567,025
- Observations retained: 5,416
- Durable checkpoint output: 2.2 MB
- Production association: 0 tracklets at `min_observations=3`
- Sensitivity association: 222 fits, all exactly two observations across two
  nights; all are underconstrained and not candidates
- Fresh isolated control: 20/20 detected, 20/20 linked, 20/20 scored

Five new fields had retained alerts on at least two nights; four had retained
alerts on three nights. The production analyzer loaded 5,026 observations
from those eligible fields, found 669 within-night motion candidates, examined
96,448 seed pairs, and formed zero valid tracklets. No real alert proceeds to
known-object exclusion, classification, scoring, adversarial review, or
submission.

## Where the data and status live

- Query-bound per-night checkpoints, association reports, and fresh control:
  `Logs/pipeline_runs/ztf_alert_archive_portfolio/ztf_dr24_coverage_selected_2024_v1/`
- Parent per-shard logs:
  `Logs/pipeline_runs/sharded_download/017eb50381badb75/`
- Shared file-locked execution manifest:
  `Logs/reports/sharded_download_manifest.jsonl`
- Committed result: `docs/evidence/live/2026-07-14-ztf-coverage-qualified-search-result.md`
- Downloader implementation:
  `Skills/ztf_alert_archive_portfolio.py`

The first sandboxed launch failed only because DNS and `.git/index.lock` were
blocked. The immediately repeated approved launch is the real network run.
Manifest readers select the latest record for each shard, so the earlier failed
record does not invalidate later successful records.

## Status and recovery commands

First verify `.agent-project-id`, branch state, and absence of
`Logs/tier3_pilot.active.json`. Use the repo venv and local uv cache for every
command.

Safe partial status (v0.90.95 infers four shards from the run manifest):

```bash
source .venv/bin/activate
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python \
  Skills/run_sharded_download.py --status \
  --run-id 017eb50381badb75
```

Fail-closed completion check:

```bash
source .venv/bin/activate
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python \
  Skills/run_sharded_download.py --merge \
  --run-id 017eb50381badb75
```

The network command may require the already-approved narrow sandbox exception
for `ztf.uw.edu` and the manifest-only git relay. Do not broaden it.

## Completed analysis and next work

1. The planned coverage-qualified replay is complete and its production result
   is a valid null: zero three-observation tracklets.
2. The 222 two-point sensitivity fits are not candidates and must not enter
   time-aware known-object exclusion or later review stages.
3. The fresh batch-isolated positive control passed 20/20, so the null is not
   explained by a broken detect/link/score chain.
4. `Skills/run_sharded_download.py --status/--merge` now infers non-default
   shard topology from the selected run; legacy manifests without topology
   still require explicit `--shards`.
5. The next research expansion should be selected and logged as a new bounded
   batch rather than silently reusing this completed result. Gate Z3 remains
   separately paused.

Validation for v0.90.95: optimized 6x6 broad suite, 1,943 tests in 27 seconds,
100% coverage across 5,447 source statements; full Ruff and mypy clean; uv
lock and repository artifact-policy checks passed.

## Hard boundaries

- This authorization covers archival search and internal review only.
- Do not submit to MPC/NEOCP, contact NASA/PDCO or another authority, publish an
  alert, claim a discovery, or state an impact probability.
- Never call an internally detected object a confirmed NEO. Use “candidate
  consistent with an NEO orbit” until independent MPC/NEOCP confirmation.
- Gate Z3 remains a separate intentionally paused known-object identity search;
  this portfolio run does not reopen or close Z3.
- Stay inside this git root and below the 100 GB project-data ceiling.
