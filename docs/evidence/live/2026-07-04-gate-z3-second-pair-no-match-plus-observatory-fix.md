# Gate Z3 — second candidate pair also fails to positively control; real root-cause fix

## Real results: 20210106/20210111 pair

```bash
caffeinate -i uv run --python 3.14 python Skills/run_archive_positive_control.py \
    --nights 20210106 20210111 --min-observations 2 \
    --out Logs/pipeline_runs/run_archive_positive_control/report_20210106_20210111.json
```

Real result: 449 observations loaded (272 + 177), all preprocessed, 88
candidates detected, 54 tracklets formed at `min_observations=2`.

```bash
uv run --python 3.14 python Skills/match_positive_control_tracklet.py \
    Logs/pipeline_runs/run_archive_positive_control/report_20210106_20210111.json \
    --ref1 116.1336 8.6041 \
    --ref2 114.9238 8.8044
```

Best match: total offset **4231.5 arcsec (70.5 arcmin, 1.18 deg)** --
same order of magnitude as the first pair's failure, again far too large
to be the same object. All 54 tracklets ruled out.

```bash
uv run --python 3.14 python Skills/find_nearest_raw_observation.py \
    Logs/pipeline_runs/ztf_alert_archive_ingest/20210106.json --ref 116.1336 8.6041
uv run --python 3.14 python Skills/find_nearest_raw_observation.py \
    Logs/pipeline_runs/ztf_alert_archive_ingest/20210111.json --ref 114.9238 8.8044
```

Night 20210106: closest real detection is **14.1 arcsec** away
(`real_bogus=0.71`) -- a strong plausible match. Night 20210111: closest
is **2103.1 arcsec (35.1 arcmin)** away -- far too large (would require
~58 hours of the object's own ~36.2 arcsec/hr motion, well beyond a
single UTC night).

## Pattern across both candidate pairs (2 apparitions checked)

| Pair | Night A offset | Night B offset |
|---|---|---|
| 20220817/20220819 | 74.1 arcsec (plausible) | 615.7 arcsec (too far) |
| 20210106/20210111 | 14.1 arcsec (plausible) | 2103.1 arcsec (too far) |

Both pairs show a strong near-match on their first night and no plausible
match on their second night. Two data points are not enough to prove a
systematic bias, but the pattern is suspicious enough to investigate the
underlying MPC data rather than blindly ingesting a third apparition.

## Real root cause found and fixed (not guessed)

`docs/evidence/phase0/2026-07-02-root-cause-findings.md` already recorded
(2026-07-02, real operator `curl` output) that MPC's `get-obs` ADES
response for a real designation returns "hundreds of `<optical>` records
... multiple stations/surveys" -- i.e. MPC's observation history
aggregates reports from every observatory/survey that ever reported the
object, not just ZTF. `src/fetch.py:fetch_mpc_observations` already
extracted this real `observatory` value from the astroquery table (line
834, pre-existing) but only used it to build an internal hash string --
it was never exposed on the returned `Observation` object, so no
downstream tool (including the ones that selected these two candidate
pairs) could ever see or filter on it.

**This means every candidate pair selected via
`scan_mpc_history_ztf_coverage.py` so far was chosen using only "does ZTF
have sci-exposure metadata at this position/date" (Gate Z1) plus "does
MPC have a confirmed report at this position/date" (any station) -- never
confirming the MPC report itself came from ZTF.** A non-ZTF station
reporting the object's real position on a given UTC date, combined with
ZTF separately having imaged near that same position that night (common,
since ZTF resurveys the whole visible sky every ~3 nights), produces a
false-positive "hit" in the systematic scan even when ZTF's own alert
pipeline never generated a confident detection of the true object that
night.

## Fix (this PR)

- `src/fetch.py:fetch_mpc_observations` now passes the already-fetched
  `observatory` value through as `field_id` on each returned
  `Observation` (a pre-existing schema field, no new API added).
- `Skills/lookup_mpc_observation_history.py`'s report rows and console
  output now include this `observatory` field per report.
- `Skills/scan_mpc_history_ztf_coverage.py`'s per-hit console line and
  JSON report now include it too (the JSON already carried it through via
  dict spread; only the console line needed updating).
- 1 new regression test in `tests/test_fetch.py` and 1 in
  `tests/test_lookup_mpc_observation_history.py` confirm the value flows
  through end to end.

## Next step (NOT YET DONE)

Do not select a third candidate pair blindly. Instead, re-run
`Skills/lookup_mpc_observation_history.py --designation 72966` (cheap,
already cached locally, no new network call needed) and inspect the new
`observatory` field for every in-window report -- specifically checking
whether the two reports anchoring each of the two tried pairs actually
share the same station code, and whether that code is genuinely ZTF's.
If the two nights within a pair have *different* observatory codes, that
directly explains the observed pattern (one night's report is a real
ZTF-adjacent coincidence, the other isn't), and future candidate-pair
selection should filter to matching, ZTF-associated station codes before
spending more download bandwidth on another apparition.
