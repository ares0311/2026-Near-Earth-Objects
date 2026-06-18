# T1-C Evidence: Recovery Selector And Provider Diagnostic

## Purpose

This file records the durable GitHub-visible summary for the June 18, 2026 T1-C recovery work. Raw operational outputs remain local under `Logs/` and are intentionally ignored.

## What Changed

- `Skills/build_recovery_manifest.py` can now preselect expected-known objects from the broader MPC asteroid orbit list, either by auto-centering on a dense projected field or by preserving a requested ZTF-available field.
- `Skills/select_survey_fields.py` can now optionally probe live ALeRCE/ZTF availability before recommending recovery fields.
- `src/fetch.py` now queries ALeRCE `stamp_classifier=asteroid` objects before falling back to generic alert objects.
- `src/detect.py` now preserves stable broker object histories via `field_id` instead of pairing unrelated same-night alerts.

## Live Diagnostic Results

| Run / Artifact | Result |
|---|---|
| Auto-centered NEO-only manifest | `3` expected-known rows; too sparse for production recovery. |
| Auto-centered all-asteroid manifest | `89` expected-known rows, but selected field had `0` ZTF alerts in the window. |
| ZTF-aware fixed field selector | Top field RA `251.66`, Dec `-22.50`, radius `3.5`, with `100` live ALeRCE/ZTF objects. |
| Fixed-field 4-day manifest | `19` expected-known rows; pipeline fetched `98` alerts, detected `44` candidates, linked `0` tracklets. |
| Fixed-field 30-day generic run | Pipeline fetched `229` alerts, detected `31` candidates, linked `1` internal candidate; recovery audit `0/18`. |
| Fixed-field 30-day asteroid-class run | Pipeline fetched `119` asteroid-class alerts, detected `48` candidates, linked `0` multi-night tracklets. |

## Root Cause

ALeRCE asteroid-class objects in this field are same-night three-detection asteroid tracklets: `50` objects were fetched, and the top object histories all had `(3 detections, 1 distinct night)`. This is useful real moving-object evidence, but it does not satisfy the current T1-C multi-night tracklet recovery KPI.

The current T1-C production gate therefore remains open. It needs either:

1. A provider/data path that exposes multi-night known-object detections suitable for the existing `>=3 observations on >=2 nights` recovery audit, or
2. An explicitly documented same-night known-object recovery subgate that is treated as diagnostic evidence only and does not replace the multi-night production gate.

## Safety Status

All runs were dry recovery diagnostics. No external submission was performed, no MPC submission was made, no NASA/PDCO notification was made, and no impact probability was asserted.
