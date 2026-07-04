# Gate Z3 — no tracklet matches designation 72966's real position (2026-07-04)

## Command and real result

```bash
uv run --python 3.14 python Skills/match_positive_control_tracklet.py \
    Logs/pipeline_runs/run_archive_positive_control/report_min2.json \
    --ref1 257.0809 -10.7456 \
    --ref2 257.5497 -10.9843
```

Run on `main` @ v0.90.51 against the operator's already-produced
`report_min2.json` (88 tracklets from the `--min-observations 2`
positive-control run). Real result -- best match:

```
Best candidate: ce90f4b9-732a-48de-a98d-9e99724959bb with total offset
4172.4 arcsec (69.5 arcmin, 1.16 deg) from the real reference positions.
```

**This rules out all 88 tracklets as a match for designation 72966.** A
real astrometric/orbit-propagation offset would be at most a few arcmin;
69.5 arcmin (over 1 degree) is far too large to be the same object. The
next four closest tracklets were similarly large (4176.7, 4728.3, 4728.4,
5338.6 arcsec). This is a genuine negative for this specific candidate
pair's *linked tracklets*, not an inconclusive result.

## Root cause: link() has no positional check, only rate consistency

`link()` builds 2-observation tracklets solely by testing whether the
implied motion rate between two candidates (one per night) falls in the
allowed window (0.05-60 arcsec/hr) -- it never checks proximity to a
target position. In a crowded 116-candidate field, the real object's own
two genuine detections (if captured that night) may simply never be
paired together: a greedy/exhaustive pairing algorithm can assign either
observation to a different, unrelated candidate with a similarly
plausible rate before the true pair is ever considered. This means "no
tracklet near the known position" does NOT by itself prove ZTF failed to
detect the object that night -- it only proves the *linker's specific
pairing choices* didn't produce it.

## Next diagnostic (new tool, this PR): check raw observations directly

`Skills/find_nearest_raw_observation.py` bypasses detect()/link() entirely
and searches a single night's raw kept observations (from the
`ztf_alert_archive_ingest.py` checkpoint already on disk) for the nearest
real detection to the known reference position. This answers a narrower,
prior question: did ZTF's archive record *any* confident (rb >= 0.5)
detection near the real reported position that night at all?

## Next step (NOT YET DONE)

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
uv run --python 3.14 python Skills/find_nearest_raw_observation.py \
    Logs/pipeline_runs/ztf_alert_archive_ingest/20220817.json \
    --ref 257.0809 -10.7456
uv run --python 3.14 python Skills/find_nearest_raw_observation.py \
    Logs/pipeline_runs/ztf_alert_archive_ingest/20220819.json \
    --ref 257.5497 -10.9843
```

If both nights show a real observation within a small offset (tens of
arcsec, consistent with real astrometric error) of the known position,
the object WAS captured but the linker failed to pair it -- a linker
limitation, not a data-availability problem, and the fix would be a
position-aware linking pass rather than another ingest. If neither night
shows a close raw observation, ZTF's archive did not record a confident
alert-level detection of the real object at that position that night,
which is consistent with the previously-diagnosed "sci exposure existing
does not guarantee an alert fired" finding, and this candidate pair should
be treated as exhausted for Gate Z3.
