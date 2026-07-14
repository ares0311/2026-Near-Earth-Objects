# Active Handoff — ZTF DR24 Sharded Portfolio Search

Updated: 2026-07-14
Repository identity: `2026 Near Earth Objects`
Branch: `main`
Merged batch selection: `d81af0a0` (PR #235)
Execution manifest: `b048be9c`
App version: `v0.90.98`

## Latest result and decision gate

Run `56c2348f31302291` completed 3/3 shards in 5m10s: 402,053 scanned,
2,311 retained, 1.1 MB persisted, zero production tracklets, zero sensitivity
tracklets, and a fresh 20/20 control. Cross-batch analysis with run
`017eb50381badb75` gave IEO 147.53 four retained nights and 8,956 seed pairs
but zero production tracklets. Its 70 sensitivity fits are all two-point/
two-night pairs. No candidate proceeds to later gates. Further bulk replay is
now a research decision, not an automatic continuation.

## Historical-context audit and operator decision

The official ZTF Science Data System documentation says `prv_candidates`
contains historical events within 1.5 arcseconds of the triggering alert and
looks back approximately 30 days. ZTF's cautionary notes further explain that
packet histories and `objectId` reuse are position-based and can split or merge
nearby sources. Therefore `prv_candidates` must not be inserted into the
moving-object linker as if it supplied missing tracklet observations.

Decision required before another large transfer:

1. **Recommended:** change candidate generation to survey detection/image
   products designed for motion, keeping the alert replay as benchmark/null
   evidence. This costs more engineering but directly addresses the observed
   mismatch between transient alerts and moving-object discovery.
2. Continue bounded alert replay. This reuses current tooling but accepts the
   measured low yield and another multi-gigabyte transfer with no evidence that
   `prv_candidates` fixes the association gap.
3. Pause the archival search. This avoids more transfer and engineering but
   does not advance the discovery-event gate.

If packet history is retained in future work, use it only as provenance-bound
context or veto evidence after an independent tracklet exists, with explicit
deduplication and no-future-leakage tests.

## Completed sparse-field expansion

`data_selection/batch_manifests/ztf_dr24_sparse_field_expansion_2024_v1.json`
targeted the two fields that remained below three retained nights. Its three
nights (`20231003`, `20231029`, `20240429`) total 19.053230740 GB and provide
98 central-box exposure rows for Aten 81.18 and 88 for IEO 147.53. It is the
minimum-transfer qualifying trio among the 12 highest-exposure candidates
whose archive sizes were HEAD-verified. Run `56c2348f31302291` executed it as
three shards x one worker; raw archives remained streamed/unpersisted and
retained output stayed at 1.1 MB.

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
5. The sparse-field expansion and provenance-bound cross-batch analysis are
   complete. Another bulk replay requires an explicit research decision and a
   newly selected, logged, bounded batch. Gate Z3 remains separately paused.

Validation for v0.90.98: optimized 6x6 broad suite, 1,950 tests in 29 seconds,
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
