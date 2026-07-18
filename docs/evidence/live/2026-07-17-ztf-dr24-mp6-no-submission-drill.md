# Gate MP6 — No-Submission Package Drill (Motion-Product Path)

**Date**: 2026-07-17
**Gate**: `docs/ZTF_DR24_PRODUCTION_GATES.md` MP6, per the "MP6 closure plan"
section written in this project's prior session.
**Objective**: prove a real tracklet produced by the source-native
pixel-extraction pipeline can be carried through
`classify() -> fit_orbit() -> score() -> process_alert(dry_run=True)` into a
real `ScoredNEO` review packet, then through `Skills/adversarial_review.py`
and `Skills/export_ades_report.py`, with zero external submission and zero
network calls at the export step — mirroring Gate Z6's already-proven
pattern for the alert-replay sub-approach.

## Step 1 — code change

Added `--build-review-packets` and `--review-packet-out` to
`Skills/run_pixel_extraction_positive_control.py`, mirroring
`Skills/run_archive_positive_control.py`'s existing pattern: every linked
tracklet is run through the real `classify() -> fit_orbit() -> score() ->
process_alert(dry_run=True)` chain (dry_run is fixed `True` in this code
path; there is no flag to change it), and the resulting `ScoredNEO` dicts
are collected under `review_packets`. 6 new offline tests added to
`tests/test_run_pixel_extraction_positive_control.py` (now 13 total, all
passing), including a regression test for a real bug found in Step 3 below.

## Step 2 — live run on already-acquired real data (field 1)

No new download — reused the MP5 checkpoints for field 1 (RA 232.6, Dec
-8.4; nights 20180802, 20180806, 20180809):

```
caffeinate -i uv run --python 3.14 python Skills/run_pixel_extraction_positive_control.py \
    --nights 20180802 20180806 20180809 \
    --checkpoint-dir Logs/pipeline_runs/ztf_dr24_pixel_extraction_positive_control \
    --min-observations 3 \
    --build-review-packets \
    --out Logs/pipeline_runs/ztf_dr24_pixel_extraction_positive_control/report.json
```

**Real result**: `n_tracklets_linked: 2`, matching MP5's 2 surviving
tracklets on this field exactly. `report.json`'s `review_packets` key
contains 2 real `ScoredNEO` dicts (each with `hazard`, `posterior`,
`metadata` keys populated by the real pipeline).

## Step 3 — pipe packets through adversarial review and ADES export

**Real bug found and fixed**: feeding `report.json` (the full wrapper dict
written by `--out`, which has `review_packets` as one key among several)
directly into `Skills/adversarial_review.py` does not work —
`adversarial_review.py` expects a plain JSON array of `ScoredNEO` dicts as
its top-level input. Doing this produced a spurious `review_packet_schema`
FAIL and a REJECT verdict that was **not** the real drill result — it was a
format-mismatch artifact. Root cause: the MP6 closure plan's Step 2/3
commands only specified `--out`, which was under-specified for this
purpose. Fixed by adding `--review-packet-out`
(matching `Skills/run_pipeline.py`'s existing flag of the same name and
purpose) to `run_pixel_extraction_positive_control.py`, which writes
*just* `report["review_packets"]` as a standalone plain JSON array — the
format both downstream tools actually expect. Added
`test_cli_review_packet_out_writes_plain_scored_neo_list` and
`test_cli_review_packet_out_requires_build_review_packets` as regression
coverage.

Re-ran Step 2 with the corrected flag:

```
caffeinate -i uv run --python 3.14 python Skills/run_pixel_extraction_positive_control.py \
    --nights 20180802 20180806 20180809 \
    --checkpoint-dir Logs/pipeline_runs/ztf_dr24_pixel_extraction_positive_control \
    --min-observations 3 \
    --build-review-packets \
    --review-packet-out Logs/pipeline_runs/ztf_dr24_pixel_extraction_positive_control/review_packets.json
```

Then ran the real drill against the corrected, plain-array file:

