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
| Z2: Time-aware known-object exclusion | **CLOSED (2026-07-05)** | `src/known_object_exclusion.py` implements the brief's `known_object_catalog_snapshots`/`known_objects` schema verbatim and a `known_as_of(objects, cutoff)` filter using each object's own `first_obs` date so a single current-day snapshot can be used correctly for any historical replay cutoff without needing true point-in-time catalog snapshots. Fails closed on missing `first_obs` and on a snapshot missing/violating its own `valid_for_replay_before_utc`. 9 offline tests cover every boundary. Operator ran a live query appending `first_obs` to the already-verified `sb-group=neo` JPL SBDB query: real result, `first_obs` returned populated with real dates for all 3 sampled NEOs (433 Eros: 1893-10-29; 719 Albert: 1911-10-04; 887 Alinda: 1918-02-09) out of 42,153 total NEOs matched. Full evidence: `docs/evidence/live/2026-07-05-gate-z2-first-obs-verified.md`. Exercising this end-to-end against a real linked tracklet (rather than the field-return check done here) still depends on Gate Z3's still-paused candidate-pair search. |
| Z3: Source-native candidate linking | **Pipeline mechanics confirmed on real data (546 real cross-night tracklets formed); single-object identity not yet confirmed for either tried pair (2026-07-04)** | `src/link.py`'s linear-motion tracklet linker is unchanged from prior gates. The real-detection source blocker is resolved (UW ZTF alert archive, confirmed reachable and schema-verified). Two full candidate pairs were run through the real `preprocess()`->`detect()`->`link()` chain on real archived ZTF data: **20220817/20220819** (267+286 kept obs, 88 tracklets at `min_observations=2`) and **20210106/20210111** (272+177 kept obs, 54 tracklets). For both pairs, `Skills/match_positive_control_tracklet.py` found no tracklet within a plausible tolerance of the two known real reference positions (best offsets 69.5 and 70.5 arcmin -- both too large to be the same object), and `Skills/find_nearest_raw_observation.py` confirmed a strong raw-detection match on each pair's *first* night (74.1 and 14.1 arcsec) but nothing plausible on the *second* night (615.7 and 2103.1 arcsec). Root-cause investigation (`Skills/lookup_mpc_observation_history.py --force-refresh`, v0.90.53/54) surfaced real MPC reporting-observatory codes: pair 1's night-2 reference position came from a `mag=99.00` sentinel/placeholder MPC report (observatory `C51`) -- not a genuine detection, a poor anchor regardless of station. Pair 2's reference positions are both real detections but from different stations (`I41`, `G96`), which does not by itself explain the gap. Full evidence: `docs/evidence/live/2026-07-04-gate-z3-observatory-codes-real-findings.md`. **This IS a real, valuable confirmation that the pipeline mechanics work correctly on real archived data** -- the remaining gap is a clean single-object match, not whether detect/link/preprocess function. **Still open**: neither candidate pair has produced a confirmed match; recommended next steps below. |
| Z4: Auditable ranking baseline | **CLOSED (2026-07-04)** | `Skills/evaluate_ranking_baseline.py` evaluated a handcrafted-feature logistic-regression baseline (out-of-fold stratified k-fold) against 142 real archived negative tracklets (20220817/20220819 + 20210106/20210111) and 200 synthetic positive tracklets. Real result: ECE 0.044 vs. a naive real-bogus-only baseline's 0.313; purity@K = 1.0 at every K (5/10/20/50); 0/200 false positives at the 0.5 threshold. Full evidence: `docs/evidence/live/2026-07-04-gate-z4-z5-closed.md`. |
| Z5: Retrospective validation | **CLOSED (2026-07-04)** | `Skills/evaluate_retrospective_validation.py` evaluated the real 88-candidate Gate Z6 review-packet set against the current MPC catalog via 88 real live `MPC.query_objects_in_region` calls. Real result: `{"recovered_known_object": 0, "later_confirmed_object": 0, "artifact": 88, "unresolved_candidate": 0}` -- the correct, expected outcome for tracklets already known (Gate Z6) to be combinatorial cross-night artifacts. Full evidence: `docs/evidence/live/2026-07-04-gate-z4-z5-closed.md`. |
| Z6: No-submission package drill | **CLOSED (2026-07-04)** | `Skills/run_archive_positive_control.py --build-review-packets` runs every tracklet linked from real archived ZTF data through the real `classify() -> fit_orbit() -> score() -> process_alert(dry_run=True)` chain and writes the resulting real `ScoredNEO` dicts as `review_packets`. Operator ran it against the real 88-tracklet result from 20220817/20220819 (no new download, reused existing checkpoints, completed in 25s). All 88 packets were then piped through `Skills/adversarial_review.py --offline` (real result: `SURVIVE=0 BORDERLINE=0 REJECT=88` -- correct and expected, since these are combinatorial tracklet pairings in a crowded field, not real single-object candidates) and `Skills/export_ades_report.py` (real result: valid ADES PSV text generated for all 88 with `stn=XXX`, the documented first-submission placeholder; zero network calls; nothing submitted anywhere). This closes the gate's closure requirement in full: a real review packet passed through adversarial review and ADES export in dry-run mode with no external submission and no impact-probability claim. See `docs/evidence/live/2026-07-04-gate-z6-no-submission-drill-closed.md`. |
| Z7: Operator runbook update | **CLOSED (2026-07-04)** | `docs/OPERATOR_GO_NO_GO_RUNBOOK.md` now has a "ZTF DR24 path" section covering the real `--build-review-packets` packet location, the UW ZTF alert archive source-attribution rule, the same review checklist as the WISE path, and an explicit statement that ZTF DR24 archival submission authority is not yet confirmed in writing with MPC (the `stn=XXX` default not failing closed does not constitute that confirmation). Cites the real Gate Z6 drill as the verified basis for the packet/review/export commands. |

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

**Current as of 2026-07-08 (v0.90.60)**: Gates Z1, Z2, Z4, Z5, Z6, and
Z7 are all **CLOSED** with real data -- see the gate rows above. The only
remaining open ZTF DR24 gate is Z3 (paused, see below). No further
coding-agent scoping work remains on Z1/Z2/Z4/Z5/Z6/Z7. The Gate Z3
candidate-pair search below (designation 72966,
apparitions 1-4) **remains intentionally paused** pending explicit
operator direction after being identified as a real doom-loop pattern;
do not resume it or select a different designation without that
direction. The paragraphs immediately below predate this pause and
describe the state at the point it was paused -- retained as accurate
historical context for whenever the operator chooses to resume it, not as
an active next step today.


**Full pre-pause diagnostic trail (state at pause as of 2026-07-04 v0.90.54,
plus every dated update from the original apparition-1 source search
through the four-apparition candidate-pair search)** is archived verbatim
in `docs/HANDOFF_HISTORY.md` under "ZTF_DR24_PRODUCTION_GATES.md historical
narrative — Gate Z3". Not required reading; the Gate Z3 table row above and
the pause notice immediately above this paragraph are sufficient for any
future plan. Do not resume the candidate-pair search without explicit
operator direction, per the pause notice above.
