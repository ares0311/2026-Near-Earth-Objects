# Gate Z3 — sentinel-filtered scan with real observatory codes: 35 hits, new same-station candidate pair selected

## Command and real result

```bash
caffeinate -i uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \
    --designation 72966 --archive-start-jd 2458273.5 --stride 10 \
    --force-refresh-mpc
```

Run on `main` @ v0.90.56. Real result: 16 sentinel-magnitude MPC reports
excluded (confirming the v0.90.55 filter engaged), 51 real in-window
reports checked, **35 had real ZTF sci-exposure coverage** at their exact
position/date -- and for the first time, every `HIT` line shows a real
reporting-observatory code (the `--force-refresh-mpc` fix from v0.90.56
worked as intended).

## Selection criterion (new, more principled than prior attempts)

Both previously-tried candidate pairs (20220817/20220819 and
20210106/20210111) had **different** reporting observatories for their
two nights (T05/C51-sentinel, and I41/G96 respectively) -- see
`docs/evidence/live/2026-07-04-gate-z3-observatory-codes-real-findings.md`.
With real per-hit observatory codes now visible across all 35 hits, two
candidate pairs stand out for sharing the **same** station on both
nights, close in time:

| Candidate pair | Gap | Observatory (both nights) | Real mags |
|---|---|---|---|
| **20191030 / 20191101** | 2 days | **I41** (both) | 19.48/19.19 and 18.95/18.99 (all real) |
| 20210105 / 20210111 | 6 days | **G96** (both) | 19.32-19.57 and 19.23-19.53 (all real) |

## Expected motion (computed directly from the real hit positions, not guessed)

```
20191030 (RA=29.6558, Dec=5.8706) -> 20191101 (RA=29.2335, Dec=5.6456), 2 days:
  separation=1715.8 arcsec, rate=35.75 arcsec/hr, PA=241.8 deg

20210105 (RA=116.3469, Dec=8.5736) -> 20210111 (RA=114.9265, Dec=8.8038), 6 days:
  separation=5122.2 arcsec, rate=35.57 arcsec/hr, PA=279.3 deg
```

Both rates are plausible (consistent with the object's previously
observed ~35-39 arcsec/hr range across other apparitions) and similar to
each other, as expected for the same object.

## Selected: 20191030/20191101 (shorter time gap minimizes orbit-motion targeting error, same station both nights)

## Next step (NOT YET DONE)

Run the alert-archive ingest tool for both nights, each centered on that
night's own real matched position:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20191030 \
    --ra 29.6558 --dec 5.8706 --radius-deg 2.0 --min-rb 0.5
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20191101 \
    --ra 29.2335 --dec 5.6456 --radius-deg 2.0 --min-rb 0.5
```

If both yield real kept observations, run the positive control:

```bash
caffeinate -i uv run --python 3.14 python Skills/run_archive_positive_control.py \
    --nights 20191030 20191101 --min-observations 2 \
    --out Logs/pipeline_runs/run_archive_positive_control/report_20191030_20191101.json
```

Then rank with `Skills/match_positive_control_tracklet.py` (ref1
29.6558 5.8706, ref2 29.2335 5.6456) and check raw observations with
`Skills/find_nearest_raw_observation.py` if needed, per the established
sequence.

Backup candidate if this pair fails: 20210105/20210111 (6 days apart,
both real G96 reports).
