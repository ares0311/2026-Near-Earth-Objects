# ZTF DR24 Production Gates

Last updated: 2026-07-17
Applies to: ZTF DR24 archival historical replay, the current primary discovery
path defined in `docs/MISSION.md` and `docs/neo_discovery_agent_brief.md`.

This gate register supersedes the WISE/DECam/TESS P1-P5 gates only for the
current primary path. The older gates remain valid historical evidence for the
secondary path, but they do not establish readiness for ZTF DR24 historical
replay.

**Sub-approach pivot notice (2026-07-16, operator decision — see
`docs/ACTIVE_HANDOFF.md`)**: the Z0-Z7 gates immediately below describe the
transient-alert (`prv_candidates`) replay sub-approach. As of 2026-07-16
this sub-approach is itself superseded, within the ZTF DR24 primary path,
by source-native pixel extraction over DR24 motion-designed image
products (difference images, science masks, PSF kernels) — the
"Motion-Product Gates" section further below. Z0-Z7 remain valid
historical evidence (Z1/Z2/Z4/Z5/Z6/Z7 closed, Z3 intentionally paused)
but do not by themselves establish current production readiness; the
Motion-Product Gates section is the currently-active register.

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

## Motion-Product Gates (MP1-MP7)

Currently-active register for the primary ZTF DR24 sub-approach as of
2026-07-16 (source-native pixel extraction over DR24 motion-designed image
products). Mirrors the same Production Definition and gate-naming
convention as the Z-gates above, applied to this new sub-approach. Every
`Skills/*.py` referenced below already exists and is offline-tested; MP1-MP5
are closed with real live evidence; MP6-MP7 are open with an exact,
self-contained closure plan below — no re-derivation needed by whichever
agent (this session or a fresh one, Claude or Codex) picks this up.

| Gate | Status | Closure evidence |
|---|---|---|
| MP1: Bounded manifest + preflight verification | **CLOSED (2026-07-16)** | `Skills/ztf_dr24_bounded_ingest.py --emit-motion-product-manifest --preflight-motion-products` HEAD-verifies all 4 source-native products (difference image, science mask, science PSF catalog, difference PSF) for a bounded single-exposure window without downloading bodies. Real live run: 4/4 products verified, 27,311,040 bytes aggregate. See `docs/evidence/live/2026-07-16-ztf-dr24-motion-product-preflight-first-live-run.md`. |
| MP2: Single-exposure pixel extraction | **CLOSED (2026-07-16)** | `--pixel-extraction-pilot` downloads one difference image and detects candidate sources via sigma-clipped thresholding, converting pixel positions to RA/Dec via the image's own WCS. Real live run: 855 pixels cleared a 5-sigma threshold on the first real exposure tested. See `docs/evidence/live/2026-07-16-ztf-dr24-pixel-extraction-pilot-first-live-run.md`. |
| MP3: Artifact rejection (masking + dedup) | **CLOSED (2026-07-16)** | The detector applies the exposure's real `science_mask` (nonzero pixels excluded) and uses `scipy.ndimage.label` connected-component deduplication so one physical residual becomes one candidate, not several. Real result: 855 raw pixel-hits -> 74 after masking -> 71 connected components on the same exposure. See `docs/evidence/live/2026-07-16-ztf-dr24-pixel-extraction-pilot-masking-dedup.md`. |
| MP4: PSF-shape confidence gate | **CLOSED (2026-07-16)** | Each candidate's cutout is Pearson-correlated against the exposure's real `difference_psf` kernel. A real injected synthetic Gaussian source correlates >0.95 against its own generating shape (proves the method works); real candidates on the tested exposure correlate <=0.18 (proves the method discriminates). See `docs/evidence/live/2026-07-16-ztf-dr24-pixel-extraction-pilot-psf-scoring.md`. |
| MP5: Multi-night motion-consistency linking | **CLOSED (2026-07-17)** | `Skills/convert_pixel_extraction_to_observations.py` + `Skills/run_pixel_extraction_positive_control.py` reuse the real `preprocess()`+`link()` chain across multiple real nights (bypassing `detect()`'s WISE/DECam/TESS-only singleton gate, root-caused not guessed -- see the script's own module docstring). Validated on 2 independently-selected fields (6 real nights total): `min_observations=2` shows the expected crowded-field combinatorial explosion (200 tracklets each field); the real `min_observations=3` default collapses this to 2 and 5 survivors respectively, all of which fail MP4's independent PSF check. See `docs/evidence/live/2026-07-17-ztf-dr24-multi-night-linking-first-test.md` and `docs/evidence/live/2026-07-17-ztf-dr24-selected-field-linking-test.md`. |
| MP6: No-submission package drill | **CLOSED (2026-07-17)** | `Skills/run_pixel_extraction_positive_control.py --build-review-packets` runs every tracklet linked from real pixel-extracted candidates through the real `classify() -> fit_orbit() -> score() -> process_alert(dry_run=True)` chain. Real result on field 1's 2 surviving tracklets: `Skills/adversarial_review.py --offline` reported `SURVIVE=0 BORDERLINE=0 REJECT=2` (predicted before running), with `artifact_posterior` FAIL (`stellar_artifact` ~0.99) independently agreeing with MP4's PSF-correlation finding via a third distinct signal. `Skills/export_ades_report.py` produced valid ADES PSV text with `stn=XXX`; code-inspection confirmed zero network-capable imports. Found and fixed a real interface gap along the way: the original closure plan's `--out` command produced a wrapper dict `adversarial_review.py` cannot parse; a new `--review-packet-out` flag (matching `run_pipeline.py`'s existing convention) writes the plain `ScoredNEO` array both downstream tools expect. See `docs/evidence/live/2026-07-17-ztf-dr24-mp6-no-submission-drill.md`. |
| MP7: Operator runbook update | **CLOSED (2026-07-17)** | `docs/OPERATOR_GO_NO_GO_RUNBOOK.md` now has a "ZTF DR24 motion-product path" section covering the real `--build-review-packets --review-packet-out` packet location, the exact verified `adversarial_review.py`/`export_ades_report.py` commands, the same operator-review checklist as the other paths, and an explicit statement that motion-product-path submission authority is not yet confirmed in writing with MPC. Cites the real MP6 drill above as the verified basis. |

