# Operator Go/No-Go Runbook — What To Do When A Candidate Appears

**Established**: 2026-07-02
**Updated**: 2026-07-04 — added the ZTF DR24 path (see below); the original
steps below remain valid for the secondary WISE/DECam/TESS path.
**Updated**: 2026-07-17 — added the ZTF DR24 motion-product path (see
below), the current primary sub-approach as of the 2026-07-16 pivot; the
2026-07-04 ZTF DR24 (alert-replay) section remains valid for that
now-superseded sub-approach.
**Status**: Closes `docs/PRODUCTION_READINESS.md` Gate P5 (WISE/DECam/TESS
path), `docs/ZTF_DR24_PRODUCTION_GATES.md` Gate Z7 (ZTF DR24 alert-replay
path), and Gate MP7 (ZTF DR24 motion-product path).
**Audience**: Jerome W. Lindsey III (operator). One page. If you need more
detail than this, the full references are linked at the bottom.

---

## ZTF DR24 path (current primary discovery path)

This section covers the primary path per `docs/MISSION.md` and
`docs/neo_discovery_agent_brief.md`: bounded ZTF DR24 archival historical
replay, not the secondary WISE/DECam/TESS path documented in Steps 1-6
below (which still applies verbatim if you ever run `--surveys WISE`,
`DECam`, or `TESS`).

**Source attribution rule**: every ZTF DR24 observation in a review packet
originates from the University of Washington's public ZTF alert archive
(`https://ztf.uw.edu/alerts/public/`), a real, unauthenticated,
schema-verified per-detection source ingested by
`Skills/ztf_alert_archive_ingest.py` — see
`docs/evidence/phase0/2026-07-02-gate-z3-uw-alert-archive-candidate.md`.
Do not treat a ZTF DR24 packet as coming from the live ZTF alert stream or
from ZAPS; live-stream ZTF discovery remains prohibited (see CLAUDE.md
DECISION-001).

**Step 1 (ZTF DR24) — Build review packets**:

```bash
git pull origin main
export PYTHONPATH=src
uv run --python 3.14 python Skills/run_archive_positive_control.py \
    --nights <night1> <night2> [...] --min-observations 2 \
    --build-review-packets \
    --out Logs/pipeline_runs/run_archive_positive_control/report.json
```

Real `ScoredNEO` review packets appear under the `review_packets` key of the
output JSON, one per linked tracklet. If `n_tracklets_linked` is 0, there is
nothing to review — stop here, same as the WISE path's Step 1.

**Step 2 (ZTF DR24) — Adversarial review and export**: extract the
`review_packets` array into its own file, then run the same Step 2 and
Step 4 commands from the WISE path below against it:

```bash
uv run --python 3.14 python Skills/adversarial_review.py \
    <review_packets_file>.json --offline --json
uv run --python 3.14 python Skills/export_ades_report.py \
    <review_packets_file>.json --out Logs/reports/<slug>_ades.psv
```

This exact mechanism was drilled end-to-end on real archived data (Gate
Z6, 2026-07-04): 88 real review packets from real archived ZTF tracklets,
correctly `REJECT`ed by adversarial review (they were combinatorial
cross-night pairings of unrelated sources, not a real single-object
candidate — see
`docs/evidence/live/2026-07-04-gate-z6-no-submission-drill-closed.md`),
then exported as valid dry-run ADES PSV text with zero network calls.

**Step 3 (ZTF DR24) — Your review**: same checklist as Step 3 below,
substituting the ZTF DR24 source-attribution rule above for the WISE/DECam/
TESS one.

**Step 5 (ZTF DR24) — MPC submission authority check**: `stn=XXX` (the
general MPC-documented placeholder for a new observer's first submission,
`docs/MPC_SUBMISSION_POLICY.md` §Submission Process) is the default and
`export_ades_report.py` does not fail closed on ZTF-sourced records the way
it does for WISE/NEOWISE `stn=C51`. **This does not mean ZTF DR24 archival
submission authority has been separately confirmed in writing with MPC** —
no such confirmation is currently documented anywhere in this project. Per
the same standing rule as the WISE path, do not submit externally, and do
not treat the absence of a code-level fail-closed check as authorization to
do so, until the operator has obtained and recorded written MPC guidance
for this specific archival-replay use case.

Steps 6 and "Forbidden communications" below apply identically to both
paths.

---

## ZTF DR24 motion-product path (current primary sub-approach, as of 2026-07-16)

