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
| Z1: Bounded replay ingest | Code complete, pending operator live verification | `Skills/ztf_dr24_bounded_ingest.py` queries only the Phase 0-verified IRSA ZTF sci-metadata endpoint (`POS`/`SIZE`/`WHERE obsjd`/`COLUMNS`, all documented in IRSA's own API docs, not guessed), enforces a bounded search box and time window, checkpoints/resumes, retries with backoff, and writes a sample ingest report with row counts, distinct-night/field counts, and a sha256 of the raw response. Unit-tested offline against an astropy-generated IPAC fixture (8 tests, all passing). Not yet closed: needs one real operator-run command against the live IRSA endpoint to produce a genuine (non-mocked) ingest report before this gate can close. |
| Z2: Time-aware known-object exclusion | Core mechanism code complete, pending operator field verification | `src/known_object_exclusion.py` implements the brief's `known_object_catalog_snapshots`/`known_objects` schema verbatim and a `known_as_of(objects, cutoff)` filter using each object's own `first_obs` date (a documented JPL SBDB Query API field, confirmed via official docs and a live astroquery example -- not guessed) so a single current-day snapshot can be used correctly for any historical replay cutoff without needing true point-in-time catalog snapshots. Fails closed on missing `first_obs` (never treats an object as confirmed-known without evidence) and on a snapshot missing/violating its own `valid_for_replay_before_utc`. 9 offline tests cover every boundary (exact-cutoff equality, missing-date fail-closed, snapshot validity). Not yet closed: needs operator confirmation that adding `first_obs` to the already-verified `sb-group=neo` JPL SBDB query actually returns real dates live, and Gate Z3's tracklet linker before this can be exercised against real candidates instead of synthetic objects. |
| Z3: Source-native candidate linking | Real per-source detection source found, downloaded, and schema-verified live; bulk multi-night ingest and real linking still open | `src/link.py`'s linear-motion tracklet linker (THOR/Fink-FAT-style: motion-rate window, satellite-trail rejection, chi-squared arc consistency, requires >=3 detections on >=2 nights) is unchanged from prior gates. **The real-detection blocker that previously gated this row is now resolved**: the University of Washington's public ZTF alert archive (`https://ztf.uw.edu/alerts/public/`) was found via WebSearch, confirmed reachable (HTTP 200, no auth) via `Skills/verify_ztf_dr24_sources.py`, confirmed with a real operator-captured directory listing (`docs/Alert Archive.pdf`) showing the real `ztf_public_YYYYMMDD.tar.gz` naming convention and full 2018-06-01-to-present coverage, and confirmed live by `Skills/probe_ztf_alert_archive_file.py --inspect-first-packet`: a real downloaded night (`ztf_public_20180809.tar.gz`, 715 real `.avro` alert packets) parses correctly and its `candidate` record (100 fields total) contains real `ra`/`dec`/`jd`/`magpsf`/`sigmapsf`/`fid` values, plus `cutoutScience`/`cutoutReference`/`cutoutDifference` (useful for Tier 2 CNN) and `prv_candidates` (prior-detection context) -- not guessed, not a placeholder. Full trail: `docs/evidence/phase0/2026-07-02-gate-z3-uw-alert-archive-candidate.md`. **Still open**: no bulk multi-night ingest tool exists yet (only a single-file verification probe); no real per-source detections have been run through `src/link.py` end-to-end; the "known-object positive control" sub-requirement (linking real alerts across >=2 real nights into a tracklet matching a known NEO) has not been attempted. Nightly file sizes vary widely (up to 73G) so a bounded multi-night ingest tool must filter/bound carefully -- do not attempt a naive full-night download loop. |
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

**Superseded 2026-07-02**: the per-source ZTF DR24 detection source this
section previously asked for is now found, live-verified, and
schema-confirmed -- see the Gate Z3 row above and
`docs/evidence/phase0/2026-07-02-gate-z3-uw-alert-archive-candidate.md`.
Do not repeat that search or re-evaluate ALeRCE for this purpose.

The next coding step is a **bounded, checkpointed, multi-night real-detection
ingest tool** against the confirmed UW ZTF alert archive
(`https://ztf.uw.edu/alerts/public/`), built the same way as every prior
gate's tooling: explicit bounds (a small number of nights, not an unbounded
loop), checkpoint/resume, retry-with-backoff, and a sample ingest report.
Given real nightly file sizes range up to 73G, do not naively download and
fully parse whole nights -- the tool should stream-parse each night's tar
(as `Skills/probe_ztf_alert_archive_file.py` already does for one file) and
extract only the fields the pipeline's `Observation` schema needs: `ra`,
`dec`, `jd`, `magpsf`/`mag`, `sigmapsf`/`mag_err`, `fid`/`filter_band`, and
`rb` for real_bogus_score (all six field names confirmed live via
`--dump-all-fields`, see
`docs/evidence/phase0/2026-07-02-gate-z3-uw-alert-archive-candidate.md`).
**`drb` is NOT present in the 2018-era packet checked** -- do not assume it
exists on other nights without checking `schemavsn` first; fall back to
`rb`-only if `drb` is absent, do not fail closed on its absence alone since
`rb` alone is already a valid real_bogus_score input.

The same dump also revealed the packet includes ZTF's own solar-system
cross-match fields (`ssnamenr`/`ssdistnr`/`ssmagnr`) -- do NOT wire these
into known-object exclusion logic yet; their catalog provenance and
update-cadence relative to no-future-leakage requirements has not been
researched. Continue using `src/known_object_exclusion.py`'s existing JPL
SBDB `first_obs` approach as the only currently-verified mechanism for that
gate.

Once real per-source `Observation` objects exist for >=2 real nights, run
them through the existing `src/link.py` linker for Z3's "known-object
positive control": pick a real, documented multi-night NEO detection window
(cross-checked against MPC) and confirm the linker recovers a matching
tracklet from the real archived alerts.
