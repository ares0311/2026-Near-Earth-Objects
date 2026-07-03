# Gate Z3 — third live alert-archive attempt (ephemeris-targeted night 20180903)

Date: 2026-07-02. Operator: Jerome W. Lindsey III. Branch: `main` @
`addc2e5` (v0.90.41).

## Command

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20180903 \
    --ra 242.0130 --dec -11.6968 --radius-deg 2.0 --min-rb 0.5
```

## Result

Real download: 8.5GiB, 193,223 real packets scanned over 8m36s with
correct, continuous progress/ETA output throughout (fourth consecutive
confirmation the v0.90.36/v0.90.39 fixes work correctly on real, large
files). **Kept: 0.**

This is despite `Skills/scan_neo_track_coverage.py`'s live run confirming
**6 real science exposure rows** at this exact position (RA 242.0130, Dec
-11.6968) via the Gate Z1 metadata endpoint just prior (see
`docs/evidence/live/2026-07-02-gate-z3-track-coverage-scan-hit.md`).

## Root-cause diagnosis (stated before any further code changes, per the
standing rule)

A real science exposure existing at a position (Gate Z1 IRSA metadata hit)
confirms only that ZTF pointed a camera there and took an image. It does
**not** confirm that ZTF's difference-imaging (DIA) pipeline generated an
**alert** (a candidate transient/moving-source detection) at that specific
narrow position with `rb >= 0.5`. Alert generation requires the DIA
pipeline to detect significant flux above the reference template at that
exact sub-position; a faint, slow-moving source near the noise floor, or a
predicted position with residual orbit uncertainty offsetting it from the
real detection by more than the field-of-view precision needed, can result
in zero alerts on a night with confirmed real exposure. Gate Z1's metadata
check answers "was the sky imaged" -- a categorically different question
from "did a real alert fire here."

Three real attempts (blind revisit x2, ephemeris-targeted x1) have now
each returned zero real alert-archive detections despite real exposure
coverage or plausible object positions. This is not evidence of a bug in
the ingest or scan tools -- all three runs completed with correct
progress/ETA and real, large-file scans.

## Predicted next step and its outcome test

**Predicted root cause fix**: switch from "does ZTF's sci-exposure
metadata cover this position" (Gate Z1) to "does MPC's own confirmed
observation history report a real astrometric detection of this exact
object on a real archive-covered date" (`src/fetch.py:fetch_mpc_observations`,
already Phase-0-verified production code). A real MPC-reported
observation means a real alert was generated and credible enough to be
submitted and accepted -- the exact signal missing from the sci-exposure
check.

**What the operator's console will show if this is correct**: a night
where MPC independently confirms a real reported observation of 72966
AND the alert-archive ingest at that night/position yields >=1 kept
observation.

**What it will show if this diagnosis is still wrong**: another zero-kept
result despite an MPC-confirmed report, which would indicate the gap is
something else entirely (e.g. a difference in reporting observatory/survey
for that specific observation, or a real-bogus threshold issue) and
requires fresh re-diagnosis rather than a third layer of the same
targeting-refinement pattern.
