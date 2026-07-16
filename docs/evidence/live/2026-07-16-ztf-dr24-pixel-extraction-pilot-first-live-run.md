# ZTF DR24 Pixel-Extraction Pilot — First Live Run

Date: 2026-07-16

Scope: the bounded, single-exposure "tiny pixel-extraction pilot" identified
as the next safe engineering step in
`docs/evidence/live/2026-07-16-ztf-dr24-motion-product-preflight-first-live-run.md`,
under the operator's motion-product-pivot decision (`docs/ACTIVE_HANDOFF.md`).

External submission: none. This validates extraction mechanics only; it does
not produce a candidate, does not touch Gate Z3, and authorizes no wider
batch.

## What was built

`Skills/ztf_dr24_bounded_ingest.py` gained a new `--pixel-extraction-pilot`
mode (requires `--preflight-motion-products`), hard-capped to exactly one
exposure per invocation:

1. Downloads the one verified-available difference image for that exposure
   (reuses the existing bounded retry/checkpoint machinery — no new download
   path).
2. Opens it with `astropy.io.fits` (transparent `.fz` Rice decompression).
3. Computes sigma-clipped background stats (`astropy.stats.sigma_clipped_stats`).
4. Finds local-maximum pixels above a 5-sigma threshold via
   `scipy.ndimage.maximum_filter` (pure numpy/scipy/astropy — no new
   dependency, matching this project's existing minimal-dependency
   preference).
5. Converts detected pixel positions to RA/Dec via the image's own WCS.
6. Reports the **true** count of pixels clearing threshold, not just the
   truncated top-N kept in the output — a bug caught and fixed during this
   session before it shipped (see below).

This is a proof-of-concept extractor, explicitly not a calibrated
PSF-fit photometry pipeline — building that is out of scope for a tiny
validation pilot.

## Bug caught before evidence was recorded

The first live run reported exactly `n_candidate_sources: 200` with no
indication this was a truncated cap rather than the true count. Per this
project's "no silent caps" convention, that's a defect: it would misrepresent
"200 candidate sources exist" when the honest statement is "at least 200, cap
reached." Fixed by adding `n_peaks_above_threshold` (the true pre-cap count)
and `n_candidate_sources_truncated` (explicit boolean) to the report, plus
two new regression tests (`test_detect_sources_in_difference_image_caps_output_count`
now also asserts on the true count; a new
`test_detect_sources_in_difference_image_reports_untruncated_when_under_cap`
covers the non-truncated case). The stale checkpoint was deleted and the
pilot re-run before this evidence was written.

## Real live result

Command:

```bash
caffeinate -i uv run --python 3.14 python Skills/ztf_dr24_bounded_ingest.py \
    --ra 232.6 --dec -8.4 --size-deg 0.01 \
    --start-jd 2458339.5 --end-jd 2458340.5 \
    --emit-motion-product-manifest \
    --preflight-motion-products \
    --pixel-extraction-pilot
```

| Field | Value |
|---|---|
| Exposure (pid) | 585152193615 |
| Downloaded bytes | 7,957,440 (matches the earlier HEAD-verified content length exactly) |
| Downloaded SHA-256 | `d536c474298d528a96d38e5fc13c099c254e3318ee3f4e50fd8e9bf2ccdfdbbf` |
| Image size | 9,461,760 pixels total; 8,304,470 finite (non-NaN) |
| Background median / std | 0.0489 / 11.781 |
| Detection threshold (5-sigma) | 58.95 |
| **Pixels clearing threshold (true count)** | **855** |
| Sources kept in output (cap) | 200 |
| Truncated | true |
| Wall time | 3.4 s (download + extraction) |

Top 3 candidate sources by peak brightness:

| x | y | RA (deg) | Dec (deg) | Peak value | SNR |
|---:|---:|---|---|---:|---:|
| 1758 | 2327 | 232.434940 | -8.571039 | 3744.81 | 317.9 |
| 1376 | 701 | 232.542167 | -8.113288 | 3173.42 | 269.4 |
| 1337 | 3050 | 232.555347 | -8.774079 | 2886.82 | 245.0 |

Offline unit coverage: `test_detect_sources_in_difference_image_finds_injected_point_source`
verifies the detector recovers a synthetic injected point source at its
exact WCS-derived RA/Dec (agreement to 1e-6 deg) before this was trusted
against real pixels.

## Interpretation — proves mechanics, reveals real next-iteration need

This confirms the core claim of the motion-product pivot: real RA/Dec source
positions **can** be extracted directly from a DR24 difference image,
independent of ZTF's own alert pipeline and independent of the
`prv_candidates` association problem that motivated the pivot.

It also surfaces an honest, expected limitation: 855 pixels clearing a plain
5-sigma global threshold on one single-CCD-quadrant difference image is too
many to be individually genuine transient/moving-source detections. The
most likely contributors, in rough order of expected impact:

- No bad-pixel/artifact masking applied yet — the already-verified-available
  `science_mask` product (18.9 MB, downloaded in the earlier preflight
  evidence but not yet used here) flags exactly this.
- No deduplication/clustering of adjacent pixels from the same physical
  residual (a single bright-star subtraction residual can produce several
  neighboring pixels above threshold).
- No cross-reference against the `science_psf_catalog` to reject peaks
  coincident with known bright stars (subtraction residuals cluster there).
- Raw peak value used instead of PSF-matched photometry (via the
  `difference_psf` product), which would suppress non-PSF-shaped artifacts.

None of these are surprising for a first proof-of-concept pilot — they define
concrete next engineering steps if the operator wants to continue toward a
real candidate generator, rather than blocking anything today.

## Decision boundary

This does not authorize a wider batch, a candidate claim, Gate Z3 resumption,
or external submission. It is scoped exactly as described in the prior
evidence file: prove single-exposure pixel extraction works end-to-end
against real IRSA data before considering anything broader.
