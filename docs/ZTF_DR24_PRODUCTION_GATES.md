# ZTF DR24 Production Gates

Last updated: 2026-07-02
Applies to: ZTF DR24 archival historical replay, the current primary discovery
path defined in `docs/MISSION.md` and `docs/neo_discovery_agent_brief.md`.

This gate register supersedes the WISE/DECam/TESS P1-P5 gates only for the
current primary path. The older gates remain valid historical evidence for the
secondary path, but they do not establish readiness for ZTF DR24 historical
replay.

## Production Definition

For the ZTF DR24 path, production readiness means the project can run a bounded,
time-aware historical replay over public archival ZTF data, exclude objects that
were knowable at the replay cutoff, link moving-source candidates, rank them
with auditable evidence, reject low-confidence cases, and package survivors for
operator review under fail-closed submission controls.

Production readiness does not require that a genuinely new NEO has already been
found. A confirmed discovery is an event-driven outcome after MPC/NEOCP review,
not a precondition for running the production search.

## Gates

| Gate | Status | Closure evidence required |
|---|---|---|
| Z0: Phase 0 source verification | Closed except Fink external blocker | `docs/evidence/phase0/` contains live evidence for JPL SBDB, MPC get-obs, and IRSA ZTF metadata; Fink TLS failure is documented as external; pretrained model use is deferred. |
| Z1: Bounded replay ingest | Closed (2026-07-02) | `Skills/ztf_dr24_bounded_ingest.py` queries only the Phase 0-verified IRSA ZTF sci-metadata endpoint (`POS`/`SIZE`/`WHERE obsjd`/`COLUMNS`, all documented in IRSA's own API docs, not guessed), enforces a bounded search box and time window, checkpoints/resumes, retries with backoff, and writes a sample ingest report with row counts, distinct-night/field counts, and a sha256 of the raw response. Unit-tested offline against an astropy-generated IPAC fixture (8 tests, all passing). **Operator live run (2026-07-02)** against the real IRSA endpoint (RA 232.6, Dec -8.4, 2 deg box, 10-day window) returned a real, non-mocked report: 5 rows, 1 distinct night, 1 distinct field -- see `docs/evidence/live/2026-07-02-gate-z1-bounded-ingest-first-live-run.md`. |
| Z2: Time-aware known-object exclusion | Core mechanism code complete, pending operator field verification | `src/known_object_exclusion.py` implements the brief's `known_object_catalog_snapshots`/`known_objects` schema verbatim and a `known_as_of(objects, cutoff)` filter using each object's own `first_obs` date (a documented JPL SBDB Query API field, confirmed via official docs and a live astroquery example -- not guessed) so a single current-day snapshot can be used correctly for any historical replay cutoff without needing true point-in-time catalog snapshots. Fails closed on missing `first_obs` (never treats an object as confirmed-known without evidence) and on a snapshot missing/violating its own `valid_for_replay_before_utc`. 9 offline tests cover every boundary (exact-cutoff equality, missing-date fail-closed, snapshot validity). Not yet closed: needs operator confirmation that adding `first_obs` to the already-verified `sb-group=neo` JPL SBDB query actually returns real dates live, and Gate Z3's tracklet linker before this can be exercised against real candidates instead of synthetic objects. |
| Z3: Source-native candidate linking | Real second night with confirmed coverage found via targeted ephemeris scan (2026-07-02); positive-control loader/runner built and offline-verified; final live linking attempt not yet run | `src/link.py`'s linear-motion tracklet linker is unchanged from prior gates. The real-detection source blocker is resolved (UW ZTF alert archive, confirmed reachable and schema-verified). Blind field-revisit sampling (nights 20180810, 20180902 at the original fixed field) found zero detections -- diagnosed as a targeting error, not a data problem: real ephemeris for known object 72966 showed the object had moved ~9.4 deg in RA by night 20180902. `Skills/scan_neo_track_coverage.py` (v0.90.41) then found real ZTF coverage at the object's actual predicted position on night 20180903 (6 real sci exposure rows) -- see `docs/evidence/live/2026-07-02-gate-z3-track-coverage-scan-hit.md`. **New (v0.90.42)**: `Skills/run_archive_positive_control.py` loads real per-source `Observation` objects from >=2 nights' checkpoint files and runs the exact production `preprocess()` -> `detect()` -> `link()` chain. Offline verification surfaced a real parameter-sensitivity finding: `link()`'s default `min_observations=3` can reject a genuine 2-night tracklet when each night contributes only 1-2 observations; `--min-observations` is exposed to re-check before concluding failure. **Still open**: night 20180903's alert-archive ingest has not yet been run, so the positive control itself has not yet been attempted against real data. |
| Z4: Auditable ranking baseline | Open | Handcrafted tabular features plus logistic regression baseline are evaluated before LightGBM/XGBoost. Metrics include recall@K or purity@K, false-positive review burden, calibration error, and ablation against a simple baseline. |
| Z5: Retrospective validation | Open | Historical replay candidates are evaluated against later MPC/JPL outcomes after the replay window without future leakage. The report must separate recovered known objects, later-confirmed objects, artifacts, and unresolved candidates. |
| Z6: No-submission package drill | Open | At least one ZTF DR24 review packet, synthetic or recovered-known if needed, passes through adversarial review and ADES/export tooling in dry-run mode with no external submission and no impact-probability claim. |
| Z7: Operator runbook update | Open | `docs/OPERATOR_GO_NO_GO_RUNBOOK.md` includes the ZTF DR24-specific packet locations, review checklist, source attribution rule, and fail-closed MPC submission path. |

## Stop Conditions

Stop the production loop and ask for operator action only when one of these
conditions is true:

- A live command requiring the operator's Mac credentials, Keychain, or network
  access is necessary and cannot be performed from the coding-agent environment.
- A bounded replay would download or compute beyond the documented local system
  profile without explicit operator approval.
- A candidate reaches the point where external MPC submission could be
  considered.
- A public source contradicts the recorded Phase 0 behavior and needs a fresh
  live verification packet.

Do not stop merely because no candidate has been found.

## Next Coding Step

**Superseded 2026-07-02**: the per-source ZTF DR24 detection source, its
schema, and a bounded multi-night ingest tool are now all built and
**confirmed working against the real archive in a live operator run** --
see the Gate Z3 row above and
`docs/evidence/live/2026-07-02-ztf-alert-archive-ingest-first-live-run.md`.
Do not repeat the source search, the schema-field research, or rebuild the
ingest tool from scratch. Do not re-run the exact `20180809`/`20180810`
pair for its own sake -- that data already exists (21 real kept
observations for night 1, 0 for night 2) and does not need to be redone;
the progress-silence bug that run also caught is separately fixed in
v0.90.36/PR #173.

**Why nights 2 and 3 produced zero matches -- now confirmed, not just
inferred**: `ztf_public_20180810.tar.gz` and `ztf_public_20180812.tar.gz`
both had zero detections in the same 2-degree sky box as night 1. A Gate
Z1 live run against the real IRSA sci-metadata endpoint (2026-07-02, see
Gate Z1 row and
`docs/evidence/live/2026-07-02-gate-z1-bounded-ingest-first-live-run.md`)
confirms this is not a linking or ingest problem: across the full 10-day
window from night 1 (JD 2458339.5-2458349.5), IRSA reports **only 1
distinct night and 1 distinct field** with any real science exposure at
this exact sky position. ZTF simply did not point at this field again in
that window. Blindly trying more individual nights against the multi-GB
alert archive is no longer justified -- use the metadata tool first.

**Update 2026-07-02 (v0.90.38)**: the 100-day-window run above was
executed live and found a **real second night** -- 14 rows across 2
distinct nights, 1 field. See
`docs/evidence/live/2026-07-02-gate-z1-wider-window-second-night.md`. The
tool's report initially only exposed `n_distinct_nights` as a bare count,
not which nights -- fixed by adding `distinct_nights_yyyymmdd` (real UTC
calendar dates, matching the alert archive's `ztf_public_YYYYMMDD.tar.gz`
naming) to the report, computed from the already-cached raw response with
no new network call needed.

**Update 2026-07-02 (v0.90.39)**: the first `distinct_nights_yyyymmdd`
output (`['20180808', '20180902']`) had a real off-by-one bug -- JD
increments at noon UTC, not midnight, and the code truncated `obsjd` to an
integer before converting to a calendar date, silently landing on the day
before the correct one. Fixed; see
`docs/evidence/live/2026-07-02-gate-z1-night-date-offbyone-fix.md`. The
corrected real night pair for this sky position is **20180809** (not
20180808) and **20180902** -- roughly 24 days apart, confirming this
specific 2-degree field is genuinely low-cadence, not a bug.

**Update 2026-07-02 (second attempt result)**: that command was run.
Night 20180809 resumed from cache (21 kept, unchanged). Night 20180902
(real, confirmed exposure via Gate Z1) downloaded 8.5GiB, scanned 192,243
real packets over 7m09s with correct live progress/ETA throughout
(confirms the v0.90.36 and v0.90.39 fixes both work together on a real,
large file) -- but kept **0**. This is a genuine negative, not a bug: see
`docs/evidence/live/2026-07-02-ztf-alert-archive-ingest-second-attempt.md`.
Two real multi-GB downloads (5.3GiB + 8.5GiB) have now produced zero net
progress toward a linkable 2-night pair via blind field-revisit sampling.
**Blind field-revisit sampling is no longer the recommended next step.**

**Next step (v0.90.40)**: target a real, known NEO instead of an arbitrary
field. `Skills/lookup_neo_archive_ephemeris.py` queries the Phase-0-verified
JPL Horizons endpoint (`src/fetch.py:fetch_horizons`, already 100%-covered
production code) for a real object's real predicted sky position across a
date range, so the alert-archive ingest tool can target a specific real
position instead of guessing. Default designation `72966` is the real
`ssnamenr` cross-match already present in a real Gate Z3 alert packet
(not a guess -- see
`docs/evidence/phase0/2026-07-02-gate-z3-uw-alert-archive-candidate.md`):

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/lookup_neo_archive_ephemeris.py \
    --designation 72966 \
    --start-jd 2458339.5 --end-jd 2458439.5 --step 1d
```

This prints the object's real predicted RA/Dec on each real calendar night
in the window. **That first live run was executed (2026-07-02)** and
revealed a real targeting error, not just a low-cadence field: by night
20180902 the object's real predicted position had moved ~9.4 deg in RA
and ~3.2 deg in Dec from the original fixed 2-degree search box used in
the second alert-archive attempt -- the earlier "Gate Z1 hit" for that
night was a coincidental revisit of the *original* field, unrelated to
where the object actually was. See
`docs/evidence/live/2026-07-02-neo-72966-ephemeris-and-targeting-error.md`.

**Next step (v0.90.41)**: `Skills/scan_neo_track_coverage.py` re-centers
the cheap Gate Z1 metadata check on each candidate night's real predicted
position (not a stale fixed field), for a bounded, stride-limited subset
of real ephemeris points:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/scan_neo_track_coverage.py \
    --designation 72966 \
    --start-jd 2458339.5 --end-jd 2458439.5 --step 1d --stride 5
```

This checks 1 of every 5 real nights (21 metadata queries, cheap) at the
object's real predicted position for that night, and reports which (if
any) had real ZTF science exposure there. Only once a real, non-guessed
night with confirmed real coverage near the object's real position is
found should `Skills/ztf_alert_archive_ingest.py` be run against it (using
that night's predicted RA/Dec as the search center, not the original
fixed field) -- do not skip straight to the expensive alert-archive step
without this cheap check first.

