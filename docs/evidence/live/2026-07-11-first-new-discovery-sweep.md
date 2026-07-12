# First Genuinely New ZTF DR24 Discovery Sweep (Not Z3-Tied)

Date: 2026-07-11/12
Scope: First ZTF DR24 archival discovery-search run on a field selected via
the population-bias algorithm (`Skills/select_survey_fields.py --mode aten`)
rather than one chosen to track a known designation (contrast with Gate Z3's
four apparitions of 72966). Non-submitting throughout.

## Target Selection

- `Skills/select_survey_fields.py --jd 2459107.5 --mode aten --top-n 8`
- Top field: RA 89.3, Dec 22.5, radius 3.5 deg, score 0.9238, elongation
  83.0 deg (near-optimal quadrature/dawn-dusk geometry).
- Selection persisted to `data_selection/target_priority_queue.csv` (rank 1
  of that run's 8-row batch) and logged in
  `data_selection/data_selection_decision_log.md` under
  "2026-07-11 — First genuinely new ZTF DR24 discovery-field selection".
- Window: 2020-09-14 / 2020-09-16 (JD 2459106.5–2459108.5) — the one
  calendar year not present in any prior ingest at the time of selection.

## Ingest

Real `Skills/ztf_alert_archive_ingest.py --ra 89.3 --dec 22.5 --radius-deg 2.0`
runs against the UW public ZTF alert archive:

| Night | Remote size | Scanned | Kept | Wall time |
|---|---|---|---|---|
| 20200914 | 7.2 GiB | 159,928 | 12 | ~2h10m (see note below) |
| 20200916 | (not logged) | 126,046 | 316 | ~2h |

Note: the first night's initial throughput was severely I/O-bound
(~110KB/s, ETA briefly over 17h) before accelerating substantially partway
through the transfer; total wall time for both nights combined was under 3
hours. Diagnosed live with the operator using `ps`/`nettop` on the
operator's Mac (CPU 0.3% on the ingest process, ruling out CPU-bound
parsing) — see conversation record for the full diagnostic. Root cause not
conclusively isolated to either server-side per-connection throttling or
general network variability; both nights were run as concurrent processes
per this project's sharding-by-independent-file standing rule.

A real, live-tested bug was found and fixed in the same session: the
ingest tool's checkpoint was keyed by night only, not by (night, field),
so re-querying an already-ingested night with a different sky box would
have silently returned the wrong field's cached data. Fixed to fail closed
on any query-parameter mismatch; see commit `a0fb56e0` and the module
docstring in `Skills/ztf_alert_archive_ingest.py`.

## Analysis

`Skills/run_archive_positive_control.py --nights 20200914 20200916 --build-review-packets`:

- At the tool's default `min_observations=3`: 0 tracklets (matches the
  tool's own documented sparse-data finding — a 2-night tracklet with few
  observations per night can be rejected outright at the default).
- Re-run at `--min-observations 2` (per the tool's own guidance): **12
  tracklets formed in ~22 seconds total** (10 spanning the real 2-day gap
  between nights, arc 2.01–2.09d, motion rates 4.18–53.82 arcsec/hr, all
  within this project's plausible solar-system-object range; 2 spanning
  only 1 night at ~0.02–0.03d arc, likely spurious same-night pairings).
- All 12 piped through `Skills/adversarial_review.py --offline`:
  **12/12 REJECT.** Dominant disqualifying challenges: `orbit_quality`
  (12/12 — a 2-observation arc cannot support a well-constrained orbit),
  `artifact_posterior` (10/12 — classifier reads these as instrumental
  artifacts), `real_bogus` (8/12 below the 0.90 gate), `arc_length` (2/12).

Raw outputs: `Logs/reports/first_discovery_sweep_20200914_20200916_minobs2.json`
(full tracklet/review-packet detail), `Logs/reports/first_discovery_sweep_adversarial_review.json`
(per-tracklet verdicts) — both local/gitignored; this file is the durable
summary.

## Interpretation

A clean, expected null result — **not a failure of the pipeline or the
target-selection algorithm.** Per `docs/ZTF_DR24_PRODUCTION_GATES.md`'s own
Production Definition: *"Production readiness does not require that a
genuinely new NEO has already been found... Do not stop merely because no
candidate has been found."* The scoring model's own priors (0.05 on
genuine NEO vs. 0.25 on stellar artifact, 0.35 on main-belt asteroid) make
a 12/12 reject outcome on a single 2-night field the statistically
expected result, matching Gate Z6's own precedent (88/88 REJECT on a
different, Z3-tied field).

Target queue rank 1 updated to `status=null_result` with this file cited
in the notes field.

## Next Steps (not yet done)

- Select and ingest additional new fields via the same
  `select_survey_fields.py --mode aten|ieo` process to build a real
  portfolio of searched regions (60/30/10 new/follow-up/control split per
  `docs/astrometrics_data_selection_policy.md`).
- Consider whether `link()`'s default `min_observations=3` should become a
  standing lower default for sparse discovery-search fields, versus
  leaving it as an explicit per-run override — not decided here, flagging
  for operator judgment given it changes a scientific threshold.