### MP6 closure plan — no-submission package drill (CLOSED — kept for reference)

**Closed 2026-07-17.** See the MP6 gate row above and
`docs/evidence/live/2026-07-17-ztf-dr24-mp6-no-submission-drill.md` for the
real drill result. The plan text below is left in place, corrected, as a
reference for how the drill was actually run — including the real
`--review-packet-out` gap found and fixed along the way (Step 3's original
text used only `--out`, which does not produce a format
`adversarial_review.py`/`export_ades_report.py` can consume; use
`--review-packet-out` instead, as corrected below).

**Objective**: prove that a real tracklet produced by this pipeline can be
carried through `classify() -> fit_orbit() -> score() -> process_alert
(dry_run=True)` into a real `ScoredNEO` review packet, then through
`Skills/adversarial_review.py` and `Skills/export_ades_report.py`, with
zero external submission and zero network calls at the export step --
exactly Gate Z6's closure requirement, for this new pipeline.

**Step 1 — add `--build-review-packets` to `Skills/run_pixel_extraction_
positive_control.py`.** `Skills/run_archive_positive_control.py` already
implements this exact feature (its `build_review_packets` parameter,
`--build-review-packets` CLI flag, lines building `features, posterior =
classify(trk)`, `orbital = fit_orbit(trk)`, `scored = score(...)`,
`process_alert(scored, dry_run=True)` for every linked tracklet). Mirror it
verbatim into `run_pixel_extraction_positive_control.py`'s
`run_positive_control()` and `main()` -- same parameter name, same CLI flag
name, same behavior. Add matching offline tests (empty tracklet list ->
`review_packets` key absent or empty; a real synthetic tracklet fixture ->
non-empty `review_packets` with valid `ScoredNEO` dicts), following
`tests/test_run_archive_positive_control.py`'s existing coverage pattern
for the equivalent feature if such tests exist there, else write new ones
matching this project's standing test conventions (independent-oracle,
offline, no network).

**Step 2 — run it live on already-acquired real data.** No new download
needed; checkpoints already exist from MP5's closure:

```bash
caffeinate -i uv run --python 3.14 python Skills/run_pixel_extraction_positive_control.py \
    --nights 20180802 20180806 20180809 \
    --checkpoint-dir Logs/pipeline_runs/ztf_dr24_pixel_extraction_positive_control \
    --min-observations 3 \
    --build-review-packets \
    --review-packet-out Logs/pipeline_runs/ztf_dr24_pixel_extraction_positive_control/review_packets.json
```

(Corrected 2026-07-17: use `--review-packet-out`, not `--out`, to get the
plain `ScoredNEO` array `adversarial_review.py`/`export_ades_report.py`
expect -- see the real gap found in the MP6 evidence file cited above.)

