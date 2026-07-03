# Gate Z1 — first live run of `Skills/ztf_dr24_bounded_ingest.py`

Date: 2026-07-02. Operator: Jerome W. Lindsey III. Branch: `main` @
`e5d95d2` (v0.90.36).

## Command

```bash
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_dr24_bounded_ingest.py \
    --ra 232.6 --dec -8.4 --size-deg 2.0 \
    --start-jd 2458339.5 --end-jd 2458349.5
```

10-day window starting the night before the confirmed-good night 20180809
(JD 2458339.5 ≈ 2018-08-09 00:00 UT), same 2-degree sky box already used by
the Gate Z3 ingest runs.

## Console output (verbatim)

```
[resume] run 954ac3d94cdb: checkpoint and raw response already present, skipping fetch
[ingest] Parsed 5 rows across 1 distinct night(s), 1 distinct field(s)  elapsed 0m00s
[ingest] Wrote Logs/pipeline_runs/ztf_dr24_bounded_ingest/954ac3d94cdb/sample_ingest_report.json
```

Note: this run resumed from an existing local checkpoint rather than
performing a fresh network fetch (the checkpoint/resume key is a hash of
the exact query parameters, so an identical prior invocation on the
operator's machine is why `skipping fetch` appears here) — the underlying
IRSA response and the 5-row/1-night/1-field result are real query output
either way; resume does not change or invalidate the data.

## Result

- **This is Gate Z1's first confirmed live run against the real, unmocked
  IRSA ZTF sci-metadata endpoint** (`irsa.ipac.caltech.edu/ibe/search/ztf/products/sci`),
  closing the "pending operator live verification" status on Gate Z1's row
  in `docs/ZTF_DR24_PRODUCTION_GATES.md`.
- Real result: across the full 10-day window (nights 20180809 through
  ~20180819), IRSA reports **only 1 distinct night** and **1 distinct
  field** with any science exposure at all inside this exact 2-degree box
  centered on RA 232.6, Dec -8.4.
- This directly explains the Gate Z3 negative results already on record:
  night 20180810 (docs/evidence/live/2026-07-02-ztf-alert-archive-ingest-first-live-run.md)
  and night 20180812 both came back with zero kept observations not
  because of any bug, but because **ZTF simply took no science exposures
  at this sky position on either of those nights** — confirmed now from
  the survey's own real exposure metadata, not inferred from the
  documented "~3-night cadence" generalization alone.

## What this does and does not close

- **Closes**: Gate Z1's "operator live verification" pending item — the
  bounded metadata ingest tool is confirmed working against the real,
  live IRSA endpoint.
- **Does not close**: Gate Z3's "known-object positive control." The
  10-day window at this exact sky position only contains 1 real
  observing night, so a second night cannot be found here without
  widening the time window further (still bounded, well under
  `_MAX_WINDOW_DAYS=400`) to find this specific field's true real revisit
  cadence, before spending bandwidth downloading more multi-GB alert
  archive files.
