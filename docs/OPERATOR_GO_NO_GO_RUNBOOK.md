# Operator Go/No-Go Runbook — What To Do When A Candidate Appears

**Established**: 2026-07-02
**Status**: Closes `docs/PRODUCTION_READINESS.md` Gate P5
**Audience**: Jerome W. Lindsey III (operator). One page. If you need more
detail than this, the full references are linked at the bottom.

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

## Step 5 — MPC submission authority check (Gate P4 — human-gated)

**No code can do this step. It is yours alone.**

Before any `export_ades_report.py --obs-code C51
--mpc-confirmed-wise-c51-submission` run, you must have **written MPC
confirmation** that this independent archival pipeline may submit
WISE/NEOWISE remeasurements under station code C51. See
`docs/MPC_SUBMISSION_POLICY.md §TODO for Future Agents — Archival WISE
Submission Authority` and `docs/mpc_wise_neowise_archival_astrometry_submission.md`
for the current state of that correspondence. Until you have that
confirmation on record, `--mpc-confirmed-wise-c51-submission` must not be
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
