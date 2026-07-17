# Active Handoff — ZTF DR24 Motion-Product Pivot

Updated: 2026-07-16
Repository identity: `2026 Near Earth Objects`
Branch: `main`
Merged batch selection: `d81af0a0` (PR #235)
Execution manifest: `b048be9c`
App version: `v0.91.0`

## Operator decision (2026-07-16): motion-product pivot approved

Jerome W. Lindsey III chose Option 1 of the three-way decision below:
**pivot candidate generation to survey detection/image products designed
for motion**, keeping the completed alert-replay work as benchmark/null
evidence. This is now the active ZTF DR24 direction. The immediate next
step taken under this decision was the first live, integrated run of
`Skills/ztf_dr24_bounded_ingest.py --preflight-motion-products` (previously
only manually HEAD-probed): all four products for the one-exposure bounded
verification window (RA 232.6, Dec -8.4, 0.01 deg, JD 2458339.5-2458340.5)
returned HTTP 200, `available: true`, aggregate 27,311,040 bytes, no bodies
downloaded. Evidence:
`docs/evidence/live/2026-07-16-ztf-dr24-motion-product-preflight-first-live-run.md`.
This confirms the checkpointed preflight tool itself, not just the manual
probe.

**Next step completed same day**: the bounded, single-exposure
pixel-extraction pilot named above. `Skills/ztf_dr24_bounded_ingest.py
--pixel-extraction-pilot` downloads exactly one difference image and runs a
minimal numpy/scipy/astropy source detector, converting hits to RA/Dec via
WCS. Real live run on the same verified exposure: 855 pixels genuinely
cleared a 5-sigma threshold, output capped at 200 -- a report bug that
silently hid the true 855 count behind the cap was caught and fixed (per
the standing no-silent-caps rule) before this was recorded, with two new
regression tests. This proves real RA/Dec extraction from DR24 pixels works
end-to-end, independent of `prv_candidates`; it also honestly surfaces that
bad-pixel masking (the already-verified `science_mask` product), peak
deduplication, and PSF-matched photometry are still needed before the
source list is usable for real candidate generation. Evidence:
`docs/evidence/live/2026-07-16-ztf-dr24-pixel-extraction-pilot-first-live-run.md`.

**Masking + deduplication closed same day**: the detector now applies the
exposure's verified `science_mask` (nonzero pixels excluded) and uses
connected-component labeling instead of local-maximum filtering, so one
physical residual spanning several pixels becomes one candidate source.
Real re-run on the same exposure: 855 raw pixel-hits -> 74 after masking ->
71 connected components, untruncated. Masking alone did nearly all the
work; most surviving components are 1-2 pixels (consistent with genuine
near-threshold detections, not artifact blobs). Schema bumped to
`ztf-dr24-pixel-extraction-pilot-v2`. Evidence:
`docs/evidence/live/2026-07-16-ztf-dr24-pixel-extraction-pilot-masking-dedup.md`.
**PSF-shape scoring closed same day — single-exposure arc complete**: the
detector now Pearson-correlates a cutout around each candidate against the
real `difference_psf` kernel (shape consistency, not flux-calibrated
photometry). Real result: the PSF kernel is 25x25 pixels, larger than
assumed when this gap was scoped, so 38 of the 71 v2 candidates were too
close to the image edge for a full cutout. **Of the 33 that could be
scored, none exceed 0.18 correlation** (mean 0.037, median 0.010) -- an
honest null result. A unit test confirms the method itself works (a real
synthetic Gaussian source correlates >0.95 against its own generating
shape), so this is a genuine finding about this exposure's candidates, not
a broken metric: none of them show meaningful evidence of being real point
sources, consistent with noise-level fluctuations right at the 5-sigma
threshold. Schema bumped to `ztf-dr24-pixel-extraction-pilot-v3`. Evidence:
`docs/evidence/live/2026-07-16-ztf-dr24-pixel-extraction-pilot-psf-scoring.md`.

**This completes the single-exposure pixel-extraction pilot arc**
(preflight -> extraction -> masking/dedup -> PSF-shape scoring), each step
closing the disclosed gap from the one before it. **Still not authorized**:
a wider batch, a candidate claim, Gate Z3 resumption, or any external
submission. **The next step is a genuine operator decision, not another
same-exposure refinement**: try this pipeline against a different
exposure/field (this null result may just mean this one night/field had
nothing), build real multi-exposure tracklet linking (the actual next
scientific rung -- consistency across exposures, not just single-exposure
PSF shape), or pause this path here having validated the extraction
mechanics end-to-end on real data.

## Source-native motion-product path initiated

The recommended metadata-first pivot is now implemented without acquiring
pixels. `Skills/ztf_dr24_bounded_ingest.py --emit-motion-product-manifest`
derives the documented DR24 difference-image, science-mask, science-PSF-catalog,
and difference-PSF URLs for each usable (`infobits < 33554432`) exposure. It
marks every product unverified and performs no product download.

A one-exposure live query returned real DR24 metadata. Four HEAD probes
confirmed all planned products with an aggregate size of 27,311,040 bytes
(~26.0 MiB); no bodies were downloaded. Evidence:
`docs/evidence/live/2026-07-16-ztf-dr24-motion-product-manifest.md`.

The bounded, checkpointed HEAD preflight is now implemented and records
availability and byte estimates:
`--preflight-motion-products` defaults to 10 exposures and 4 workers, has hard
caps of 100 exposures and 6 workers, checkpoints every product, and fails
closed on missing/zero-byte/transport-failed products. Its integrated live
invocation was not authorized in the v0.91.0 session, so only the v0.90.99
manual four-HEAD live evidence exists. A later tiny pixel/extraction pilot
still requires an explicit bounded batch decision. Broad alert replay, Gate
Z3, and all external submission remain paused.

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

Validation for v0.91.0: optimized 6x6 broad suite, 1,965 tests in 30 seconds,
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
