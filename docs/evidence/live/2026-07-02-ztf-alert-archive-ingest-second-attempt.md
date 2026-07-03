# Gate Z3 — second live run of `Skills/ztf_alert_archive_ingest.py` (corrected night pair)

Date: 2026-07-02. Operator: Jerome W. Lindsey III. Branch: `main` @
`8d772d6` (v0.90.39, includes both the progress-print fix from PR #173 and
the JD off-by-one fix from PR #178).

## Command

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20180809 20180902 \
    --ra 232.6 --dec -8.4 --radius-deg 2.0 --min-rb 0.5
```

## Result (console output summarized; full transcript in the operator's
terminal history)

- **Night 20180809**: resumed instantly from the existing local checkpoint
  (21 kept observations from the first Gate Z3 run). No new download.
- **Night 20180902**: fresh download, 8.5GiB, real progress printed
  continuously throughout with a correctly-tracking byte-based ETA (e.g.
  `scanned=100000 kept=0 4.4GiB/8.5GiB (51.8%) elapsed 3m51s ETA 3m35s`) --
  this directly confirms the v0.90.36 progress-print fix and the v0.90.39
  night-date fix both work correctly together on a real, large (192,243-
  packet) night file. Final: `scanned=192243 kept=0 elapsed 7m09s`.
- **Total: 21 kept observations (all from night 1); 0 from night 2.**

## Analysis

This is a genuine, informative negative, not a bug or regression:

- The Gate Z1 metadata query (`docs/evidence/live/2026-07-02-gate-z1-wider-window-second-night.md`,
  now corrected in
  `docs/evidence/live/2026-07-02-gate-z1-night-date-offbyone-fix.md`)
  independently confirmed ZTF took **real science exposures** in this
  field on night 20180902 -- so this is not a "field wasn't observed"
  case like nights 20180810/20180812 were.
- Despite a confirmed real exposure, the alert-archive ingest found **zero**
  real per-source detections passing `rb >= 0.5` inside the 2-degree sky
  box that night. Plausible real-world causes (not mutually exclusive):
  taking a science exposure does not guarantee any difference-image alerts
  are generated for that field/night (most of the sky is unchanging most
  nights); the specific `rb >= 0.5` threshold may exclude legitimate but
  lower-quality detections; or this specific 2-degree patch may simply be
  quiet that night. There is no evidence of a code defect -- the
  progress/ETA output behaved exactly as designed throughout a real,
  large-file run.

## What this means for Gate Z3's "known-object positive control"

Blind field-revisit sampling (try night N, check for any detections) has
now cost two real multi-minute-to-multi-GB downloads (night 20180810:
5.3GiB/0 kept; night 20180902: 8.5GiB/0 kept) for zero net progress toward
a linkable 2-night detection pair. Continuing to guess more individual
nights this way is not an efficient use of the operator's bandwidth.

**Recommended next approach**: instead of picking sky positions/nights
blind and hoping for a detection, target a specific, real, MPC-confirmed
NEO's actual historical ephemeris. Query the already Phase-0-verified JPL
Horizons/SBDB endpoints for a known NEO's real (RA, Dec, JD) positions
across two or more nights confirmed present in the archive (2018-06-04
onward), then run `Skills/ztf_alert_archive_ingest.py` with a sky box
centered on that object's *predicted* position on those specific nights.
This is real, verifiable, non-guessed targeting rather than a blind sample
of an arbitrary field, and directly serves the "known-object" part of the
positive-control requirement (we would know in advance which real object
we are trying to recover, which lets us also confirm the *identity* of any
detections found, not just their existence).

This requires new (currently unbuilt) code: a small helper that queries
JPL Horizons for a chosen NEO's ephemeris at specific epochs and emits the
`--ra`/`--dec`/`--nights` arguments for `ztf_alert_archive_ingest.py`. Not
yet built -- flagged as the next production action.
