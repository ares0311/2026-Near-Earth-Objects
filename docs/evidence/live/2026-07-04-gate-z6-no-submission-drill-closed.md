# Gate Z6 — no-submission package drill: CLOSED

## Commands and real results

```bash
uv run --python 3.14 python Skills/run_archive_positive_control.py \
    --nights 20220817 20220819 --min-observations 2 --build-review-packets \
    --out Logs/pipeline_runs/run_archive_positive_control/report_with_packets.json
```

Run on `main` @ v0.90.57, reusing the real 88-tracklet result already on
disk from the 20220817/20220819 pair (267+286 kept observations, no new
download). Real result: 88 real `ScoredNEO` review packets built via the
real `classify() -> fit_orbit() -> score() -> process_alert(dry_run=True)`
chain, completed in 25 seconds.

```bash
python3 -c "
import json
report = json.load(open('Logs/pipeline_runs/run_archive_positive_control/report_with_packets.json'))
json.dump(report['review_packets'], open('Logs/pipeline_runs/run_archive_positive_control/review_packets.json', 'w'), indent=2)
"
uv run --python 3.14 python Skills/adversarial_review.py \
    Logs/pipeline_runs/run_archive_positive_control/review_packets.json --offline
```

Real result: **`Summary: 88 candidates reviewed — SURVIVE=0 BORDERLINE=0
REJECT=88`**. Every packet failed on `orbit_quality` (no orbital elements
computed -- expected, since each tracklet has only 2 observations across
2 nights, insufficient for orbit fitting) and most also failed on
`artifact_posterior` (stellar_artifact posterior ~0.656, consistently
above the 0.3 threshold) and/or `real_bogus` (many packets below the 0.9
submission gate). This is the correct outcome: these 88 tracklets are
combinatorial pairings of unrelated real sources in a crowded field (per
`docs/evidence/live/2026-07-04-gate-z3-no-tracklet-matches-72966.md`), not
real single-object NEO candidates -- automated adversarial review
correctly rejected all of them rather than falsely advancing any to
operator review.

```bash
uv run --python 3.14 python Skills/export_ades_report.py \
    Logs/pipeline_runs/run_archive_positive_control/review_packets.json
```

Real result: valid ADES PSV-format text generated for all 88 packets
(`# version=A22`, `! mpcCode XXX`, one `data` block per packet with 2
real observation rows each: real RA/Dec/mag/band/obsTime pulled directly
from the archived ZTF tracklets). `stn=XXX` throughout (the default,
documented first-submission placeholder). Zero network calls made
anywhere in this command -- confirmed by code inspection of
`Skills/export_ades_report.py` (pure local text generation) and by the
absence of any request in the real run's output.

## Gate Z6 closure assessment

`docs/ZTF_DR24_PRODUCTION_GATES.md`'s Z6 closure requirement: "At least
one ZTF DR24 review packet, synthetic or recovered-known if needed,
passes through adversarial review and ADES/export tooling in dry-run
mode with no external submission and no impact-probability claim."

All conditions met with real data:
- Real ZTF DR24 review packets: yes (88, built from real archived alert
  data, not synthetic).
- Passed through adversarial review: yes, in `--offline` mode.
- Passed through ADES export tooling: yes, in dry-run mode (default
  `--obs-code XXX`, no network access).
- No external submission: confirmed -- `process_alert` was called with
  `dry_run=True` throughout, and `export_ades_report.py` only writes
  local text/stdout.
- No impact-probability claim: confirmed -- no impact probability is
  computed or asserted anywhere in this pipeline path.
- No candidate described as "confirmed": confirmed -- all 88 were
  REJECTed by adversarial review and the tooling itself states this is a
  mechanism test only.

**Gate Z6 is CLOSED.**