This section covers the sub-approach that superseded the alert-replay
section above on 2026-07-16 (see `docs/ACTIVE_HANDOFF.md` and
`docs/ZTF_DR24_PRODUCTION_GATES.md`'s pivot notice): source-native pixel
extraction directly over DR24 motion-designed image products (difference
images, science masks, PSF kernels) rather than the `prv_candidates`
alert-broker field. The alert-replay section above remains valid if you
ever run that older path again; this section is what to use for the
current default.

**Source attribution rule**: every motion-product observation in a review
packet originates from a real DR24 difference-image exposure and its
paired science mask / PSF products, downloaded and pixel-extracted by
`Skills/ztf_dr24_bounded_ingest.py` and converted to `Observation` records
by `Skills/convert_pixel_extraction_to_observations.py` — see the MP1-MP5
evidence files cited in `docs/ZTF_DR24_PRODUCTION_GATES.md`. Do not treat a
motion-product packet as coming from the live ZTF alert stream, ZAPS, or
the `prv_candidates` field; live-stream ZTF discovery remains prohibited
(CLAUDE.md DECISION-001).

**Step 1 (motion-product) — Build review packets**:

```bash
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/run_pixel_extraction_positive_control.py \
    --nights <night1> <night2> [...] \
    --checkpoint-dir <checkpoint_dir> \
    --min-observations 3 \
    --build-review-packets \
    --review-packet-out <checkpoint_dir>/review_packets.json
```

Real `ScoredNEO` review packets are written directly to
`<checkpoint_dir>/review_packets.json` as a plain JSON array — this is the
`--review-packet-out` flag, not `--out` (which instead writes the full
diagnostic report as a wrapper dict that `adversarial_review.py` cannot
parse; this exact interface gap was found and fixed closing Gate MP6, see
`docs/evidence/live/2026-07-17-ztf-dr24-mp6-no-submission-drill.md`). If
`n_tracklets_linked` in the console output is 0, there is nothing to
review — stop here.

**Step 2 (motion-product) — Adversarial review and export**: run the same
Step 2 and Step 4 commands from the ZTF DR24 alert-replay path above,
against `<checkpoint_dir>/review_packets.json`:

```bash
uv run --python 3.14 python Skills/adversarial_review.py \
    <checkpoint_dir>/review_packets.json --offline --json
uv run --python 3.14 python Skills/export_ades_report.py \
    <checkpoint_dir>/review_packets.json --out Logs/reports/<slug>_ades.psv
```

This exact mechanism was drilled end-to-end on real data (Gate MP6,
2026-07-17): 2 real review packets from a real pixel-extracted, multi-night
motion-consistency-linked tracklet, correctly `REJECT`ed by adversarial
review (independent PSF-shape correlation and classifier posterior both
agree these are not real point sources — see the MP6 evidence file above),
then exported as valid dry-run ADES PSV text with zero network calls
(verified by code inspection).

**Step 3 (motion-product) — Your review**: same checklist as Step 3 below,
substituting the motion-product source-attribution rule above.

**Step 5 (motion-product) — MPC submission authority check**: same as the
alert-replay path's Step 5 above — `stn=XXX` not failing closed does not
constitute written MPC confirmation that this pipeline may submit
motion-product-derived astrometry. No such confirmation is currently
documented anywhere in this project for this sub-approach. Do not submit
externally until the operator has obtained and recorded it.

Steps 6 and "Forbidden communications" below apply identically to all three
paths.

---

## The one thing to remember

**A `SURVIVE` or `BORDERLINE` verdict means "this candidate may be reviewed
for MPC submission." It does not mean "confirmed NEO," and it does not mean
any statement about impact risk can be made.** Every object stays a
*candidate* until MPC assigns a provisional designation via NEOCP.

---

## Step 1 — Find the review packet

Every `Skills/run_pipeline.py` run that finds tracklets writes a review
packet automatically when called with `--review-packet-out`:

```
Logs/reports/<slug>_review_packets.json
```

The console output tells you how many full `ScoredNEO` packets were written.
**If it says 0 packets, stop — there is nothing to review.** Do not run
adversarial review on an empty or non-`ScoredNEO` file; it will fail closed
with `ERROR: no valid ScoredNEO entries found in input`, which is correct
behavior, not a bug.

## Step 2 — Run adversarial review

```bash
git pull origin main
export PYTHONPATH=src
uv run --python 3.14 python Skills/adversarial_review.py \
    Logs/reports/<slug>_review_packets.json --offline --json
```

Exit code tells you the outcome at a glance: `0` = all `SURVIVE`, `1` = at
least one `REJECT`, `2` = `BORDERLINE` present but no `REJECT`.

Verdict meanings (from `Skills/adversarial_review.py`):
- **REJECT** — at least one disqualifying flaw found. Stop here for that
  candidate. Do not proceed to Step 3 for it.
- **BORDERLINE** — no disqualifying flaw, but ≥2 warnings. Needs your manual
  scrutiny before proceeding (Step 3).
- **SURVIVE** — clean, or at most 1 minor warning. Candidate may advance to
  your review (Step 3).

## Step 3 — Your review (only for SURVIVE/BORDERLINE candidates)

Read the full packet JSON yourself. Checklist:

- [ ] Does the tracklet's motion, arc, and night coverage look like a real
      solar-system object to you, independent of the automated verdict?
- [ ] For a `BORDERLINE` verdict, read every listed warning and form your own
      judgment on each one — the tool flags concerns, it does not resolve them.
- [ ] Confirm `hazard.hazard_flag`, `hazard.alert_pathway`, and
      `hazard.neo_class` all still say "candidate," not a confirmed
      classification. If any pipeline output ever says "confirmed NEO,"
      that is a guardrail violation — stop and report it, do not proceed.
- [ ] Check `docs/PRODUCTION_READINESS.md` Gate P2
      (`docs/SURVEY_NATIVE_CONFIDENCE_POLICY.md`) for the discovery source
      involved — WISE is live-verified; DECam/TESS are not, and TESS
      candidates are not evidence of a real detection at all (see that doc).

If you approve: proceed to Step 4. If you don't: stop, note why in a
`docs/evidence/` file, and do not export.

## Step 4 — Export an MPC-compatible report (still local, still no submission)

```bash
git pull origin main
export PYTHONPATH=src
uv run --python 3.14 python Skills/export_ades_report.py \
    Logs/reports/<slug>_review_packets.json --out Logs/reports/<slug>_ades.psv
```

This only formats a local text file. It does not send anything anywhere.

**If the candidate uses WISE/NEOWISE observations, this will fail closed by
default** (see `docs/evidence/prod-loop/2026-07-02-gate-p3-no-submission-drill.md`
for a verified drill of exactly this behavior). That is correct — do not work
around it. It stays fail-closed until Step 5 is done.

## Step 5 — MPC submission authority check (only relevant if you reach this step)

**This step is dormant until a real candidate reaches it. There is nothing
to do here, and no reason to contact MPC, until Step 3 has actually produced
a candidate you intend to submit.** Do not treat this as a standing task.

If and when that day comes: before any `export_ades_report.py --obs-code C51
--mpc-confirmed-wise-c51-submission` run, you need **written MPC
confirmation** that this independent archival pipeline may submit
WISE/NEOWISE remeasurements under station code C51 — see
`docs/MPC_SUBMISSION_POLICY.md §TODO for Future Agents — Archival WISE
Submission Authority` and `docs/mpc_wise_neowise_archival_astrometry_submission.md`
for what is and isn't already documented from MPC's own sources. Until that
confirmation is in hand, `--mpc-confirmed-wise-c51-submission` must not be
set, and no coding agent should ever suggest setting it for you.

For non-WISE sources (once DECam/TESS are live-verified per Gate P2), the
equivalent station-code/authority question must be resolved the same way
before submission — check with MPC in writing first.

## Step 6 — Submit, then let MPC/NEOCP/Scout do their job

Once you submit, this pipeline's job is done for that candidate:

- MPC computes a digest2 score automatically. `digest2 > 65` → object posted
  to NEOCP automatically. No pipeline action required.
- NEOCP is monitored 24/7 by professional/amateur observatories worldwide —
  this **is** the expert review step. No in-house expert is required or
  expected.
- Scout (CNEOS/JPL) assesses impact probability automatically if warranted.

## Forbidden communications (always, no exceptions)

- Do **not** contact NASA PDCO directly. Scout does this automatically.
- Do **not** publicly state or imply any impact probability, for any object,
  ever. Defer to Scout/Sentry/CNEOS.
- Do **not** publicly announce a candidate before MPC assigns a provisional
  designation.
- Do **not** output or say "confirmed NEO" for anything this pipeline found
  on its own. Everything is a candidate until MPEC publication.
- Do **not** lower the `ready_for_submission()` gates
  (`src/alert.py`: MOID ≤ 0.05 AU, orbit quality ≥ 2, `real_bogus_score` ≥
  0.90, not already a known object) to force a candidate through.

---

## References (only if you need more than this page)

- `docs/MPC_SUBMISSION_POLICY.md` — full submission policy and background.
- `docs/SURVEY_NATIVE_CONFIDENCE_POLICY.md` — per-source confidence gates
  (Gate P2).
- `docs/evidence/prod-loop/2026-07-02-gate-p3-no-submission-drill.md` — the
  verified drill this runbook is based on (Gate P3).
- `docs/PRODUCTION_READINESS.md` — full gap register, all gates P1-P5.
- `docs/ALERT_PROTOCOL.md` — technical reference for the alert-pathway
  decision tree.
- `docs/ZTF_DR24_PRODUCTION_GATES.md` — full gap register for the current
  primary ZTF DR24 path, all gates Z0-Z7 and MP1-MP7.
- `docs/evidence/live/2026-07-04-gate-z6-no-submission-drill-closed.md` —
  the verified drill the ZTF DR24 alert-replay section above is based on
  (Gate Z6).
- `docs/evidence/live/2026-07-17-ztf-dr24-mp6-no-submission-drill.md` — the
  verified drill the ZTF DR24 motion-product section above is based on
  (Gate MP6).
