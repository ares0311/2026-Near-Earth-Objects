# T1-C Evidence: ATLAS Forced-Photometry Fallback Diagnostic

This file records the durable GitHub-visible summary for the June 18, 2026
ATLAS fallback work. Raw operational outputs remain local under `Logs/` and
are intentionally ignored.

## Purpose

T1-C still requires multi-night known-object recovery evidence and
citizen-science operator false-positive review. The previous public ALeRCE
path produced useful real moving-object detections, but those detections were
same-night histories and did not satisfy the multi-night recovery gate.

The fallback tested here is targeted ATLAS forced photometry against an
expected-known MPC/Horizons manifest. This is supporting recovery evidence, not
blind discovery evidence, and it does not authorize MPC submission, NASA
notification, or any impact-probability statement.

## Implementation

`Skills/fetch_atlas_data.py` now has an expected-known recovery mode:

```bash
uv run --python 3.14 python Skills/fetch_atlas_data.py \
  --expected-known Logs/reports/t1c_expected_known_ztf_available_251p66_m22p5_30d.json \
  --run-root Logs/pipeline_runs \
  --min-recovered-samples 3 \
  --min-nights 2 \
  --workers 2 \
  --resume \
  --force-refresh
```

The command intentionally uses the `1.0` day default search half-window. ATLAS
cadence is approximately two days, so the earlier diagnostic value
`--window-days 0.05` was too narrow for production recovery evidence and should
not be reused for T1-C.

The recovery mode writes an audit-compatible packet:

- `Logs/pipeline_runs/<run_id>/checkpoint.json`
- `Logs/pipeline_runs/<run_id>/run_summary.json`
- `Logs/pipeline_runs/<run_id>/expected_known_atlas_forced.json`

The packet is consumed by `Skills/audit_real_run.py`. Recovery remains
fail-closed: no audit tracklet is emitted unless enough usable ATLAS samples
are recovered across enough distinct nights.

## Provider Fix

The live ATLAS diagnostic found that the forced-photometry helper was using a
JSON request body and did not request JSON responses. The official ATLAS API
guide uses form `data` for `/queue/` and sets `Accept: application/json`.

`src/fetch.py::fetch_atlas_forced` now:

- submits form data to `/forcedphot/queue/`;
- sends `Accept: application/json` on queue and task-status requests;
- supports bounded polling with configurable `max_polls` and
  `poll_interval_seconds`;
- exposes an optional progress callback so operator runs show ATLAS queue
  position and completion state.
- persists in-flight ATLAS task URLs in the recovery checkpoint so an
  interrupted operator run can resume polling the same queued tasks instead of
  creating duplicate queue jobs.

## Live Result

A bounded fallback pilot was run before the provider request-format fix:

- run id: `atlas_recovery_203f0f698996`
- manifest rows: `3`
- expected samples: `10`
- recovered samples: `0`
- emitted audit tracklets: `0`
- `Skills/audit_real_run.py` status: `evaluated`, `passed=false`

After the request-format fix, a redacted one-sample ATLAS diagnostic confirmed
the server returns the documented JSON task response and a task URL. The
diagnostic task reported a high queue position (`164`) and was deleted after
inspection to avoid cluttering the ATLAS queue.

## Current Conclusion

The ATLAS fallback path is now implemented and test-backed, but it has not yet
closed T1-C. A longer operator-supervised run is required because ATLAS queue
latency can exceed short diagnostic windows.

The next T1-C run should use the fixed recovery mode with `caffeinate -i`, a
longer poll budget, and conservative worker count. The result must still pass
the existing `audit_real_run.py` known-object recovery KPI and operator review
before internal production promotion.

Follow-up hardening after the first long queue wait: the recovery checkpoint now
survives `--resume --force-refresh`, records `polling` sample states during
ATLAS queue waits, and reuses stored task URLs on resume. This means a killed or
sleep-interrupted queue wait should be restarted with the same command after
pulling latest `main`; the tool will print `[resume] ... polling existing ATLAS
task` for samples with stored task URLs.

If `max_polls` is exhausted while ATLAS still reports no `finished` or
`result_url` state, the sample is recorded as `poll_exhausted`, not
`not_recovered`. That state remains pending and resumable because it reflects
provider queue latency rather than a completed no-data result.

No external submission was performed.
No impact probability was asserted.
