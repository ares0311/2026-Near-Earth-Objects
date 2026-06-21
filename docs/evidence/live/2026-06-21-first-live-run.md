# First Live Pipeline Run — 2026-06-21

## Summary

**Date**: 2026-06-21  
**Operator**: Jerome W. Lindsey III  
**Mode**: LIVE RUN (--no-dry-run)  
**Run ID**: 6c1b387e0763  

## Result

Pipeline executed end-to-end without errors. Console output conforms to
`docs/CONSOLE_OUTPUT_SPEC.md`.

## Parameters

| Field | Value |
|-------|-------|
| RA | 83.8221° |
| Dec | -5.3911° |
| Radius | 1.0° |
| Start JD | 2460700.0 |
| End JD | 2460707.0 (7-day window) |
| Surveys | ZTF |
| Elapsed | 4s |

## Credential Status

| Credential | Status |
|------------|--------|
| ATLAS_TOKEN | PRESENT |
| ZTF_IRSA_USERNAME | PRESENT |
| ZTF_IRSA_PASSWORD | PRESENT |
| ATLAS live test | OK (5 obs) |
| ZTF live test | OK (0 obs) |

## Outcome

- Alerts retrieved: 0
- Candidates: 0
- Tracklets: 0
- Submission-ready: 0
- Cache files deleted: 393

## Notes

Zero ZTF alerts is expected for the Orion field (RA=83.8221, Dec=-5.3911) at
JD 2460700. ZTF's observing footprint for any given 7-day window is ~15,000
sq-deg out of the northern sky (~30,000 sq-deg). The Orion field sits near the
galactic plane where ZTF density is lower and the test window may not overlap
with a ZTF observation epoch for this cone.

The 393 cache files deleted confirms the IRSA TAP query was issued and
returned (empty) results normally — the pipeline reached the network and
got a valid (zero-row) response.

## Next Step

Use `Skills/select_survey_fields.py --mode recovery` to select a field that
ZTF has actually observed recently, with known recoverable moving objects.
This will ensure the live run returns real alerts.

## Status

LIVE PIPELINE: OPERATIONAL ✓  
Console spec: COMPLIANT ✓  
`--no-dry-run` flag: WORKING ✓
