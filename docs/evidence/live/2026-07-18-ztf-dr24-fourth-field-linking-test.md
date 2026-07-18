# ZTF DR24 Multi-Night Linking — Fourth Algorithmically-Selected Field

Date: 2026-07-18

Scope: continued field expansion per operator direction ("reenter loop"
after the third field's evidence), ran the same fully-validated
pixel-extraction -> masking/dedup -> PSF-scoring -> multi-night-linking ->
review-packet -> adversarial-review -> ADES-export pipeline against a
fourth field, again chosen by the project's own documented selection
scoring. No code changes were needed.

External submission: none. Diagnostic linking, review, and dry-run export
only.

## Field selection (documented, not guessed)

Rank 3 of the same `--mode aten --top-n 20` batch that gave fields 2 and 3
(see `docs/evidence/live/2026-07-17-ztf-dr24-selected-field-linking-test.md`),
already recorded in `data_selection/target_priority_queue.csv`:

| Field | Value |
|---|---|
| RA / Dec | 48.71 / 22.5 |
| Score | 0.8879 |
| Reason | "coverage gap 0.94; pop density 0.73; geometry 0.96 (9.9h vis)" |

## Coverage and acquisition

Metadata-only query (`Skills/ztf_dr24_bounded_ingest.py`, metadata fetch
only), identical query shape/window to fields 2 and 3 (`--size-deg 0.01
--start-jd 2458200.5 --end-jd 2458599.5`, the maximum allowed 399-day
window): 318 rows across 90 distinct real nights, 3 distinct real ZTF
fields (556: 108 exposures, 606: 106, 557: 104 -- another field-boundary
overlap region). Picked 3 consecutive-cadence field-556 nights:
**20180713, 20180716, 20180719** (3-day, 3-day gaps). Verified locally
against the already-downloaded metadata table that each candidate
single-exposure window isolates exactly one exposure before any further
network calls (no adjacent-field collision this time, unlike field 3's
20180810).

Ran the full preflight -> download -> mask -> dedup -> PSF-score pipeline,
unmodified, on each of the 3 nights:

| Night | Raw connected components | Output (capped at 200) |
|---|---:|---:|
| 20180713 | 449 | 200 |
| 20180716 | 143 | 143 |
| 20180719 | 65 | 65 |

## Real live results

Converted and linked (`Skills/convert_pixel_extraction_to_observations.py`
+ `Skills/run_pixel_extraction_positive_control.py`, unmodified):

| `min_observations` | Tracklets formed |
|---:|---:|
| 2 (exploratory) | 200 (capped) |
| 3 (real default) | **6** |

Six survivors is the most of any field tested so far (fields 1: 2, field
2: 5, field 3: 0).

## Cross-validation: three independent signals, all four fields agree

**Adversarial review** (`Skills/adversarial_review.py --offline`): all 6
packets REJECTED. `SURVIVE=0 BORDERLINE=0 REJECT=6`. All 6 fail the same
4 challenges as fields 1/2's survivors (`orbit_quality`, `real_bogus`,
`artifact_posterior` -- `stellar_artifact` posterior ~0.99 for every
packet, `neo_dominance` -- `neo_candidate` posterior ~0.001 for every
packet). Two of the six additionally fail the hard `motion_rate` bound
(rates 0.031 and 0.037 arcsec/hr, below the 0.05 arcsec/hr hard floor for
a solar-system body -- these are near-stationary pairings, not moving
sources, correctly caught as a fifth failing challenge for those two).

**PSF-shape correlation** (independent of the classifier posterior above,
computed during pixel extraction against each exposure's real
`difference_psf` kernel): max correlation per night was 0.077 (20180713,
155/200 scored), 0.124 (20180716, 18/143 scored), 0.187 (20180719,
19/65 scored) -- all far below the >0.5 threshold a real point source is
expected to clear, and far below the >0.95 the synthetic injected-source
control achieves. The low scored-fraction on some nights matches MP4's
already-documented finding that the 25x25-pixel PSF kernel excludes
candidates near the image edge from full-cutout scoring.

**ADES export**: `Skills/export_ades_report.py` produced valid dry-run
PSV text for all 6 objects with `stn=XXX`; nothing submitted anywhere.

## Honest conclusion

**A fourth, independently and algorithmically selected field again
produces a null result under both independent verification signals**,
despite forming the most raw survivors (6) of any field tested. This is
exactly why the pipeline uses two independent checks rather than trusting
`min_observations=3` alone: geometric consistency (chi2 orbit fit) and
physical plausibility (PSF shape, classifier posterior) are different
questions, and a candidate that passes the first can still fail the
second cleanly, as it does here. Combined with fields 1-3, this is now
four consecutive fields, twelve real nights total, with no candidate
surviving both independent checks.

## Decision boundary

Does not authorize a wider batch, a candidate claim, Gate Z3 resumption, or
external submission. `data_selection/target_priority_queue.csv`'s rank-3
row (RA 48.71, Dec 22.5) updated to `null_result` citing this file.
