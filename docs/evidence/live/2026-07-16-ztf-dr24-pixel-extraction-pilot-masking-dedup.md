# ZTF DR24 Pixel-Extraction Pilot — Masking + Deduplication (v2)

Date: 2026-07-16

Scope: closes the two concrete next-iteration gaps named in
`docs/evidence/live/2026-07-16-ztf-dr24-pixel-extraction-pilot-first-live-run.md`
("bad-pixel masking, peak deduplication, and PSF-matched photometry are
still needed before the source list is production-usable"). PSF-matched
photometry remains out of scope for this tiny pilot.

External submission: none. Still a bounded, single-exposure validation
pilot -- no candidate claim, no Gate Z3 resumption.

## What changed

`_detect_sources_in_difference_image` in `Skills/ztf_dr24_bounded_ingest.py`:

1. **Bad-pixel masking**: accepts the exposure's `science_mask` product
   (already verified available in the earlier preflight run, previously
   downloaded but unused). Any pixel with a nonzero mask value is excluded
   from both background statistics and candidate detection. Deliberately
   coarse (any nonzero flag -> excluded) rather than decoding ZTF's
   per-bit mask semantics -- disclosed as a simplification, not overclaimed
   as precise.
2. **Connected-component deduplication**: replaced the v1 local-maximum
   filter with `scipy.ndimage.label` on the post-mask thresholded pixels.
   One physical residual spanning several adjacent pixels now collapses
   into exactly one candidate source (its brightest pixel), instead of
   being counted once per pixel.

`_run_pixel_extraction_pilot` now downloads the science mask automatically
when the same preflight run already verified it available (soft
requirement -- an exposure without a verified mask still runs, reporting
`mask_applied: false` explicitly rather than silently proceeding as if
nothing changed).

Schema bumped to `ztf-dr24-pixel-extraction-pilot-v2` since the underlying
computation changed, not just added fields.

## Real live result — same exposure as the v1 run

Command:

```bash
caffeinate -i uv run --python 3.14 python Skills/ztf_dr24_bounded_ingest.py \
    --ra 232.6 --dec -8.4 --size-deg 0.01 \
    --start-jd 2458339.5 --end-jd 2458340.5 \
    --emit-motion-product-manifest \
    --preflight-motion-products \
    --pixel-extraction-pilot
```

| Metric | v1 (2026-07-16, unmasked, no dedup) | v2 (this run) |
|---|---:|---:|
| Pixels/components clearing threshold | 855 (raw pixels) | 74 pixels -> 71 connected components |
| Reported candidate sources | 200 (capped, truncated) | 71 (untruncated) |
| Masked pixels excluded | n/a | 110,863 |

Masking alone did nearly all the work: 855 -> 74 raw pixel hits once
flagged pixels are excluded, before deduplication even runs. Deduplication
then merged 74 pixels into 71 components — most components are 1-2 pixels
(consistent with genuine near-threshold noise/faint-source detections, not
large artifact blobs), confirming the earlier 855-count was dominated by
masked/flagged-region artifacts, not by one-residual-many-pixels
duplication as originally hypothesized.

Top candidate source: x=1860, y=2233, RA 232.405853, Dec -8.544674,
peak_value 179.74, SNR 15.3, component_size_pixels 2.

## Offline test coverage

New/updated tests in `tests/test_ztf_dr24_bounded_ingest.py`:
- `test_detect_sources_deduplicates_adjacent_pixels_into_one_component` —
  independent-oracle test: a synthetic 3x3 (9-pixel) bright blob must
  collapse to exactly 1 component with `component_size_pixels == 9`.
- `test_detect_sources_excludes_masked_pixels` — a real injected source is
  found without a mask, then confirmed excluded when its exact pixel is
  flagged in a synthetic mask.
- `test_detect_sources_mask_shape_mismatch_raises_loudly` — malformed ->
  fails loudly rather than silently misapplying a mismatched mask.
- `test_run_pixel_extraction_pilot_downloads_mask_when_verified_available`
  / `..._skips_mask_when_not_verified_available` — the soft-requirement
  download logic, both branches.
- `test_run_bounded_ingest_pixel_extraction_pilot_end_to_end` updated to
  mock a real (all-zero) mask response and assert `mask_applied: true`.

Full offline suite (`Skills/verify_reliability_controls.py`): all 6 checks
PASS, 2026 tests passed, 100% coverage (5,447 statements).

## Decision boundary

Still a single-exposure, bounded validation pilot. Does not authorize a
wider batch, a candidate claim, Gate Z3 resumption, or external submission.
PSF-matched photometry (using the already-verified `difference_psf`
product) remains the one disclosed gap before this extractor's output
could inform a real candidate generator.
