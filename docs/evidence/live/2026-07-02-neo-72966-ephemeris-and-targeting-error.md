# Gate Z3 — real ephemeris for NEO 72966 reveals the second-attempt targeting error

Date: 2026-07-02. Operator: Jerome W. Lindsey III. Branch: `main` @
`de283e2` (v0.90.40).

## Command

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/lookup_neo_archive_ephemeris.py \
    --designation 72966 \
    --start-jd 2458339.5 --end-jd 2458439.5 --step 1d
```

## Result

Real JPL Horizons ephemeris for minor planet 72966, 101 points over the
100-day window from night 20180809. Full output committed to the
operator's local `Logs/pipeline_runs/lookup_neo_archive_ephemeris/`.
Selected points:

| Night | RA (deg) | Dec (deg) |
|---|---|---|
| 20180809 | 232.5584 | -8.4239 |
| 20180810 | 232.8862 | -8.5551 |
| 20180902 | 241.5899 | -11.5706 |
| 20181117 | 280.3291 | -16.9327 |

## Key finding: this explains the second alert-archive attempt's miss

Night 20180809's predicted position (RA 232.5584, Dec -8.4239) is within
~0.05 deg of the real detection already confirmed in that night's alert
packet (RA 232.6075742, Dec -8.4449086, `ssnamenr: '72966'`) — this
independently validates the ephemeris lookup against already-established
ground truth.

By night 20180902, 72966's real predicted position has moved to RA
241.5899, Dec -11.5706 — an angular separation of roughly **9.4 degrees in
RA and 3.2 degrees in Dec** from the original fixed search box (RA 232.6,
Dec -8.4, radius 2.0 deg) used in the second Gate Z3 alert-archive attempt
(`docs/evidence/live/2026-07-02-ztf-alert-archive-ingest-second-attempt.md`).

This means the Gate Z1 "hit" recorded for night 20180902 at the *original*
fixed field was a coincidental revisit of that field, unrelated to
tracking this specific object — by then 72966 had moved to a completely
different patch of sky, well outside the 2-degree search radius used. The
zero-kept result from the alert-archive ingest on night 20180902 was
therefore a **targeting error** (searching the wrong sky position for that
night), not further evidence about this field's cadence.

## Fix / next step (v0.90.41)

Blind field-revisit sampling with a fixed sky box across multiple nights
does not account for a moving object's real motion. Added
`Skills/scan_neo_track_coverage.py`: for a bounded subset of the real
ephemeris points (stride-limited to avoid hammering IRSA), it re-centers
each cheap Gate Z1 metadata check on that specific night's real predicted
position, so real coverage is checked at the object's actual location
rather than a stale fixed field.

Next operator action: run the track-coverage scan to find real nights
where ZTF's real exposure coverage overlaps 72966's real predicted
position, before spending bandwidth on another multi-GB alert-archive
download.
