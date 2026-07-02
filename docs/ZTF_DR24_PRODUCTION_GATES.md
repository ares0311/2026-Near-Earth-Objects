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
| Z3: Source-native candidate linking | Partially satisfied by existing code; real-detection dependency identified | `src/link.py`'s linear-motion tracklet linker (THOR/Fink-FAT-style: motion-rate window, satellite-trail rejection, chi-squared arc consistency, requires >=3 detections on >=2 nights) is not new -- it is the same production linker used by every prior gate. A ZTF-cadence synthetic positive control already exists and passed (`data/injection_recovery_n200.json`: n=200, 100% detection/link/score), via `Skills/injection_recovery.py --survey ZTF`, but that evidence predates the ZTF DR24 primacy pivot and needs re-confirmation under current code before it counts as Z3 evidence. The older ALeRCE-backed provider is real source-level ZTF pilot evidence, but it is not accepted as the current DR24 historical-replay production source unless its schema, bounds, and no-future-leakage implications are verified for that role. Real blocker identified: Gate Z1 ingests ZTF image/exposure *metadata* only (sky position, field, filter, obsdate) -- it does not yet ingest per-source moving-object detections (ra/dec/mag per alert), so there is nothing real to link yet. The "known-object positive control" sub-requirement cannot be satisfied until a verified per-source ZTF DR24 detection source exists (a new, not-yet-Phase-0-verified endpoint -- candidate: IRSA's ZTF Lightcurve Queries API, not yet checked against the live API). |
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

Work Gate Z3 by verifying a per-source ZTF DR24 detection source before adding
more linking or ranking code. The existing linker is already adequate for the
first ZTF-cadence positive controls; the missing input is real source-level
detections with RA, Dec, observation time, and photometry. Use only official
documentation or live evidence for endpoint, schema, and request-body choices.
Do not guess URLs or schemas. Legacy ALeRCE support may be evaluated, but it
must not be assumed to satisfy DR24 historical replay without the same
documentation. Candidate sources must first be documented with auth
requirements, bounded query limits, sample row schema, and no-future-catalog-
leakage implications before being wired into the production pipeline.