Expect 2 real `ScoredNEO` review packets (matching MP5's 2 surviving
tracklets on this field). Repeat for the second field's checkpoint dir
(`Logs/pipeline_runs/ztf_dr24_pixel_extraction_positive_control_field2`,
nights `20180327 20180330 20180409`) for 5 more packets, if a broader
sample is wanted -- not required to close the gate; one field's packets
are sufficient to prove the mechanics.

**Step 3 — pipe the packets through the existing review/export tools:**

```bash
PYTHONPATH=src uv run --python 3.14 python Skills/adversarial_review.py \
    Logs/pipeline_runs/ztf_dr24_pixel_extraction_positive_control/review_packets.json \
    --offline --json

PYTHONPATH=src uv run --python 3.14 python Skills/export_ades_report.py \
    Logs/pipeline_runs/ztf_dr24_pixel_extraction_positive_control/review_packets.json
```

**Expected, predicted result** (state this before running, per this
project's "predict before you run" discipline): `adversarial_review.py`
should report `SURVIVE=0 BORDERLINE=0 REJECT=2` (or however many packets
were produced) -- REJECT is the *correct* expected outcome here, not a
failure, because MP4/MP5 already established these specific tracklets fail
independent PSF-shape validation. `export_ades_report.py` should produce
valid ADES PSV text with `stn=XXX` (the documented placeholder) and make
zero network calls (verify by code inspection, matching Gate Z6's
verification method, or by running with network access removed/monitored).
**If `adversarial_review.py` instead reports any SURVIVE or BORDERLINE**,
that contradicts MP4/MP5's findings and must be re-diagnosed before
declaring the gate closed -- do not paper over a result that disagrees
with already-established evidence.

**Closing the gate**: once Step 3 runs for real with the predicted result,
update this table's MP6 row to CLOSED with a dated evidence file under
`docs/evidence/live/`, following the exact format of every other dated
evidence file in this project (command, real output, honest interpretation).

### MP7 closure plan — operator runbook update

Once MP6 is closed, add a "ZTF DR24 motion-product path" section to
`docs/OPERATOR_GO_NO_GO_RUNBOOK.md`, mirroring its existing "ZTF DR24 path"
section (added when Z7 closed): review-packet location
(`Logs/pipeline_runs/ztf_dr24_pixel_extraction_positive_control/
review_packets.json`), the exact `adversarial_review.py`/
`export_ades_report.py` commands (verified against MP6's real drill), the
same operator-review checklist as the other paths, and an explicit
statement that motion-product-path submission authority is not yet
confirmed in writing with MPC (same caveat as the alert-replay path's Z7
closure). This is a small, mechanical documentation step once MP6's real
evidence exists to cite.

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

**Current as of 2026-07-17**: all seven Motion-Product Gates (MP1-MP7) are
now **CLOSED** with real data. MP6's no-submission drill produced the
predicted `REJECT=2` result (a third independent signal agreeing with
MP4/MP5 that no real point source survives on the tested field), and MP7's
operator runbook update is complete. No candidate has survived adversarial
review on either tested field. Per the Production Definition above, this
is not itself a readiness gap -- production readiness does not require a
confirmed discovery. The next roadmap move is again an operator decision
(same three options listed under `CLAUDE.md`'s "Immediate Next Steps": try
another field via `Skills/select_survey_fields.py`, resume the paused Z3
alert-replay identity search, or pause pending a different direction). Do
not select a new field or start a new bulk transfer without that
direction.

**Z0-Z7 below are the superseded alert-replay sub-approach's gate history**
(see the pivot notice near the top of this file). Gates Z1, Z2, Z4, Z5, Z6,
and Z7 are all **CLOSED** with real data -- see the gate rows above. Z3 is
the only ever-open gate in that sub-approach and **remains intentionally
paused** pending explicit operator direction after being identified as a
real doom-loop pattern; do not resume it or select a different designation
without that direction. This entire Z0-Z7 track is historical evidence, not
an active next step -- the current active discovery work is the
Motion-Product Gates track above.


**Full pre-pause diagnostic trail (state at pause as of 2026-07-04 v0.90.54,
plus every dated update from the original apparition-1 source search
through the four-apparition candidate-pair search)** is archived verbatim
in `docs/HANDOFF_HISTORY.md` under "ZTF_DR24_PRODUCTION_GATES.md historical
narrative — Gate Z3". Not required reading; the Gate Z3 table row above and
the pause notice immediately above this paragraph are sufficient for any
future plan. Do not resume the candidate-pair search without explicit
operator direction, per the pause notice above.
