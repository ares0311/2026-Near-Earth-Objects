# Gate Z3 — positive control at --min-observations 2 re-run: reproducible, still not confirmed

## Command and result

```bash
caffeinate -i uv run --python 3.14 python Skills/run_archive_positive_control.py \
    --nights 20220817 20220819 --min-observations 2 \
    --out Logs/pipeline_runs/run_archive_positive_control/report_min2.json
```

Re-run on `main` @ v0.90.50 (after PR #192's per-observation-position fix
merged). Real result: 553 observations loaded, 553 preprocessed, 116
candidates detected, **88 tracklets formed** -- identical distribution of
arc lengths (1.94-2.02 days) and motion rates to the first
`--min-observations 2` run (new random tracklet UUIDs each run, but the
same set of rates, e.g. one tracklet at 38.10 arcsec/hr, another at 40.28
arcsec/hr). This confirms the result is deterministic given the same
input checkpoints, not a flaky/random artifact.

## Why the console output alone can't confirm a match

`Skills/run_archive_positive_control.py`'s console print statement does
not include per-observation RA/Dec (only the written JSON report does, as
of v0.90.50). Eyeballing rates against the expected 38.70 arcsec/hr for
designation 72966 is not sufficient -- multiple unrelated real sources in
a crowded 116-candidate field can coincidentally share a similar rate.

## Fix: dedicated position-matching tool (v0.90.51, this PR)

`Skills/match_positive_control_tracklet.py` reads the already-written
`report_min2.json` (no pipeline re-run needed) and ranks every
2-observation tracklet by real angular offset (arcsec) from the two known
reference positions (257.0809/-10.7456 and 257.5497/-10.9843 -- the real
MPC-reported positions of designation 72966 on those two nights). This
directly answers "is any tracklet actually near the object" rather than
"does any tracklet have a plausible rate."

## Next step (NOT YET DONE)

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
uv run --python 3.14 python Skills/match_positive_control_tracklet.py \
    Logs/pipeline_runs/run_archive_positive_control/report_min2.json \
    --ref1 257.0809 -10.7456 \
    --ref2 257.5497 -10.9843
```

If the best-ranked tracklet's total offset is small (consistent with real
astrometric/orbit-propagation error, likely sub-arcmin to a few arcsec),
that is real supporting evidence for a genuine Gate Z3 recovery. If the
best offset is large, the 88 tracklets are almost certainly combinatorial
artifacts of a crowded field and this candidate pair should be treated as
a Gate Z3 negative, prompting escalation to a tighter, more precisely
centered re-ingest rather than further linker-threshold tuning.