**Update 2026-07-02 (real hit found)**: that scan was run live. Real
result: 2 of 21 checked nights had real ZTF coverage -- night 20180809
(already known) and **night 20180903** (new, RA 242.0130, Dec -11.6968,
6 real sci exposure rows) -- found via targeted ephemeris-based scanning,
not blind guessing. See
`docs/evidence/live/2026-07-02-gate-z3-track-coverage-scan-hit.md`.

**Next step**: run the alert-archive ingest tool against night 20180903,
centered on this night's real predicted position (not the stale original
field used in the earlier failed attempt):

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20180903 \
    --ra 242.0130 --dec -11.6968 --radius-deg 2.0 --min-rb 0.5
```

Night 20180809's existing cached data (21 kept, centered on RA 232.6/Dec
-8.4, within ~0.05 deg of 72966's real predicted position that night)
already covers this object's real location and does not need re-fetching.
If night 20180903 also yields >=1 kept observation, this project will have
real per-source detections on 2 real nights for the first time.

**Update 2026-07-02 (loader/runner built, v0.90.42)**: the positive
control loader/runner is now built --
`Skills/run_archive_positive_control.py` loads real per-source
`Observation` objects from >=2 nights' checkpoint files and runs the exact
production `preprocess()` -> `detect()` -> `link()` chain, reporting
whether a real multi-night tracklet forms. Offline verification (using
the exact synthetic generator already proven in
`Skills/injection_recovery.py`'s baseline) found a real parameter-
sensitivity issue: `link()`'s default `min_observations=3` can reject a
genuine 2-night tracklet when each night contributes only 1-2
observations to the final arc. Real archived data has far more
observations per night (21 on night 20180809 alone) so the default is
likely fine, but `--min-observations 2` is available to re-check a
zero-tracklet result before concluding failure.

Once night 20180903's alert-archive ingest completes (see the command
above), run:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/run_archive_positive_control.py \
    --nights 20180809 20180903 \
    --out Logs/pipeline_runs/run_archive_positive_control/report.json
```

If this reports zero tracklets, re-run with `--min-observations 2` before
concluding the positive control failed.

The same dump also revealed the packet includes ZTF's own solar-system
cross-match fields (`ssnamenr`/`ssdistnr`/`ssmagnr`) -- do NOT wire these
into known-object exclusion logic yet; their catalog provenance and
update-cadence relative to no-future-leakage requirements has not been
researched. Continue using `src/known_object_exclusion.py`'s existing JPL
SBDB `first_obs` approach as the only currently-verified mechanism for that
gate.
