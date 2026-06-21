# Live Run Diagnosis — ALeRCE ndet Ordering Bug — 2026-06-21

## Root Cause

`_fetch_ztf_alerce_api` queried ALeRCE with `order_by="ndet", order_mode="DESC"`:
- Returns the 50 MOST-detected persistent sources (stars, AGN) first
- Moving solar system objects appear as **one new OID per night per position** (ndet=1 each)
- These low-ndet OIDs rank last and are excluded by the 50-object cap
- All 102/120 alerts were stationary sources; linker correctly found 0 tracklets

The IRSA TAP fallback (`_fetch_ztf_irsa_api`) is documented as "fail-closed" —
the `ztf_alerts` table does not exist in IRSA TAP; swapping order would not fix it.

## Symptom

| Run | Window | Alerts | Candidates | Tracklets |
|-----|--------|--------|------------|-----------|
| Run 2 | 7 days | 102 | 48 | 0 |
| Run 3 | 30 days | 120 | 38 | 0 |

Only 18 more alerts for 23 extra days confirms a fixed-population persistent source
cap, not time-series data.

## Fix Applied (src/fetch.py)

`_fetch_alerce_objects_for_filter` now accepts `order_mode` and `ndet_max` params:

- **Mode 1 (asteroid classifier)**: `order_mode="DESC"`, `ndet_max=None`
  Returns all ALeRCE asteroid-classified objects (highest confidence path).

- **Mode 2 (generic fallback)**: `order_mode="ASC"`, `ndet_max=20`
  Returns the 50 LEAST-detected objects with 1-20 total detections.
  Single-night moving-object OIDs (ndet=1) now rank first instead of last.

## Expected Outcome

Next run should return single-night transient detections. If the same moving
object appears at different positions on different nights (as separate OIDs
each with ndet=1), the linker should connect them based on motion rate and
position consistency to form tracklets.
