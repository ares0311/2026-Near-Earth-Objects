# ZTF DR24 Multi-Night Linking — First Real Test

Date: 2026-07-17

Scope: the operator-approved next step after the single-exposure
pixel-extraction pilot arc (preflight -> extraction -> masking/dedup ->
PSF-shape scoring): real multi-night acquisition and cross-night tracklet
linking, reusing the existing, already-tested `src/link.py` linker rather
than building a new one.

External submission: none. This is diagnostic linking only -- no
classification, scoring, review, or submission of any candidate.

## What was acquired

Metadata-only coverage query (no pixels) over the same field
(RA 232.6, Dec -8.4) across a ~400-day window found 52 real nights of
ZTF coverage. Two additional nights close to the already-analyzed
2026-07-16 exposure were selected for a bounded 3-night test:

| Night | JD | Exposures | Pixel-extraction result |
|---|---|---:|---|
| 20180802 | 2458332.6713 | 1 | 302 connected components, 200 output (capped) |
| 20180806 | 2458336.6918 | 1 (of 2 available; second not used) | 344 connected components, 200 output (capped) |
| 20180809 | 2458339.6522 | 1 (already had this from 2026-07-16) | 71 connected components, untruncated |

Each night ran through the full existing preflight -> download -> mask ->
dedup -> PSF-score pipeline, unmodified from the single-exposure work.

## New engineering built

1. `Skills/convert_pixel_extraction_to_observations.py` -- converts a
   pixel-extraction-pilot checkpoint into the `Observation` checkpoint
   format `Skills/run_archive_positive_control.py` already consumes, so
   real per-night acquisition and the existing linker infrastructure could
   be reused rather than rebuilt. Uses an explicitly disclosed, uncalibrated
   magnitude proxy (`zeropoint - 2.5*log10(peak_value)`), since this
   extractor has no real photometric calibration.
2. `Skills/run_pixel_extraction_positive_control.py` -- reuses
   `preprocess()` and `link()` directly, bypassing `detect()`'s ZTF-specific
   candidate-forming logic. Root-caused, not guessed: `detect.py`'s
   within-night pairing (`_find_moving_sources`) requires two same-night
   exposures (structurally impossible here -- one exposure per night), and
   its cross-night singleton-preservation path
   (`_preserve_discovery_archive_singletons`) is gated to
   `mission in {"WISE", "DECam", "TESS"}`, excluding "ZTF" even though this
   data is architecturally identical in kind (single-epoch, archive-sourced,
   no broker object history). Extending that gate in shared `detect.py`
   was judged out of scope (real regression risk across 2000+ existing
   tests); this new script performs the same singleton-wrapping without
   touching `detect.py`.

Both scripts have offline test coverage (11 new tests total) including an
independent-oracle regression test for a real bug caught live (see below).

## Real bug caught and fixed before this evidence was recorded

The first real run of the converter produced **0/471 observations passing
`preprocess()`**. Root cause, diagnosed not guessed: `preprocess()` hard-
rejects any observation with `mag <= 0` (`src/preprocess.py`'s basic
quality cuts), and the converter's first magnitude formula
(`-2.5*log10(peak_value)`) produces negative magnitudes for every realistic
peak value in this dataset (tens to low thousands). Fixed by adding a
disclosed placeholder zeropoint (25.0) so proxy magnitudes land in a
physically plausible ZTF range (~15-22); a new regression test
(`test_converted_observations_survive_preprocess_mag_gate`) calls the real
`preprocess()` end-to-end so a future regression here is caught the same
way this one was, not just checked in isolation.

## Real live linking results

Command:

```bash
caffeinate -i uv run --python 3.14 python Skills/run_pixel_extraction_positive_control.py \
    --nights 20180802 20180806 20180809 \
    --checkpoint-dir Logs/pipeline_runs/ztf_dr24_pixel_extraction_positive_control \
    --min-observations 3
```

| `min_observations` | Tracklets formed |
|---:|---:|
| 2 (exploratory) | **200** -- combinatorial explosion |
| 3 (link()'s real default) | **2** |

**The 200-tracklet result at `min_observations=2` is expected, not a bug.**
The field is 0.01 deg (~36 arcsec) wide; over the 4-day gap between
20180802 and 20180806, `link()`'s 60 arcsec/hr motion-rate tolerance allows
up to 60 x 96 = 5,760 arcsec (1.6 deg) of separation -- far larger than the
entire field. Every candidate on one night can trivially pair with nearly
every candidate on the other within tolerance. This is the identical
"combinatorial cross-night pairing in a crowded field" phenomenon this
project's Gate Z6 evidence already documented for the old alert-based path
(88 tracklets from a crowded field, none real) -- now independently
reproduced for the new source-native pixel-extraction path. It is not a
property of `prv_candidates` or the old pipeline; it is a property of a
narrow field, a wide time gap, and a permissive `min_observations=2`.

At the real default `min_observations=3` (requiring a third,
geometrically-consistent point across all three nights, which `link()`
checks via its chi2 orbit-consistency test when extending pairs), the
combinatorial pool collapses from 200 to **2** tracklets.

## Cross-validation against PSF-shape scoring: both survivors fail independently

The two `min_observations=3` survivors were traced back to their original
pixel-extraction records (which carry `psf_correlation` and `snr`, not
propagated into the linker's `Observation` objects):

| Tracklet | Night | SNR | `psf_correlation` |
|---|---|---:|---|
| 7cc057fd | 20180802 | 5.49 | null (edge of image) |
| | 20180806 | 5.97 | 0.068 |
| | 20180809 | 10.60 | null (edge of image) |
| 458a8601 | 20180802 | 5.42 | null (edge of image) |
| | 20180806 | 6.59 | 0.023 |
| | 20180809 | 6.29 | -0.004 |

Every observation in both surviving tracklets is at or near the 5-sigma
detection floor (SNR 5.4-10.6), and every `psf_correlation` value that
could be computed is far below the >0.5 threshold a real point source is
expected to clear (the earlier PSF-scoring evidence's own synthetic
Gaussian test correlates >0.95). The geometric linker (a 3-night motion-
consistency test) and the independent PSF-shape check (a per-observation
point-source-shape test) are testing completely different things and
agree here: **neither tracklet shows corroborating evidence from the other
test.** This is exactly the kind of cross-validation the project's own
adversarial-review philosophy calls for, and it comes out negative.

## Honest conclusion

This is a well-supported null result across the full pipeline (preflight ->
extraction -> masking/dedup -> PSF-shape scoring -> multi-night linking),
not a tooling failure:

- The pixel-extraction and linking mechanics work correctly end-to-end on
  real DR24 data (200 real tracklets demonstrate the linker functions; the
  drop to 2 at the correct `min_observations=3` demonstrates the
  orbit-consistency filter functions).
- Neither `min_observations=3` survivor shows independent PSF-shape
  evidence of being a real point source.
- No candidate from this 3-night, one-field test is a plausible NEO
  candidate.

## Decision boundary

Does not authorize a wider batch, a candidate claim, Gate Z3 resumption, or
external submission. This closes the operator-approved "build real
multi-exposure linking" direction as a working, validated capability with
an honest negative result on this specific field/night set. The next
decision is again the operator's: try this same linking pipeline against a
different field (more promising sky region, e.g. via
`Skills/select_survey_fields.py`'s scoring rather than reusing the already-
explored verification field), or pause.
