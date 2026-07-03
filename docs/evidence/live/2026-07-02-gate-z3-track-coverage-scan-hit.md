# Gate Z3 — first live run of `Skills/scan_neo_track_coverage.py`, real second-night hit found

Date: 2026-07-02. Operator: Jerome W. Lindsey III. Branch: `main` @
`d7f4f42` (v0.90.41).

## Command

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/scan_neo_track_coverage.py \
    --designation 72966 \
    --start-jd 2458339.5 --end-jd 2458439.5 --step 1d --stride 5
```

## Result

21 cheap Gate Z1 metadata checks issued (1 per 5 real ephemeris nights,
stride=5, over 4m32s total), each centered on minor planet 72966's real
predicted position for that specific night (not a fixed field). Real
result: **2 of 21 checked nights had real ZTF science exposure** near the
object's real predicted position:

| Night | RA (deg) | Dec (deg) | Real sci exposure rows |
|---|---|---|---|
| 20180809 | 232.5584 | -8.4239 | 5 |
| 20180903 | 242.0130 | -11.6968 | 6 |

Night 20180809 was already known (this is the night with the existing 21
kept alert-archive observations). **Night 20180903 is a new, real,
non-guessed second night with confirmed real ZTF coverage at the object's
actual predicted position** — found by targeted ephemeris-based scanning
rather than blind field-revisit sampling, which had cost two prior
multi-GB downloads for zero net progress.

## Why this differs from the earlier failed attempts

Nights 20180810 and 20180812 (tried via blind field-revisit sampling) and
night 20180902 (tried at the *original fixed* field, not the object's real
position that night) all came back with zero real coverage or zero kept
detections. Night 20180903 -- one day after the previously-tried
20180902 -- succeeds because it is the real predicted position for that
specific night (RA 242.01, Dec -11.70), not the stale original field
(RA 232.6, Dec -8.4) used in the earlier attempt. This directly confirms
the targeting-error diagnosis in
`docs/evidence/live/2026-07-02-neo-72966-ephemeris-and-targeting-error.md`.

## Next step

Run the alert-archive ingest tool against night 20180903 only, centered on
this night's real predicted position (not the original fixed field):

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20180903 \
    --ra 242.0130 --dec -11.6968 --radius-deg 2.0 --min-rb 0.5
```

Night 20180809's existing cached alert-archive data (21 kept observations,
centered on RA 232.6/Dec -8.4, radius 2.0 -- within ~0.05 deg of 72966's
real predicted position that night, so already covers this object's real
location) does not need to be re-fetched. If night 20180903 also yields
>=1 kept observation, this project will have real per-source detections
on 2 real nights, enabling the first real attempt at Gate Z3's
"known-object positive control" via `src/detect.py` -> `src/link.py`.
