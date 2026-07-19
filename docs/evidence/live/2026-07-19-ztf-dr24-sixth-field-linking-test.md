# ZTF DR24 Multi-Night Linking — Sixth Algorithmically-Selected Field

Date: 2026-07-19

Scope: continued field expansion per operator direction ("reenter loop"),
ran the same fully-validated pixel-extraction -> masking/dedup ->
PSF-scoring -> multi-night-linking -> review-packet -> adversarial-review
-> ADES-export pipeline against a sixth field (fifth candidate from the
priority queue; the fourth candidate, rank 4, was skipped for
insufficient coverage -- see below). No code changes were needed.

External submission: none. Diagnostic linking, review, and dry-run export
only.

## Rank-4 candidate skipped: insufficient coverage

Before this field, rank 4 of the same `--mode aten --top-n 20` batch (RA
211.81, Dec -7.5, score 0.8821) was checked first. A metadata-only query
over the maximum allowed 399-day window (`--size-deg 0.01 --start-jd
2458200.5 --end-jd 2458599.5`) found only **2** real distinct nights
(20190124, 20190325) -- below this project's 3-night minimum for a
meaningful multi-night linking test. Recorded in
`data_selection/target_priority_queue.csv` as `insufficient_coverage`
rather than `null_result` (no linking test was actually run), and the
next-ranked candidate was used instead.

## Field selection (documented, not guessed)

Rank 5 of the same batch (already recorded in
`data_selection/target_priority_queue.csv`):

| Field | Value |
|---|---|
| RA / Dec | 46.59 / 15.0 |
| Score | 0.8761 |
| Reason | "coverage gap 0.91; pop density 0.78; geometry 0.87 (9.3h vis)" |

## Coverage and acquisition

Metadata-only query, identical shape/window to prior fields: 138 rows
across 72 distinct real nights, 2 distinct real ZTF fields (505: 103
exposures, 1551: 35). Picked 3 consecutive-cadence field-505 nights:
**20180714, 20180717, 20180720** (3-day, 3-day gaps). Verified locally
against the already-downloaded metadata table that each single-exposure
window isolates exactly one exposure before any further network calls.

Ran the full preflight -> download -> mask -> dedup -> PSF-score pipeline,
unmodified, on each of the 3 nights (download times 2-3s for the
difference image on all three -- a healthy serial baseline, consistent
with this project's other serial single-exposure downloads and
independently confirming the same-day IRSA concurrency probe's serial
baseline was accurate):

| Night | Raw connected components | Output (capped at 200) |
|---|---:|---:|
| 20180714 | 75 | 75 |
| 20180717 | 95 | 95 |
| 20180720 | 246 | 200 |

## Real live results

Converted and linked (unmodified):

| `min_observations` | Tracklets formed |
|---:|---:|
| 2 (exploratory) | 95 |
| 3 (real default) | **2** |

## Cross-validation: both independent signals agree

**Adversarial review** (`Skills/adversarial_review.py --offline`): both
packets REJECTED. `SURVIVE=0 BORDERLINE=0 REJECT=2`. Both fail the same 4
challenges seen on every prior field's survivors (`orbit_quality`,
`real_bogus`, `artifact_posterior`, `neo_dominance`).

**PSF-shape correlation**: max correlation per night was 0.177
(20180714, 20/75 scored), 0.202 (20180717, 32/95 scored), 0.260
(20180720, 150/200 scored) -- all well below the >0.5 real-source
threshold.

**ADES export**: `Skills/export_ades_report.py` produced valid dry-run PSV
text for both objects with `stn=XXX`; nothing submitted anywhere.

## Honest conclusion

A sixth field (fifth real linking test; one candidate skipped for
insufficient coverage) again produces a null result under both
independent verification signals, consistent with fields 1-4. Combined
total: **five algorithmically-selected fields tested with a real linking
run, fifteen real nights total**, plus one candidate correctly skipped
before consuming any download budget on a field with too little coverage
to test meaningfully.

## Decision boundary

Does not authorize a wider batch, a candidate claim, Gate Z3 resumption, or
external submission. `data_selection/target_priority_queue.csv`'s rank-5
row (RA 46.59, Dec 15.0) updated to `null_result` citing this file.
