# Gate Z3 — first real positive-control run (2026-07-03)

## Command

```bash
caffeinate -i uv run --python 3.14 python Skills/run_archive_positive_control.py \
    --nights 20220817 20220819 \
    --out Logs/pipeline_runs/run_archive_positive_control/report.json
```

Run on `main` @ v0.90.49, real per-source data loaded from the
`Skills/ztf_alert_archive_ingest.py` checkpoints for both nights (267 kept
observations from 20220817, 286 from 20220819 — see
`docs/evidence/live/2026-07-03-gate-z3-six-tab-batch-results.md`).

## Real result

```
[control] Loaded 553 real observation(s) across 2 real night(s)
[control] preprocess: 553/553 sources passed
[control] detect: 116 candidate(s), 0 known match(es)
[control] link: 0 tracklet(s) formed (min_observations=3)
[control] RESULT: no tracklet recovered
```

All 553 real observations passed preprocessing. `detect()` formed 116
candidates (0 matched to the known-object catalog). `link()` formed **0
tracklets** at the linker's default `min_observations=3`.

## Interpretation

This is not necessarily a linking failure — `Skills/run_archive_positive_control.py`'s
own docstring and the v0.90.42 offline finding (in
`tests/test_run_archive_positive_control.py`) established that
`link()`'s default `min_observations=3` can reject a genuine 2-night
tracklet if too few observations from the SAME source land in the linked
arc, even when many detections exist across the field that night. 116
detect-stage candidates across 2 nights with 0 tracklets formed is
consistent with real field crowding: most of these candidates are almost
certainly independent real sources (other stars/asteroids/artifacts in a
2-degree box), not multiple observations of the same object across both
nights — so the correct next diagnostic is not simply lowering
`min_observations`, but confirming whether any candidate genuinely spans
both nights at all before concluding the linker itself under- or
over-rejected.

## Next step (NOT YET DONE)

Re-run with `--min-observations 2` per the documented fallback, to rule out
the threshold-sensitivity finding before concluding this pair does not
positively control:

```bash
caffeinate -i uv run --python 3.14 python Skills/run_archive_positive_control.py \
    --nights 20220817 20220819 --min-observations 2 \
    --out Logs/pipeline_runs/run_archive_positive_control/report_min2.json
```
