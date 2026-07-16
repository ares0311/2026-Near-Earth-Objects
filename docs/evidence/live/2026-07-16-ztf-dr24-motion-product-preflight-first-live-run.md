# ZTF DR24 Motion-Product Preflight — First Integrated Live Run

Date: 2026-07-16

Scope: first live invocation of `Skills/ztf_dr24_bounded_ingest.py
--preflight-motion-products` (the checkpointed, hard-capped HEAD-preflight
flag), following the operator's 2026-07-16 decision to pivot ZTF DR24
candidate generation from transient-alert replay (`prv_candidates`) to
survey detection/image products designed for motion.

External submission: none. No pixel or catalog product bodies were
downloaded.

## Why this step

The 2026-07-16 motion-product manifest evidence
(`docs/evidence/live/2026-07-16-ztf-dr24-motion-product-manifest.md`)
verified product availability via four manual HTTP HEAD requests, but the
*integrated* `--preflight-motion-products` flag (checkpointed, hard-capped
at 100 exposures / 6 workers, fails closed on missing/zero-byte/transport-failed
products) had not yet been exercised live — `docs/ACTIVE_HANDOFF.md` recorded
this explicitly as pending. This run closes that gap using the same
already-verified bounded query window, per the operator's approval of the
motion-product pivot as the path forward.

## Command

```bash
caffeinate -i env UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python Skills/ztf_dr24_bounded_ingest.py \
    --ra 232.6 --dec -8.4 --size-deg 0.01 \
    --start-jd 2458339.5 --end-jd 2458340.5 \
    --emit-motion-product-manifest \
    --preflight-motion-products
```

## Result

The bounded IPAC metadata query reused the existing checkpoint from the
2026-07-16 manifest evidence (run `3d28311a660d`, unchanged query
parameters -> same content hash, no new network call for that stage). The
`--preflight-motion-products` stage then ran fresh, live HTTP HEAD requests
against all four product URLs for the one exposure in that window:

| Product | HTTP | Content length | Checked at (UTC) |
|---|---:|---:|---|
| Difference image | 200 | 7,957,440 bytes | 2026-07-16T11:38:33.604808+00:00 |
| Difference-image PSF | 200 | 5,760 bytes | 2026-07-16T11:38:33.618157+00:00 |
| Science mask | 200 | 18,941,760 bytes | 2026-07-16T11:38:33.636427+00:00 |
| Science PSF catalog | 200 | 406,080 bytes | 2026-07-16T11:38:33.642424+00:00 |
| **Aggregate** | | **27,311,040 bytes (~26.0 MiB)** | |

All four `available: true`, `error: null`. Byte counts match the earlier
manual four-HEAD probe exactly, confirming both the underlying products are
stable and the automated preflight path reproduces the manual verification
correctly. Checkpoint written to
`Logs/pipeline_runs/ztf_dr24_bounded_ingest/3d28311a660d/motion_product_preflight.json`
(gitignored `Logs/**`, not committed raw).

Console output:

```text
[resume] run 3d28311a660d: checkpoint and raw response already present, skipping fetch
[preflight] 1/4 585152193615:difference_image: HTTP 200, bytes=7957440  elapsed 0m01s  ETA 0m03s
[preflight] 2/4 585152193615:difference_psf: HTTP 200, bytes=5760  elapsed 0m01s  ETA 0m01s
[preflight] 3/4 585152193615:science_mask: HTTP 200, bytes=18941760  elapsed 0m01s  ETA 0m00s
[preflight] 4/4 585152193615:science_psf_catalog: HTTP 200, bytes=406080  elapsed 0m01s  ETA 0m00s
[ingest] Planned source-native products for 1 exposure(s); availability verified by HEAD preflight and no products were downloaded
[ingest] Parsed 1 rows across 1 distinct night(s), 1 distinct field(s)  elapsed 0m01s
[ingest] Distinct real nights (YYYYMMDD): ['20180809']
[ingest] Wrote Logs/pipeline_runs/ztf_dr24_bounded_ingest/3d28311a660d/sample_ingest_report.json
```

## Decision boundary

This confirms the checkpointed preflight tool itself works end-to-end
against the live IRSA service, on a single-exposure bounded window. It does
not authorize pixel download, a candidate claim, Gate Z3 resumption, or any
external submission. The next safe engineering step is a separately scoped,
explicitly bounded tiny pixel-extraction pilot (single exposure, one
difference image) to validate that a source-native motion extractor can be
built against this product family before any wider batch. Broad alert
replay remains paused; Gate Z3 remains paused.
