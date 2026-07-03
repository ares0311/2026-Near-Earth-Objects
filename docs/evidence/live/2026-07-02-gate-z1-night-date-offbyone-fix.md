# Gate Z1 — JD noon/midnight off-by-one in `distinct_nights_yyyymmdd`

Date: 2026-07-02. Operator: Jerome W. Lindsey III. Branch: `main` @
`5298c68` (v0.90.38, the version that introduced the buggy field).

## Command and real output that exposed the bug

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_dr24_bounded_ingest.py \
    --ra 232.6 --dec -8.4 --size-deg 2.0 \
    --start-jd 2458339.5 --end-jd 2458439.5
```

```
[resume] run af142e089e85: checkpoint and raw response already present, skipping fetch
[ingest] Parsed 14 rows across 2 distinct night(s), 1 distinct field(s)  elapsed 0m00s
[ingest] Distinct real nights (YYYYMMDD): ['20180808', '20180902']
[ingest] Wrote Logs/pipeline_runs/ztf_dr24_bounded_ingest/af142e089e85/sample_ingest_report.json
```

## Diagnosis

`20180808` is physically inconsistent with already-established ground
truth: an earlier gate (`docs/evidence/phase0/2026-07-02-gate-z3-uw-alert-archive-candidate.md`)
live-downloaded and schema-inspected a real alert packet with
`jd: 2458339.6521991` and confirmed, by directly downloading and
tar-listing the file, that this exact packet originates in
`ztf_public_20180809.tar.gz` — i.e. the real archive's own per-night
naming says this JD is night **20180809**, not 20180808.

Root cause, confirmed by direct computation:

```python
>>> from astropy.time import Time
>>> Time(2458339.6521991, format="jd").datetime          # correct, full jd
datetime.datetime(2018, 8, 9, 3, 39, 10, 2220)
>>> Time(int(2458339.6521991), format="jd").datetime      # truncated first
datetime.datetime(2018, 8, 8, 12, 0)
```

The Julian Date convention increments at **noon UTC**, not midnight.
`v0.90.38`'s implementation first collapsed each row's `obsjd` to a bare
integer (`int(float(v))`) before converting that integer back to a
calendar date. Whenever the original fractional part was less than 0.5
(i.e. the observation happened before noon UTC, as ZTF's UTC-evening
observations typically do), the truncated integer JD lands exactly on
noon UTC of the day *before* the observation's real UTC calendar date —
producing a systematically wrong, off-by-one night label.

## Fix (v0.90.39)

`Skills/ztf_dr24_bounded_ingest.py` now derives each row's calendar date
directly from its full, un-truncated `obsjd` value (`Time(float(v),
format="jd").datetime.strftime("%Y%m%d")` per row), then deduplicates the
resulting date *strings* — never truncating the JD to an integer first.
`n_distinct_nights` is now computed as `len(distinct_nights_yyyymmdd)` so
both fields stay consistent with each other and with the real archive
night-naming convention.

Regression-tested in `tests/test_ztf_dr24_bounded_ingest.py`
(`test_night_date_matches_known_real_archive_night`): asserts that the
exact real `obsjd` value from this incident (2458339.6521991) maps to
`"20180809"`, encoding the already-established ground truth so this exact
bug cannot silently reappear.

## What this means for the real result

The real underlying data (14 rows, 2 distinct nights, 1 field, from a
100-day window at RA 232.6, Dec -8.4) is unchanged — only the calendar-date
labels were wrong. The corrected real night pair is **20180809** (not
20180808) and **20180902**, roughly 24 days apart — not the ~3-night
cadence assumed earlier, and much sparser than the ~10-day window
originally tried. This is real evidence that this specific 2-degree sky
box at this position is a genuinely low-cadence field for ZTF, not a bug
in the ingest or linking code.

## Next step

Re-run the same command (now on v0.90.39+) to get the corrected
`distinct_nights_yyyymmdd` output (no new network call — resumes from the
cached response), then target `Skills/ztf_alert_archive_ingest.py --nights
20180809 20180902 --ra 232.6 --dec -8.4 --radius-deg 2.0 --min-rb 0.5` for
the Gate Z3 "known-object positive control" attempt. Note night 20180809's
alert-archive data (21 kept observations) is already cached locally from
the first Gate Z3 live run and will resume without a re-download; only
20180902 needs a fresh alert-archive fetch.
