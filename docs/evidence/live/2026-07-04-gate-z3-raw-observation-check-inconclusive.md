# Gate Z3 — raw-observation proximity check: night 2 has no plausible match

## Commands and real results

```bash
uv run --python 3.14 python Skills/find_nearest_raw_observation.py \
    Logs/pipeline_runs/ztf_alert_archive_ingest/20220817.json \
    --ref 257.0809 -10.7456
uv run --python 3.14 python Skills/find_nearest_raw_observation.py \
    Logs/pipeline_runs/ztf_alert_archive_ingest/20220819.json \
    --ref 257.5497 -10.9843
```

Run on `main` @ v0.90.52 against the operator's existing local checkpoints
(267 kept observations for 20220817, 286 for 20220819).

**Night 20220817** (267 real observations): closest real detection is
**74.1 arcsec** away (`real_bogus=0.85`) -- plausibly consistent with real
astrometric/orbit-propagation error, though not confirmable on its own in
a crowded field (the systematic MPC scan's own reference position derives
from an MPC-reported observation, not necessarily at the exact same JD as
this ZTF exposure, so some offset is expected even for a genuine match).

**Night 20220819** (286 real observations): closest real detection is
**615.7 arcsec (10.3 arcmin)** away (`real_bogus=0.61`) -- far too large
to be explained by normal intra-night motion (the object's own expected
rate is ~38.7 arcsec/hr; 615.7 arcsec of drift would require ~16 hours,
inconsistent with typical single-night astrometric/timing differences).

## Interpretation

A real, high-confidence detection exists near the object's expected
position on night 1, but **no comparably close detection exists on night
2** at all. This does not by itself prove ZTF failed to image the true
position on 20220819 (a lower real-bogus-threshold or wider search could
still find something closer, or the true detection could have been
dropped by the `rb >= 0.5` cutoff already applied at ingest time) --  but
with the data as ingested, there is no candidate on night 2 within a
plausible tolerance of the known reference position. Combined with
`docs/evidence/live/2026-07-04-gate-z3-no-tracklet-matches-72966.md`'s
finding that no linked tracklet is near either position, this specific
2-night pair (20220817/20220819) does not currently support a genuine
Gate Z3 positive control.

## Next step (NOT YET DONE): try the other real candidate pair

The six-tab batch also produced substantial real kept observations for a
different apparition of the same designation 72966:
20210106 (kept=272, ref RA/Dec 116.1336/8.6041) and 20210111 (kept=177,
ref RA/Dec 114.9238/8.8044) -- see
`docs/evidence/live/2026-07-03-gate-z3-six-tab-batch-results.md`. This
pair has never been run through `run_archive_positive_control.py`. Run the
same sequence used for the 20220817/20220819 pair:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/run_archive_positive_control.py \
    --nights 20210106 20210111 --min-observations 2 \
    --out Logs/pipeline_runs/run_archive_positive_control/report_20210106_20210111.json
```

Then rank the resulting tracklets with
`Skills/match_positive_control_tracklet.py` against the real reference
positions above, and if that comes back inconclusive too, check raw
observations directly with `Skills/find_nearest_raw_observation.py` as
done here. If both candidate pairs (5 real apparitions checked total
across this project) fail to positively control, this should be
escalated as a documented open question rather than continuing to try
more individual nights -- see the "Next Coding Step" discussion in
`docs/ZTF_DR24_PRODUCTION_GATES.md`.
