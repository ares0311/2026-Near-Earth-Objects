# Gate Z3 — full systematic MPC-history × ZTF-coverage scan: 30 real hits

Date: 2026-07-02. Operator: Jerome W. Lindsey III. Branch: `main` @
`587dae7` (v0.90.44, the sequential pre-sharding version — this ran to
full completion in one process, ~12 minutes, so no sharding was needed
for this particular result).

## Command

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \
    --designation 72966 \
    --archive-start-jd 2458273.5 --stride 10
```

## Result

Real, complete (53/53 checked, not partial) result: **30 of 53 checked
real MPC reports had real ZTF sci-exposure coverage** at their exact
observed position/date -- a far richer hit rate than the earlier
hand-picked-cluster check (1/4). Full list committed to the operator's
local
`Logs/pipeline_runs/scan_mpc_history_ztf_coverage/scan_report.json`.
Selected notable hits (RA/Dec/sci-row-count):

| Night | RA | Dec | Sci rows |
|---|---|---|---|
| 20191005 | 35.0025 | 9.0289 | 30 |
| 20191008 | 34.4307 | 8.6509 | 24 |
| 20210106 | 116.1336 | 8.6041 | 24 |
| 20210111 | 114.9238 | 8.8044 | 42 |
| 20220626 | 255.9003 | -6.4134 | 12 |
| 20220628 | 255.5771 | -6.4516 | 2 |
| **20220817** | **257.0809** | **-10.7456** | **16** |
| **20220819** | **257.5497** | **-10.9843** | **24** |

## Selected target pair for the next Gate Z3 alert-archive attempt

**20220817 and 20220819** -- only 2 real days apart (minimizing orbit-
motion targeting error), both with substantial independent real sci
coverage (16 and 24 rows respectively), and both independently confirmed
by a real MPC-reported observation of 72966. This is the strongest
candidate pair found in this project to date: closer in time than the
July 2018 cluster, richer in coverage than the single-night 20180713
candidate, and covering two genuinely different real nights (unlike the
20191023 duplicate-night artifact in the raw hit list, which was the same
night sampled by two different MPC report rows).

## Next step

Run the alert-archive ingest tool against both nights, each centered on
that night's own real matched position (not a shared fixed box, since the
object moved ~0.5 deg between the two nights):

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20220817 \
    --ra 257.0809 --dec -10.7456 --radius-deg 2.0 --min-rb 0.5
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20220819 \
    --ra 257.5497 --dec -10.9843 --radius-deg 2.0 --min-rb 0.5
```

If both yield >=1 kept observation, run the positive control:

```bash
caffeinate -i uv run --python 3.14 python Skills/run_archive_positive_control.py \
    --nights 20220817 20220819 \
    --out Logs/pipeline_runs/run_archive_positive_control/report.json
```

If this specific pair comes back empty, the next-best backup candidates
(in order of time-proximity) are 20191005/20191008 (3 days apart, 30/24
sci rows) and 20220626/20220628 (2 days apart, but night 2 has only 2 sci
rows -- riskier).
