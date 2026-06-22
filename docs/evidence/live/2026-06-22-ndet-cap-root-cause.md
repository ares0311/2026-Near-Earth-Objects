# Live Run Diagnosis — ndet Cap Root Cause — 2026-06-22

## Correct Root Cause

The previous diagnosis (2026-06-21) misidentified the root cause as "ndet DESC ordering"
and applied a fix to Mode 2 only.  Mode 2 is never called when Mode 1 succeeds.
Runs 4 and 5 produced identical output (120 alerts, 38 candidates, 0 tracklets),
confirming the previous fix had no effect.

**True root cause**: `_fetch_ztf_alerce_api` Mode 1 used `ndet_max=None`, which
returns ALeRCE OIDs of **persistent or semi-persistent stationary sources** at
fixed sky positions.  For each such OID, `query_detections(oid)` returns multiple
detections spread across the 30-day window at essentially the **same sky position**
(centroid ± ~1 arcsec astrometric noise).

The linker then:
1. Groups these same-OID detections by night
2. Forms seed pairs between nights — motion rate ≈ 0 arcsec/hr (same position)
3. Rejects all pairs: rate below `_MOTION_MIN_ARCSEC_PER_HR = 0.01`
4. Result: 3134 pairs tried, 0 accepted → 0 tracklets

## Why ndet=1 Is the Moving-Object Signature

ZTF/ALeRCE OID association radius is ~1 arcsec.  An MBA at opposition moves
~700 arcsec/night; a NEO moves faster.  Each night's detection is at a
**new sky position** far outside the association radius → a **new OID with ndet=1**.

- Persistent star (ndet=500): all detections at same position → one OID
- Moving object (ndet=1 per OID): each night a new OID at a new position

An asteroid-classified OID with `ndet=1` is exactly the signature of a real
single-night moving-object detection.

## Fix Applied (src/fetch.py)

`_fetch_ztf_alerce_api` Mode 1 changed:
- `ndet_max`: None → **3** (exclude persistent background sources)
- `order_mode`: "DESC" → **"ASC"** (surface single-detection OIDs first)
- `max_objects`: 50 → **200** (more candidates for broader field coverage)

Mode 2 (generic fallback):
- `ndet_max`: 20 → **3** (consistent with Mode 1; tighter exclusion of persistent sources)

Two regression tests added to `tests/test_fetch.py`:
- `test_mode1_uses_ndet_cap_not_persistent_sources`: verifies `ndet[1] ≤ 3` in Mode 1
- `test_mode2_fallback_also_uses_ndet_cap`: verifies `ndet[1] ≤ 3` in Mode 2 fallback

## Run History

| Run | ndet filter | Alerts | Candidates | Tracklets | Notes |
|-----|------------|--------|------------|-----------|-------|
| 3 | None (DESC) | 120 | 38 | 0 | Persistent sources |
| 4 | ASC, ndet≤20 (Mode 2 only, never called) | 120 | 38 | 0 | Fix was irrelevant |
| 5 | ASC, ndet≤20 (Mode 2 only, never called) | 120 | 38 | 0 | Confirmed fix had no effect |
| Next | ASC, ndet≤3 (Mode 1 AND Mode 2) | TBD | TBD | TBD | Correct fix |

## Expected Outcome

With ndet≤3, Mode 1 returns OIDs where:
- The stamp classifier labeled at least one detection as "asteroid"
- The OID appeared ≤3 times in the ALeRCE database (transient / single-night)

Each such OID contributes 1 observation at a unique sky position on a unique night.
The linker then pairs observations from different nights showing consistent solar
system motion rates (0.01–60 arcsec/hr) to form tracklets.

If still 0 tracklets after this fix, the next diagnostic step is to switch to
ATLAS forced photometry at Horizons-predicted positions of known NEOs (approach
that already succeeded in T1-C producing 5 multi-night tracklets).
