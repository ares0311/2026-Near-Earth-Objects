# Gate Z3 — first live run of `Skills/ztf_alert_archive_ingest.py`

Date: 2026-07-02. Operator: Jerome W. Lindsey III. Branch: `main` @
`bdbec1f` (v0.90.35 — the pre-progress-fix version; the operator ran this
*before* PR #173's v0.90.36 fix was merged, per the timestamp in the
`starship` prompt showing `v0.90.35` both before and after the command).

## Command

```bash
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20180809 20180810 \
    --ra 232.6 --dec -8.4 --radius-deg 2.0 --min-rb 0.5
```

## Console output (verbatim, sanitized of local machine path only)

```
[ingest] 20180809: HEAD https://ztf.uw.edu/alerts/public/ztf_public_20180809.tar.gz
[ingest] 20180809: remote size 31.0MiB
[ingest] 20180809: complete -- scanned=715 kept=21 elapsed 0m03s
[ingest] 20180810: HEAD https://ztf.uw.edu/alerts/public/ztf_public_20180810.tar.gz
[ingest] 20180810: remote size 5.3GiB
[ingest] 20180810: complete -- scanned=119815 kept=0 elapsed 4m47s

nights_ingested: 2
total_kept_observations: 21
out_dir: Logs/pipeline_runs/ztf_alert_archive_ingest
```

## Result

- **Night 20180809** (real, small 31.0MiB file, matches the file already
  probed and schema-verified in prior handoffs): scanned all 715 real AVRO
  packets in 3s, kept **21** real observations passing both the `rb >= 0.5`
  filter and the 2-degree sky-box centered on RA 232.6, Dec -8.4. This
  confirms the ingest tool works end-to-end against the real archive and
  produces real `Observation`-shaped records from real detections.
- **Night 20180810** (real, much larger 5.3GiB file): scanned **119,815**
  real AVRO packets over 4m47s, kept **0** — no detection in that night's
  file fell inside the same 2-degree sky box with `rb >= 0.5`. This is a
  legitimate negative result, not a failure: NEOWISE/ZTF field pointings
  are not guaranteed to revisit the same 2-degree patch on consecutive
  nights, and a single moving NEO passing through a 4-square-degree patch
  on one specific night is not expected on every night.
- The run completed with **zero visible progress output during the
  4m47s/119,815-record scan of night 20180810** — this is the exact defect
  fixed in PR #173/v0.90.36 (progress print was gated behind the sky-box/rb
  filter `continue` statements, so it only fired for records that passed
  both). This live run is direct, real-world confirmation that the bug was
  real and not hypothetical: a nearly 5-minute silent stretch on real
  hardware, exactly as predicted before the fix. The operator's `main` was
  at `bdbec1f` (v0.90.35, pre-fix) for this run; v0.90.36 (merged via PR
  #173, already on `main` as of this evidence file) fixes it for future
  runs. No re-run is required solely to see the fixed progress output —
  this run's *data* result (21 kept observations for night 1, 0 for night
  2) remains valid and does not need to be redone.

## Data produced

`Logs/pipeline_runs/ztf_alert_archive_ingest/20180809.json` — real
checkpoint file with `kept_count: 21` real `Observation`-shaped dicts
(local to the operator's Mac; not committed, per the `Logs/**` gitignore
policy). `Logs/pipeline_runs/ztf_alert_archive_ingest/20180810.json` exists
with `kept_count: 0`.

## What this does and does not close

- **Closes**: the "ingest tool confirmed working against the real
  archive" precondition from `docs/ZTF_DR24_PRODUCTION_GATES.md`'s Gate Z3
  Next Coding Step — the tool is no longer purely offline-verified.
- **Does not close**: Gate Z3's "known-object positive control"
  sub-requirement. That needs real per-source detections spanning **at
  least 2 real nights** in the same sky region so `src/link.py` has
  cross-night pairs to link into a tracklet. This run produced real data
  for only 1 night in this specific sky box (night 2 had zero matches
  here). The next step is either (a) a wider sky box and/or a longer night
  list so a real multi-night match is more likely, or (b) targeting a
  known NEO's real historical sky position/date pair (e.g. via JPL
  Horizons, already Phase-0-verified) so the ingest tool's sky box is
  centered on a night/position pair known to contain a real detection.
