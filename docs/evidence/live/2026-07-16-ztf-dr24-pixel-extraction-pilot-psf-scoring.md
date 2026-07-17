# ZTF DR24 Pixel-Extraction Pilot — PSF-Shape Scoring (v3)

Date: 2026-07-16

Scope: closes the last disclosed gap from
`docs/evidence/live/2026-07-16-ztf-dr24-pixel-extraction-pilot-masking-dedup.md`
("PSF-matched photometry remains the one disclosed gap"). This is a PSF-shape
*consistency* score (correlation against the real PSF kernel), not
flux-calibrated PSF photometry -- disclosed as the lighter-weight
implementation it actually is, not overclaimed as a full photometric
pipeline.

External submission: none. Still a bounded, single-exposure validation
pilot -- no candidate claim, no Gate Z3 resumption.

## What changed

`_detect_sources_in_difference_image` accepts an optional `psf_fits_bytes`
(the exposure's `difference_psf` product). For each candidate source, a
cutout of the difference image centered on it (sized to match the PSF
kernel) is Pearson-correlated against the kernel. A value near 1.0 means the
local pixel pattern is shaped like the PSF; near 0 or negative means it
isn't (consistent with noise, a cosmic ray, or a bad-column edge rather than
a real point source). Sources too close to the image edge for a full cutout
report `psf_correlation: null` rather than a fabricated value from a padded
cutout. `_run_pixel_extraction_pilot` downloads the PSF product following
the same soft-requirement pattern as the mask (proceeds without it,
reporting `psf_applied: false`, if the preflight never verified it
available). Schema bumped to `ztf-dr24-pixel-extraction-pilot-v3`.

## Real live result — same exposure as the v1/v2 runs

Command:

```bash
caffeinate -i uv run --python 3.14 python Skills/ztf_dr24_bounded_ingest.py \
    --ra 232.6 --dec -8.4 --size-deg 0.01 \
    --start-jd 2458339.5 --end-jd 2458340.5 \
    --emit-motion-product-manifest \
    --preflight-motion-products \
    --pixel-extraction-pilot
```

| Metric | Value |
|---|---|
| PSF kernel shape (real, downloaded) | 25x25 pixels |
| Candidate sources (from v2) | 71 |
| Sources with a full-cutout PSF score | 33 |
| Sources too close to the edge (`psf_correlation: null`) | 38 |
| PSF correlation: min / max / mean / median (of the 33 scored) | -0.017 / 0.181 / 0.037 / 0.010 |
| Sources with correlation > 0.7 (a "real point source" threshold) | **0** |

**Honest finding, reported plainly, not spun**: of the 33 candidates that
could be scored against the real PSF kernel, none show meaningful
PSF-shape correlation. The strongest is 0.181 -- far below what a genuine
point source convolved with its own PSF would produce (the offline unit
test confirms a real synthetic Gaussian source correlates >0.95 against
the same kernel shape). This is consistent with the 71 raw candidates
being noise-level statistical fluctuations right at the 5-sigma threshold
rather than confirmed real sources, on this single exposure.

The 25x25 real PSF kernel is considerably larger than assumed when this
gap was scoped (the earlier evidence files did not have this number yet);
it excludes over half of the candidates outright from PSF scoring, which is
itself useful information about how much of a single exposure's usable
area a full PSF-shape test can actually cover near typical field edges/
detector boundaries.

## Offline test coverage

New tests in `tests/test_ztf_dr24_bounded_ingest.py`:
- `test_psf_shape_correlation_high_for_matching_gaussian_source` —
  independent-oracle: a source injected with the exact Gaussian shape used
  to build the test PSF kernel correlates >0.95.
- `test_psf_shape_correlation_low_for_non_psf_shaped_artifact` — a single
  hot-pixel spike (not smoothly PSF-shaped) correlates well below the real
  source case.
- `test_psf_shape_correlation_returns_none_near_edge` — edge case
  explicitly returns `None`, not a fabricated value.
- `test_detect_sources_reports_psf_correlation_when_provided` /
  `..._omits_psf_correlation_when_not_provided` — the soft-requirement
  field-presence contract, both directions.
- `test_run_pixel_extraction_pilot_downloads_psf_when_verified_available` /
  `..._skips_psf_when_not_verified_available` — the download logic.
- `test_run_bounded_ingest_pixel_extraction_pilot_end_to_end` updated to
  mock a real `difference_psf` response and assert `psf_applied: true`.

Full offline suite (`Skills/verify_reliability_controls.py`): all 6 checks
PASS, 100% coverage maintained.

## Decision boundary and what this closes

This completes the single-exposure pixel-extraction pilot arc started
today: preflight verification -> pixel extraction -> masking + dedup ->
PSF-shape scoring. Every disclosed gap from each prior step has now been
addressed on this one bounded exposure, and the honest conclusion is a
null result for that exposure (no PSF-confirmed candidates). This does not
authorize a wider batch, a candidate claim, Gate Z3 resumption, or external
submission.

**The next step is a genuine operator decision**, not another bounded
same-exposure refinement: whether to (a) try this same pipeline against a
different exposure/field to see if the null result is specific to this one
night's data, (b) build real multi-exposure linking so a tracklet
consistency check (not just single-exposure PSF shape) can be applied --
the actual next scientific rung up from what exists today, or (c) pause
this path here, having demonstrated the extraction mechanics work
end-to-end even though this specific exposure showed nothing.
