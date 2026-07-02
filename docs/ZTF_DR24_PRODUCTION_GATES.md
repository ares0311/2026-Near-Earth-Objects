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
| Z3: Source-native candidate linking | Real per-source detection source found, downloaded, and schema-verified live; bounded multi-night ingest tool built (code complete, pending operator live run); real linking still open | `src/link.py`'s linear-motion tracklet linker is unchanged from prior gates. The real-detection source blocker is resolved (UW ZTF alert archive, confirmed reachable and schema-verified -- see prior column entries and `docs/evidence/phase0/2026-07-02-gate-z3-uw-alert-archive-candidate.md`). **New**: `Skills/ztf_alert_archive_ingest.py` builds real `src/schemas.py` `Observation` objects from real per-source alerts, using only field names confirmed live (`ra`/`dec`/`jd`/`magpsf`/`sigmapsf`/`fid`-mapped-to-band/`rb`/`field`/`diffmaglim` -- cutouts deliberately left unmapped, their AVRO structure is unverified). Bounded by design: an explicit night list (max 10), streamed directly through gzip/tar decode with a real-bogus threshold and optional sky-box filter applied per-record (never buffers a full night, which can be up to 73G), checkpointed per night, retried with backoff. Verified offline against a synthetic archive matching the real schema: sky-box filtering, real-bogus filtering, and Observation field mapping all confirmed correct; the exact real-packet field values from the Z3 evidence doc were confirmed to construct a valid `Observation`. **Still open**: no live operator run against the real archive yet; no real per-source detections have been run through `src/link.py` end-to-end; the "known-object positive control" sub-requirement has not been attempted. |
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
schema, and a bounded multi-night ingest tool are now all built -- see the
Gate Z3 row above,
`docs/evidence/phase0/2026-07-02-gate-z3-uw-alert-archive-candidate.md`, and
`Skills/ztf_alert_archive_ingest.py`. Do not repeat the source search, the
schema-field research, or rebuild the ingest tool from scratch.

The ingest tool is code-complete and offline-verified but has **not yet been
run against the real archive** (this sandbox has no live internet access).
The next step is an **operator live run**, e.g.:

```bash
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20180809 20180810 \
    --ra 232.6 --dec -8.4 --radius-deg 2.0 --min-rb 0.5
```

(the sky box is centered on the real position already confirmed present in
`ztf_public_20180809.tar.gz`, so night 1 is guaranteed to produce at least
one match; night 2 tests whether the same field was revisited, which is
needed for a multi-night tracklet).

Once real per-source `Observation` objects exist for >=2 real nights (the
ingest tool's checkpoint JSON files under
`Logs/pipeline_runs/ztf_alert_archive_ingest/`), load them and run them
through the existing `src/detect.py` -> `src/link.py` pipeline for Z3's
"known-object positive control": confirm the linker recovers at least one
real multi-night tracklet from the real archived alerts. A pre-identified
known NEO cross-checked against MPC would strengthen this further but is
not required for a first mechanical pipeline exercise on real data.

The same dump also revealed the packet includes ZTF's own solar-system
cross-match fields (`ssnamenr`/`ssdistnr`/`ssmagnr`) -- do NOT wire these
into known-object exclusion logic yet; their catalog provenance and
update-cadence relative to no-future-leakage requirements has not been
researched. Continue using `src/known_object_exclusion.py`'s existing JPL
SBDB `first_obs` approach as the only currently-verified mechanism for that
gate.
