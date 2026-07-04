# Gate Z3 — positive control at --min-observations 2: 88 tracklets, not yet confirmed as the real object

## Command and real result

```bash
caffeinate -i uv run --python 3.14 python Skills/run_archive_positive_control.py \
    --nights 20220817 20220819 --min-observations 2 \
    --out Logs/pipeline_runs/run_archive_positive_control/report_min2.json
```

Run on `main` @ v0.90.49. Real result: 553 observations loaded, all 553
preprocessed, 116 candidates detected, **88 tracklets formed** at
`min_observations=2` (each with exactly 2 observations, one per night,
arc lengths 1.94-2.02 days, motion rates spanning ~4.5 to ~59.9 arcsec/hr).

## Root cause of why 88 tracklets is not evidence of success (diagnosed, not guessed)

The search box for both nights was centered on real MPC-confirmed
observations of designation 72966 (RA/Dec 257.0809/-10.7456 on 20220817,
257.5497/-10.9843 on 20220819 -- see
`docs/evidence/live/2026-07-02-gate-z3-full-mpc-scan-30-hits.md`). With
116 real detect-stage candidates split across 2 nights (roughly 45-70 per
night after preprocessing/detection), and `link()`'s motion-rate window
being intentionally broad (0.05-60 arcsec/hr, per `docs/PIPELINE_SPEC.md`'s
THOR-inspired range), **at `min_observations=2` there is no orbit-
consistency (chi-square) check available** -- `link.py` only applies that
rejection test to arcs with >=3 observations. Any two points from
different nights whose implied motion rate happens to fall in that broad
window will form a "tracklet." With a crowded 2-degree-radius field, many
unrelated candidate pairs are statistically likely to produce rates
somewhere in a nearly-two-orders-of-magnitude window. **88 tracklets is
therefore consistent with combinatorial cross-matching of unrelated
sources, not confirmation of a positive control.**

## Expected real motion of designation 72966 between the two center positions

Computed directly from the two real MPC-confirmed positions used to
center the search boxes (not guessed):

```
RA1,Dec1 = 257.0809, -10.7456   (20220817, real MPC-reported position)
RA2,Dec2 = 257.5497, -10.9843   (20220819, real MPC-reported position)
separation = 1866.9 arcsec
implied rate = 38.70 arcsec/hr  (assuming ~2.01 day arc, matching most tracklets' arc_days)
implied position angle = 117.4 deg
```

Several of the 88 printed tracklets have rates close to this value:
`8633d484` (39.27), `493670aa` (39.18), `2c7ffc58` (38.10), `2eef9da0`
(37.97), among others. **Rate proximity alone is not sufficient
confirmation** -- multiple unrelated real sources in a crowded 2-degree
box can coincidentally share a similar rate. Confirming which (if any) of
the 88 tracklets is the actual real object requires each tracklet's
per-observation RA/Dec, which the original `report_min2.json` schema did
not include.

## Fix: extend the report schema with per-observation positions (not yet re-run)

`Skills/run_archive_positive_control.py` updated to add
`motion_pa_degrees` and a per-observation `[{ra_deg, dec_deg, jd}, ...]`
list to each tracklet summary in the JSON report, so the tracklet(s)
nearest the two known real center positions can be identified directly by
angular offset rather than by rate alone. This is a minimal, targeted
extension directly serving Gate Z3's verification need -- not a general
new API.

## Next step (NOT YET DONE)

Re-run the same command (now with the updated script) and inspect
`report_min2.json`'s `tracklets[].observations` for the tracklet whose two
positions are closest to (257.0809, -10.7456) and (257.5497, -10.9843).
That is the only way to determine whether the positive control actually
recovered designation 72966, versus recovering an unrelated combinatorial
pairing. Until this check is done, the 88-tracklet result should be read
as "the linker is mechanically capable of forming cross-night links from
real archived detections," not as "Gate Z3 is confirmed."
