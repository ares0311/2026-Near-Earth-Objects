# Gate Z3 — first cross-check of an MPC-confirmed cluster against Gate Z1

Date: 2026-07-02. Operator: Jerome W. Lindsey III. Branch: `main` @
`14ab249` (v0.90.43).

## Command

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_dr24_bounded_ingest.py \
    --ra 225.44 --dec -5.08 --size-deg 2.0 \
    --start-jd 2458308.5 --end-jd 2458316.5
```

8-day window (2018-07-09 to 2018-07-17) centered on the July 11 position
of the dense real MPC-confirmed cluster identified in
`docs/evidence/live/2026-07-02-mpc-observation-history-72966.md` (real
MPC reports on nights 20180711, 20180713, 20180714, 20180715).

## Result

Real, live IRSA response: **9 rows, 1 distinct real ZTF night (20180713),
1 field.** Only 1 of the 4 real MPC-confirmed report nights in this window
has real ZTF sci-exposure coverage at this sky position.

## Interpretation

The object's real position drifted from RA 225.44 (07/11) to RA
226.08-226.23 (07/15), well within the 2-degree search radius the whole
time, so this is not a targeting-box miss like the earlier ephemeris
attempt. The most likely explanation is that most of these specific MPC
reports (07/11, 07/14, 07/15) were made by a different observatory/survey
than ZTF -- MPC's observation history aggregates reports from many
surveys, and this project's current `fetch_mpc_observations` mapping does
not expose the reporting observatory code, so a real MPC report does not
guarantee it came from ZTF specifically.

**Night 20180713 is now the strongest single-night candidate found in
this project**: it has two independent real confirmations -- an MPC-
reported observation of object 72966, AND Gate Z1-confirmed real ZTF sci
exposure at essentially the same position. Still only one confirmed
night; a second is needed for the Gate Z3 positive control.

## Next step (v0.90.44)

Rather than hand-picking more individual clusters, `Skills/scan_mpc_history_ztf_coverage.py`
systematically checks a bounded, stride-limited subset of ALL 526 real
in-window MPC reports against Gate Z1, at each report's own exact real
observed position/date. This directly extends the successful pattern used
here to the full real observation history instead of one hand-picked
week.
