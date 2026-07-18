# ZTF DR24 Multi-Night Linking — Third Algorithmically-Selected Field

Date: 2026-07-17

Scope: per operator direction ("expand to more fields"), ran the same
fully-validated pixel-extraction -> masking/dedup -> PSF-scoring ->
multi-night-linking pipeline against a third field, again chosen by the
project's own documented selection scoring
(`Skills/select_survey_fields.py`), rather than reusing either of the two
previously-tested fields. No code changes were needed.

External submission: none. Diagnostic linking only.

## Field selection (documented, not guessed)

This field was already scored by the same `--mode aten --top-n 20` run
that selected field 2 (see
`docs/evidence/live/2026-07-17-ztf-dr24-selected-field-linking-test.md`),
which wrote all 20 ranked candidates to
`data_selection/target_priority_queue.csv` in one pass. Rank 1 of that
batch (RA 217.41, Dec -15.0) was field 2, now marked `null_result` in the
queue. This run picks rank 2 of the same batch:

| Field | Value |
|---|---|
| RA / Dec | 54.35 / 15.0 |
| Score | 0.8997 |
| Reason | "coverage gap 0.95; pop density 0.73; geometry 1.00 (9.3h vis)" |

## Coverage and acquisition

Metadata-only query (`Skills/ztf_dr24_bounded_ingest.py`, no action flags
-- metadata fetch only, no product download), identical query shape and
window to field 2's acquisition (`--size-deg 0.01 --start-jd 2458200.5
--end-jd 2458599.5`, the maximum allowed 399-day window): 248 rows across
82 distinct real nights, 3 distinct real ZTF fields. ZTF field 506
dominates (110 exposures), closely followed by field 507 (107) -- the two
fields overlap this RA/Dec box's corner. Picked 3 consecutive-cadence
field-506 nights: **20180807, 20180810, 20180813** (3-day, 3-day gaps).
Verified locally against the already-downloaded metadata table, before any
further network calls, that each candidate single-exposure JD window
isolates exactly one exposure (field-506 on 20180810 initially collided
with a near-simultaneous field-507 exposure ~35 seconds apart in the same
0.01-day window; narrowed to a 0.0004-day window to isolate field 506
only).

Ran the full preflight -> download -> mask -> dedup -> PSF-score pipeline,
unmodified, on each of the 3 nights (all four products verified/downloaded
per night, matching prior fields' pattern):

| Night | Raw connected components | Output (capped at 200) |
|---|---:|---:|
| 20180807 | 18 | 18 |
| 20180810 | 357 | 200 |
| 20180813 | 53 | 53 |

## Real live results

Converted (`Skills/convert_pixel_extraction_to_observations.py`) and
linked (`Skills/run_pixel_extraction_positive_control.py`, unmodified from
the prior two fields' runs):

| `min_observations` | Tracklets formed |
|---:|---:|
| 2 (exploratory) | 71 |
| 3 (real default) | **0** |

**This is a stronger null result than either prior field**: fields 1 and 2
both left 2 and 5 survivors respectively after the `min_observations=3`
chi2 orbit-consistency filter, each requiring independent PSF-shape
cross-validation to rule out. Here, the chi2 filter eliminates every
combinatorial candidate outright -- zero tracklets reach the review-packet
stage at all. `--build-review-packets --review-packet-out` correctly wrote
an empty `review_packets.json` (`[]`), matching this project's own
established rule (`docs/OPERATOR_GO_NO_GO_RUNBOOK.md` Step 1: "If it says 0
packets, stop -- there is nothing to review"). No adversarial review or
ADES export step applies here, since there is nothing to review or export.

The lower `min_observations=2` combinatorial count (71, versus 200 for
each prior field) is consistent with this field's lower raw candidate
density per night (18/200-capped/53, versus each prior field's ~200-capped
nights across the board) -- fewer raw candidates means fewer possible
cross-night pairings, not a different phenomenon.

## Honest conclusion

**A third, independently and algorithmically selected field again produces
a null result**, and this time a cleaner one: the geometric linker's real
`min_observations=3` default rejects every combinatorial candidate
outright rather than leaving a small survivor set requiring further
cross-validation. Combined with fields 1 and 2, this is now three
consecutive fields, nine real nights total, where the fully-validated
pipeline finds no plausible NEO candidate. This continues to strengthen
the conclusion that the null results are a property of the search (real
NEOs are rare; nine nights across three fields is a small fraction of sky
and time) rather than an artifact of any one field/night combination or a
pipeline defect.

## Decision boundary

Does not authorize a wider batch, a candidate claim, Gate Z3 resumption, or
external submission. `data_selection/target_priority_queue.csv`'s rank-2
row (RA 54.35, Dec 15.0) updated to `null_result` citing this file. Per
`docs/ZTF_DR24_PRODUCTION_GATES.md`'s Production Definition, a confirmed
discovery is not a precondition for production readiness -- three
consecutive honest null results are exactly the kind of evidence a
defensible discovery-paper search process is expected to produce most of
the time.
