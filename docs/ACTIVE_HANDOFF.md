# Active Handoff — ZTF DR24 Sharded Portfolio Search

Updated: 2026-07-14
Repository identity: `2026 Near Earth Objects`
Branch: `main`
Merged implementation: `20576cb4` (PR #231)
App version: `v0.90.92`

## Completed acquisition

The operator explicitly authorized a bounded ZTF DR24 archival search. The
acquisition run ID `0b381aac323c0f28` completed through
`Skills/run_sharded_download.py` as six disjoint archive-night shards with one
worker each (six aggregate UW streams). All shard records merged successfully;
the shared manifest was automatically committed and pushed in `226d4aee`.

Batch source of truth:

- `data_selection/batch_manifests/ztf_dr24_portfolio_2024sep_v1.json`
- Six nights: `20240910`, `20240911`, `20240914`, `20240915`, `20240916`,
  `20240919`
- Portfolio: six new Aten/IEO fields, three follow-up fields, one post-ingest
  moving-source injection control
- Verified network transfer: 38.98 GB
- Persistent output budget: at most 1.0 GB; raw tar archives are streamed and
  are never stored

The run finished in 9m48s without a rate-limit or service error. It scanned
793,005 alert packets and retained 1,211 observations in only these
field/night cells:

- `followup_aten_097p42_p22p50`: 517 on `20240911`, 299 on `20240919`
- `followup_ieo_139p76_p15p00`: 71 on `20240911`, 128 on `20240919`
- `followup_aten_089p30_p22p50`: 154 on `20240919` only
- `new_ieo_147p53_p15p00`: 42 on `20240919` only

Every other field/night cell retained zero. Only the first two follow-up
fields have observations on two nights and are eligible for immediate
multi-night linking. The single-night new-field observations are real acquired
data but cannot satisfy the reportable-tracklet requirement. Do not describe
the uncovered new-field cells as searched scientific nulls.

## Where the data and status live

- Query-bound per-night checkpoints and observations:
  `Logs/pipeline_runs/ztf_alert_archive_portfolio/ztf_dr24_portfolio_2024sep_v1/`
- Parent per-shard logs:
  `Logs/pipeline_runs/sharded_download/0b381aac323c0f28/`
- Shared file-locked execution manifest:
  `Logs/reports/sharded_download_manifest.jsonl`
- Committed acquisition rationale:
  `data_selection/data_selection_decision_log.md`
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

Safe partial status:

```bash
source .venv/bin/activate
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python \
  Skills/run_sharded_download.py --status \
  --run-id 0b381aac323c0f28 --shards 6
```

All shards are complete, so this resume command should report that completed
shards are already satisfied. Use it only if checkpoint or manifest audit
finds a real inconsistency:

```bash
source .venv/bin/activate
UV_CACHE_DIR=.uv-cache caffeinate -i uv run --no-sync --python 3.14 python \
  Skills/run_sharded_download.py \
  --script Skills/ztf_alert_archive_portfolio.py \
  --shards 6 --workers 1 --estimated-download-gb 1.0 --resume -- \
  --batch-manifest \
  data_selection/batch_manifests/ztf_dr24_portfolio_2024sep_v1.json \
  --out-dir Logs/pipeline_runs/ztf_alert_archive_portfolio \
  --min-rb 0.5 --max-per-field-night 5000
```

Fail-closed completion check:

```bash
source .venv/bin/activate
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python \
  Skills/run_sharded_download.py --merge \
  --run-id 0b381aac323c0f28 --shards 6
```

The network command may require the already-approved narrow sandbox exception
for `ztf.uw.edu` and the manifest-only git relay. Do not broaden it.

## Completed analysis and next work

1. The acquisition audit is complete: all six shards succeeded, checkpoint
   totals equal 1,211 observations, and durable output is only 548 KB.
2. `Skills/analyze_ztf_alert_archive_portfolio.py` now safely adapts the
   portfolio schema without treating ZTF survey field numbers as object IDs.
   Production association found zero valid three-observation tracklets. The
   100 two-point sensitivity fits are underconstrained and not candidates.
3. The post-ingest control passed 20/20 detection, linking, and scoring.
4. No known-object, scoring, or adversarial-review work is pending for this
   batch because the production tracklet set is empty.
5. Next build a metadata-only field/night coverage inventory and select at
   least three populated archive nights per new field before another bulk
   transfer. Reuse the bounded sharded downloader only after that preflight.

## Hard boundaries

- This authorization covers archival search and internal review only.
- Do not submit to MPC/NEOCP, contact NASA/PDCO or another authority, publish an
  alert, claim a discovery, or state an impact probability.
- Never call an internally detected object a confirmed NEO. Use “candidate
  consistent with an NEO orbit” until independent MPC/NEOCP confirmation.
- Gate Z3 remains a separate intentionally paused known-object identity search;
  this portfolio run does not reopen or close Z3.
- Stay inside this git root and below the 100 GB project-data ceiling.
