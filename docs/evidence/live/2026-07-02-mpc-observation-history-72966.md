# Gate Z3 — first live run of `Skills/lookup_mpc_observation_history.py`

Date: 2026-07-02. Operator: Jerome W. Lindsey III. Branch: `main` @
`dcd07d1` (v0.90.43).

## Command

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/lookup_mpc_observation_history.py \
    --designation 72966 \
    --archive-start-jd 2458273.5
```

## Result

Real, substantial result: **1332 total MPC-confirmed observations** of
minor planet 72966, of which **526 fall within the ZTF alert archive's
real coverage window** (JD >= 2458273.5, 2018-06-04 onward). Full report
committed to the operator's local
`Logs/pipeline_runs/lookup_mpc_observation_history/72966_2458273.5/mpc_history_report.json`.

This is the strongest real evidence of genuine detection activity for
this object found so far in this project -- far denser than the single
`ssnamenr` cross-match that originally identified it. The observations
span many surveys/years (2018-2025); this tool does not yet distinguish
which observatory reported each one (MPC's `get_observations()` result
does not expose this on the `Observation` schema as currently mapped).

## Candidate cluster identified for the next check

A dense real cluster in **July 2018** stands out for its proximity to
ZTF's active era and multiple close-together real report nights:

| Night | RA (deg) | Dec (deg) | mag |
|---|---|---|---|
| 20180711 | 225.44 | -5.08 | 19.2-19.4 |
| 20180713 | 225.78-225.81 | -5.27 to -5.29 | 18.7-20.0 |
| 20180714 | 225.99-226.07 | -5.39 to -5.43 | 19.0-99.0 |
| 20180715 | 226.08-226.23 | -5.44 to -5.52 | 99.0 (sentinel, no mag) |

4 real report nights within a single week, all at Dec ~-5 (well within
ZTF's northern footprint). This is a much stronger candidate than the
earlier single-night ephemeris-based guesses, since MPC independently
confirms real detection activity across multiple nights here -- though it
does not yet confirm the reporting survey was ZTF specifically.

## Next step

Cross-check this cluster against the cheap Gate Z1 ZTF sci-metadata tool
(centered on the July 11 position, spanning the full cluster window)
before committing to another multi-GB alert-archive download:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_dr24_bounded_ingest.py \
    --ra 225.44 --dec -5.08 --size-deg 2.0 \
    --start-jd 2458308.5 --end-jd 2458316.5
```

If this reports >=2 distinct real ZTF nights overlapping the MPC cluster
above, target `Skills/ztf_alert_archive_ingest.py` at those specific real
nights/positions next.
