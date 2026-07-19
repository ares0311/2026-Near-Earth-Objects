# Phase 2 ATLAS confirmation-quality evidence — 2026-07-19

## Objective

Close the adversarial-review path that treated any row returned by a
fixed-coordinate ATLAS forced-photometry query as independent confirmation of
a moving candidate.

## Root cause

`_challenge_cross_survey_confirmation()` queried one mean tracklet coordinate
over the full observation window and promoted one returned row to `PASS`. It
did not validate the row's time, position, measurement quality, duplication,
or consistency with the linked motion. The fetcher's compatibility behavior
also maps provider failures to an empty list, so the challenge could not
distinguish a real null result from failed acquisition.

That query is not a valid moving-object association. The ATLAS PDS operations
guide states that moving-object forced photometry requires ephemerides accurate
to about one pixel (approximately 2 arcseconds); a fixed sky position across a
multi-day moving tracklet does not satisfy that requirement. The NOIRLab
ANTARES example likewise treats `uJy/duJy` as the measurement signal-to-noise
and removes negative-flux rows rather than equating every returned row with a
detection.

Primary/public references:

- [ATLAS Operations and Data Processing, section 4.6](https://pds-smallbodies.astro.umd.edu/data_sb/missions/atlas/ATLAS_Operations_and_Data_Processing.pdf)
- [NOIRLab ANTARES ATLAS photometry example](https://nsf-noirlab.gitlab.io/csdc/antares/devkit/notebooks/LightcurvesPhotometrySearch/)

## Implementation

- Removed the live fixed-coordinate query from the confirmation challenge.
  Arbitrary forced-photometry rows can no longer upgrade a candidate.
- A ZTF-only candidate now records a transparent `SKIP`: no linked ATLAS
  observation exists, and fixed-coordinate photometry is not moving-object
  confirmation without a precise ephemeris.
- A claimed ZTF + ATLAS tracklet is independently replayed from its earliest
  ZTF position, motion rate, position angle, and elapsed time.
- Each ATLAS observation must:
  - contain finite time, position, magnitude, uncertainty, and motion inputs;
  - avoid the magnitude-99 non-detection sentinel;
  - have positive uncertainty and estimated S/N at least 5;
  - match the replayed position within 2 arcseconds;
  - be unique within the tracklet.
- Any invalid or duplicate claimed ATLAS row makes the challenge `FAIL`, not
  `PASS` or an invisible fallback.
- Evidence records the versioned policy, thresholds, predicted position,
  residual, magnitude uncertainty, and estimated S/N.
- The challenge remains optional enrichment. It does not become a required
  eligibility dependency and does not introduce AI judgment.

## Verification

Focused behavioral command:

```bash
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python -m pytest \
  tests/test_adversarial_review_skill.py tests/test_adversarial.py -q
```

Result: **86 passed**. Independent-oracle cases cover valid kinematic replay,
position mismatch, sentinel magnitude, sub-5-sigma measurement, zero
uncertainty, non-finite input, duplicate rows, polar replay, invalid predicted
declination, absent ATLAS evidence, and non-ZTF candidates.

The original Phase 1 packet replay remains safely rejected:

```bash
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python \
  Skills/adversarial_review.py \
  Logs/pipeline_runs/phase1_detection_hardening_field1/review_packets.json \
  --offline --json
```

Result: **2 REJECT**, expected exit status 1. Offline mode does not run optional
cross-survey enrichment; required epoch-specific known-object evidence still
fails closed when its cache is absent.

Canonical working-tree verification passed all six mandatory stages: **2,088
passed, 2 deselected, 100.00% coverage across all 5,545 `src` statements**.
The clean-commit freshness rerun and GitHub CI result are recorded in the PR
handoff.

## Remaining Phase 2 work

- SkyBoT live-positive validation remains blocked by the recorded upstream HTTP
  500 response. Do not repeat identical requests; run one bounded no-match and
  one known-object positive control after service recovery.
- Audit whether every scientific selector feature and weight has a measured,
  versioned provenance record and an independent regression oracle. Phase 2 is
  not closed by this unit.
- Phase 3 remains blocked.
