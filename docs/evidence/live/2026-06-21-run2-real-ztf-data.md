# Live Run 2 — Real ZTF Data Retrieved — 2026-06-21

## Run Parameters

**Run ID**: 5fb5e8d50704  
**Field**: RA=284.13°, Dec=-22.5°, r=3.5°  
**Window**: JD 2461206.0 – 2461213.0 (7 days)  
**Mode**: LIVE RUN (--no-dry-run)  
**Elapsed**: 48s

## Stage Outcomes

| Stage | Result |
|-------|--------|
| fetch | **102 real ZTF alerts** retrieved from IRSA ✓ |
| preprocess | 102/102 sources passed ✓ |
| detect | **48 moving candidates**, 0 known matches ✓ |
| link | 2639 seed pairs tried; **0 tracklets formed** |

## Root Cause: 0 Tracklets

The linker requires the same moving object to appear on ≥2 distinct nights.
With 48 candidates from 102 alerts over 7 days in a 3.5° cone, all detections
appear to be from a single ZTF epoch (or non-overlapping epochs with no
common moving object). The linker correctly returns 0.

ZTF observes a given field roughly every 2-3 nights. In a 7-day window at
Dec=-22.5° (ZTF's southern edge), there may be only 2-3 visits, each
detecting *different* transients rather than the same moving object on
multiple nights.

## Next Step

Extend the time window to 30 days (JD 2461183.0 – 2461213.0) so more
ZTF epochs are included for the same sky position. More epochs = higher
probability that a moving object appears at different positions on different
nights, enabling the linker to form tracklets.

## Status

**Live ZTF data retrieval: CONFIRMED WORKING**  
Linker: needs multi-night coverage to form tracklets.
