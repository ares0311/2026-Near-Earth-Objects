# T2-A Integration Live Test Results — 2026-06-21

## Run Summary

**Date**: 2026-06-21  
**Operator**: Jerome W. Lindsey III  
**Python**: 3.14.3  
**Command**: `PYTHONPATH=src OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run python -m pytest -m integration_live -v --timeout=120`

## Live Connection Test (verify_live_credentials.sh)

```json
{
  "atlas": { "status": "OK", "n_obs": 5 },
  "ztf":   { "status": "OK", "n_obs": 0 }
}
```

All credentials PRESENT (ATLAS_TOKEN, ZTF_IRSA_USERNAME, ZTF_IRSA_PASSWORD).

## Test Results (Run 1 — before fix)

| Test | Result | Notes |
|------|--------|-------|
| `test_fetch_ztf_live_small_region` | PASS | ZTF IRSA live cone-search OK |
| `test_fetch_atlas_live_small_region` | FAIL | HTTP 400 from ATLAS /queue/ |

**Root cause**: `fetch_atlas` used `json=payload` (Content-Type: application/json) + non-standard fields `use_reduced` and `radius`. ATLAS /queue/ endpoint requires `data=` (form-encoded) and only accepts `ra`, `dec`, `mjd_min`, `mjd_max`, `send_email`.

## Fix Applied (commit ccc9947)

- Changed `json=payload` → `data=payload` in `fetch_atlas`
- Removed `use_reduced` and `radius` from payload
- Added `"Accept": "application/json"` header
- Replaced `use_reduced: False` with `send_email: False`

Pattern matches the working `fetch_atlas_forced` implementation.

## Test Results (Run 2 — after fix, commit 4f372d6)

| Test | Result |
|------|--------|
| `test_fetch_ztf_live_small_region` | PASS |
| `test_fetch_atlas_live_small_region` | PASS |

Run time: 13.04s. 2 passed, 3744 deselected.

## Status

**T2-A CLOSED (2026-06-21)** — all integration_live tests pass on operator Mac.