```
PYTHONPATH=src uv run --python 3.14 python Skills/adversarial_review.py \
    Logs/pipeline_runs/ztf_dr24_pixel_extraction_positive_control/review_packets.json \
    --offline --json
```

**Predicted result (stated before running, per this project's "predict
before you run" discipline)**: `SURVIVE=0 BORDERLINE=0 REJECT=2` — REJECT
is the *correct* expected outcome, not a failure, because MP4 (PSF-shape
correlation, real result <=0.18 vs >0.95 for a real point source) and MP5
(3 real signals already agreeing these are not real point sources) already
established these specific tracklets fail independent validation.

**Real result: exactly as predicted.**

```
REJECT=2, SURVIVE=0, BORDERLINE=0
```

Both packets failed on 4 independent grounds, cross-validating MP4/MP5's
findings with a third, independent tool:
- `orbit_quality` FAIL — no orbital elements available from a 3-observation
  arc this short.
- `real_bogus` FAIL — no native real/bogus score from this pixel-extraction
  path; fails the 0.90 gate by design (there is nothing to pass).
- `artifact_posterior` FAIL — `stellar_artifact` posterior ~0.99 for both
  packets, agreeing with MP4's independent PSF-correlation finding via a
  completely different signal (the classifier's posterior, not pixel-shape
  correlation).
- `neo_dominance` FAIL — `neo_candidate` posterior ~0.001 for both packets.

This is the third independent line of evidence (after geometric
chi2-consistency and PSF-shape correlation) agreeing that no real point
source survives on this field — a well-supported null result, not a
tooling failure.

Exported ADES PSV:

```
PYTHONPATH=src uv run --python 3.14 python Skills/export_ades_report.py \
    Logs/pipeline_runs/ztf_dr24_pixel_extraction_positive_control/review_packets.json \
    --out Logs/pipeline_runs/ztf_dr24_pixel_extraction_positive_control/ades_export.psv
```

**Real result**: valid ADES PSV text generated for both objects with
`stn=XXX` (the documented first-submission placeholder per
`docs/MPC_SUBMISSION_POLICY.md`). Nothing was submitted anywhere.

**Zero-network-calls verification** (matching Gate Z6's verification
method — code inspection):

```
grep -n "^import\|^from\|requests\.\|urllib\|http" Skills/export_ades_report.py
```

Real result: only stdlib imports (`argparse`, `json`, `sys`,
`pathlib.Path`) appear anywhere in the file. No network library is
imported. Confirms `export_ades_report.py` is structurally incapable of
making a network call.

## Honest interpretation

MP6's closure requirement is fully satisfied on real data: a real tracklet
from the motion-product pixel-extraction pipeline was carried through
`classify() -> fit_orbit() -> score() -> process_alert(dry_run=True)` into
real `ScoredNEO` packets, correctly REJECTed by adversarial review for
reasons that agree with two prior independent gates (MP4, MP5), then
formatted as valid dry-run ADES PSV text with zero network calls and zero
external submission. This exactly mirrors Gate Z6's already-proven closure
pattern, for the new motion-product sub-approach.

The `--review-packet-out` gap is a real, disclosed finding: the original
MP6 closure plan's Step 2/3 commands (written in the prior session, before
this drill had actually been run) under-specified the interface between
`run_pixel_extraction_positive_control.py`'s `--out` report format and what
`adversarial_review.py`/`export_ades_report.py` actually consume. This is
now fixed in code and the plan text in `docs/ZTF_DR24_PRODUCTION_GATES.md`
is corrected to cite `--review-packet-out` explicitly, so a future agent
running this again (e.g. on field 2's checkpoints) does not rediscover the
same gap.

This drill did not run field 2's checkpoints
(`ztf_dr24_pixel_extraction_positive_control_field2`) — not required to
close the gate per the closure plan's own text ("one field's packets are
sufficient to prove the mechanics"), and field 1's result already
cross-validates MP4/MP5 a third time.

This does not constitute or imply MPC submission authority for the
motion-product path. No candidate was submitted, no impact probability was
stated, and no object is claimed as a confirmed NEO.
