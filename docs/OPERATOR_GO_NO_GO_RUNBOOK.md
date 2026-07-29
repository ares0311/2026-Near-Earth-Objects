# Operator Go/No-Go Runbook — What To Do When A Candidate Appears

**Established**: 2026-07-02
**Updated**: 2026-07-04 — added the ZTF DR24 path (see below); the original
steps below remain valid for the secondary WISE/DECam/TESS path.
**Updated**: 2026-07-17 — added the ZTF DR24 motion-product path (see
below), the current primary sub-approach as of the 2026-07-16 pivot; the
2026-07-04 ZTF DR24 (alert-replay) section remains valid for that
now-superseded sub-approach.
**Updated**: 2026-07-29 — recorded the HP-15 through HP-20 adversarial
re-audit, remediation, and clean local verification; hosted CI and clean
post-merge verification remain the final claim boundary.
**Status**: Closes `docs/PRODUCTION_READINESS.md` Gate P5 (WISE/DECam/TESS
path), `docs/ZTF_DR24_PRODUCTION_GATES.md` Gate Z7 (ZTF DR24 alert-replay
path), and Gate MP7 (ZTF DR24 motion-product path).
**Audience**: Jerome W. Lindsey III (operator). One page. If you need more
detail than this, the full references are linked at the bottom.

---

## Hunter PROD closure remediation (2026-07-29 re-audit)

This is the durable execution ledger for the adversarial re-audit of the
canonical Hunter workflow. Current business requirements and
`docs/HUNTER_PROD_DIRECTIVE.md` supersede the older Phase 3 closure claim where
real behavior contradicts it. Do not restore that claim until every item below
has passing behavioral and live-workflow evidence.

| ID | Finding to remediate | Required acceptance evidence | Status |
|---|---|---|---|
| HP-01 | New-search execution did not update the governing target history, so an executed target could be selected as `new` again. | Durable, stable-ID target history is written for pending and executed targets; a second new request excludes every previously selected target. | VERIFIED |
| HP-02 | Discovery stopped at the default fixed `--max-pool 200`, even when the accessible planning universe was not exhausted. | The normal path expands adaptively until top-N is supported or the planning universe is exhausted; an explicit operator limit fails loudly when it prevents sufficiency. | VERIFIED |
| HP-03 | `run-new-search` returned success even when the durable run was `partial` or `failed`. | CLI exit status is non-zero for every mandatory incomplete/failed outcome and zero only for a completed exact manifest. | VERIFIED |
| HP-04 | A crash after a target checkpoint but before ledger/follow-up ingestion could resume as `completed` while silently losing results. | Side effects are idempotent and precede the terminal target checkpoint; an injected crash/resume test proves no candidate or follow-up loss or duplication. | VERIFIED |
| HP-05 | Follow-up selection was limited to manually seeded registry/legacy CSV cases and could repeat the same nights instead of selecting additional work from real prior search history. | A completed new run becomes valid follow-up evidence; follow-up ranking uses remaining unsearched coverage and execution acquires different nights. | VERIFIED |
| HP-06 | The canonical executor invoked adversarial review offline without time-aware known-object evidence, forcing the known-object challenge to fail regardless of the candidate. | The production path obtains and provenance-stamps time-aware known-object evidence (or fails visibly); no unconditional missing-evidence verdict remains. | VERIFIED |
| HP-07 | Coverage/model/scorer/result provenance was incomplete or synthetic in durable manifests and ledgers. | Durable records carry source, source version/as-of, retrieval time, transformations, versions, exact commit/worktree state, and one of `valid`, `stale-but-usable`, `refresh-required`, `invalid`, or `unknown`; selected inputs are current-valid or visibly refreshed. | VERIFIED |
| HP-08 | README/operator commands presented lower-level scripts as product paths and there were no installed canonical Hunter entry points. | Installed `Create-New-Search`, `Run-New-Search`, and `Show-Follow-Ups` commands drive the one durable pipeline; lower-level tools are explicitly diagnostic and contract-tested as non-production bypasses. | VERIFIED |
| HP-09 | Prior live evidence did not execute the exact selected new manifest and used a seeded follow-up stand-in. | A real new-target request executes its exact durable manifest; a subsequent real history-derived follow-up executes additional exact nights; adaptive expansion, provenance, results, and restart state are preserved. | VERIFIED |

Execution followed the recorded order: HP-01/02, HP-03/04/05, HP-06/07/08,
independent negative controls, canonical/adversarial verification, then the
real HP-09 new/follow-up sequence. Exact commands, IDs, nights, provenance,
results, and limitations are in
`docs/evidence/live/2026-07-25-hunter-prod-adversarial-closure.md`.

The HP-01 through HP-09 implementation remains valid hardening, but the PROD
claim made after that sequence is revoked. A limitation review found that
three facts previously disclosed as non-blocking actually prevent the stronger
business claim that Hunter returns the best *executable* next searches and
preserves them safely. The later HP-13 reopening added the missing persistent
product terminal. Do not claim Hunter PROD unless HP-10 through HP-13 are
VERIFIED against clean current `main`.

| ID | Blocking finding | Required acceptance evidence | Status |
|---|---|---|---|
| HP-10 | New ranking policy v3 is explicitly not known to be optimal, and follow-up history uses hand-set bonuses without outcome validation. Deterministic/explainable ranking alone does not demonstrate “best available N.” | Define separate, versioned new and follow-up value contracts; compare each policy with independent real or known-ground-truth outcomes and simple baselines; require the promoted policy to be the best supported available policy without imposing an absolute-quality threshold. | **VERIFIED** — v4 geometry ordering beats the former policy and the regularized alternative on current real outcomes; the small 2024 Aten holdout also orders correctly. Follow-up uses a separate tiered contract, dedicated follow-up value, and excludes success/null history without an open registry item. |
| HP-11 | Selection validates a 2° regional coverage box while execution requires a resolvable 0.01° exact target. A predictably unexecutable target can therefore consume a top-N slot. | Before durable manifest creation, validate at least three exact-position nights plus required product availability for each selected target; reject infeasible candidates, continue adaptive expansion, and prove a lower-ranked feasible replacement outside the initial frontier is selected and executed. | **VERIFIED** — exact 0.01° inventory/product preflight is a manifest gate; ranked replacement and adaptive re-expansion have independent controls; the real new run executed three exact nights, while the real follow-up retry was correctly rejected after exact product 404s. |
| HP-12 | The canonical suite emits unclosed-SQLite `ResourceWarning`s and an obsolete XGBoost-parameter warning. Passing tests do not establish durable restart hygiene while those warnings remain unattributed. | Trace warnings to their allocation sites, close production resources and remove obsolete configuration without broad suppression; production-relevant tests must pass with `ResourceWarning` promoted to an error, and the canonical suite must finish warning-free or explicitly prove any remaining warning is outside every Hunter production path. | **VERIFIED** — SQLite lifecycle defects in tests and the Tier 3 runner are closed, the obsolete XGBoost option is removed, warning-as-error focused tests pass, and the canonical 2,279-test run completed with no warning summary. |
| HP-13 | The canonical lifecycle existed only as three one-shot commands; the required persistent `NEOHunter` terminal, slash-command discovery/history, domain-specific visual progress, and scriptable slash interface were absent. | Install `NEOHunter`; keep it active until `/Exit`; expose `/New-Search`, `/Follow-Up-Search`, `/Run-Search`, `/Show-Follow-Ups`, `/Help`, and `/Exit` through `/` discovery and Tab completion; delegate every scientific action to the one canonical pipeline; preserve exit failures in script mode; and disable color/animation cleanly for redirection, accessibility settings, and automation. | **VERIFIED** — installed `NEOHunter` is a thin canonical adapter with persisted history, semantic color, real-transition orbital-sweep events, redirect/accessibility degradation, and repeatable `--command` automation. A macOS PTY probe verified bare-`/` discovery, libedit Tab completion, persistence until `/Exit`, and clean exit. Script mode preserved a real already-executed manifest failure as exit 1. Canonical verification passed 2,307 tests at 100% coverage; all 81 adversarial controls passed. |
| HP-14 | Exact multi-target execution was serial and exposed no worker control or concurrency acceptance test, despite independent target checkpoints and the directive's configurable-parallelism requirement. | Execute independent targets concurrently within the documented IRSA pixel-product safety limit; keep every durable SQLite/ledger/follow-up/history write serialized in manifest rank order; provenance-stamp the worker/scheduler contract; require the same contract on resume; and independently prove actual overlap plus deterministic commit order. | **VERIFIED** — `Run-New-Search --workers 1..3` defaults to the documented three-stream ceiling. Target work uses isolated checkpoint roots in a bounded thread pool; durable effects remain main-thread, manifest-order operations. Worker configuration is stored in run and target provenance, legacy resumable runs are upgraded durably, and conflicting resume settings fail loudly. The overlap control reached three simultaneous targets and independently asserted manifest-order history. See `docs/evidence/live/2026-07-27-hunter-prod-concurrency-closure.md`. |
| HP-15 | `Create-New-Search` accepted an exhausted `0/N` result as a successful pending manifest, and `Run-New-Search` then classified that empty manifest as `completed` because zero targets also meant zero failures. A reproduced `requested_n=1`, `actual_n_selected=0` run exited zero with `status=completed targets=0 failed=0`. | No durable pending manifest may be created unless `actual_n_selected == requested_n > 0` and `sufficiency_met=true`; execution must independently reject malformed, empty, or insufficient legacy manifests before creating or mutating a run; both installed command boundaries must return non-zero; add negative controls for natural-universe exhaustion as well as explicit operator caps. | **VERIFIED LOCALLY** — creation and execution enforce the exact invariant independently; natural shortfall is nonzero and leaves no pending manifest; malformed legacy rows are rejected before run creation. |
| HP-16 | The release wheel contained only distribution metadata. Its console scripts pointed at `hunter_commands`, but no application module was present; an isolated Python 3.14 installation failed immediately with `ModuleNotFoundError: No module named 'hunter_commands'`. Editable-checkout tests masked the defect by importing repository files directly. | Package every runtime module and immutable Hunter resource required by the canonical workflow; keep mutable state outside installed package files; install the built wheel into an isolated environment with no checkout on `sys.path`; prove `NEO-Hunter --command /Help` and every one-shot `--help` entry point succeeds; add the same build/install/smoke boundary to release CI. | **VERIFIED LOCALLY** — v0.91.1 packages runtime code and immutable resources. An isolated artifact launches both terminal spellings, all one-shot commands, and a state operation without importing the checkout. |
| HP-17 | The pre-selection universe was not a distinct durable candidate catalog. `candidate_ledger` stores post-detection packets, while the planning universe was regenerated from a coarse 579-field grid; the largest measured mode exposed only 548 ranked fields, not the directive's 10,000-plus design scale. | Add a versioned durable target-catalog entity distinct from detected-candidate records; use stable field identities and preserve survey, canonical identity, target kind, coordinates, resource estimates, scientific metrics, and source provenance; evaluate at least 10,000 viable planning candidates when the sky/mode supports them; prove a request for 100 ranks from that larger universe without changing exact-execution safety gates. | **VERIFIED LOCALLY** — schema v3 adds version-preserving `target_catalog`; controlled `all` mode materializes 30,096 viable rows and ranks 100 from them; selected exact targets are members of the governing snapshot. |
| HP-18 | Operator manifest and follow-up tables omitted mandatory decision fields. Manifests lacked explicit mode, prior-search count/provenance, resource estimates, and several domain metrics; `/Show-Follow-Ups` stored but did not display evidence reference, originating run, prior history, required data, or estimated resources. The `N>100` export decision was based on actual rows rather than requested `N`. | Persist and display/export the complete operator contract with honest not-applicable values where necessary; base grid-versus-CSV behavior on requested `N`; add schema/behavior tests for both small tables and large or exhausted requests; make follow-up rows independently actionable from displayed/exported information. | **VERIFIED LOCALLY** — durable small tables and large CSVs expose the required manifest fields; follow-up output is independently actionable; requested N governs display behavior. |
| HP-19 | Hunter emitted human-readable `print` progress but had no structured operational event log, and installed-path configuration assumed repository-relative mutable state. | Add explicit, documented resource/state/config resolution with an operator override; write append-only structured JSONL events for create, run, per-target outcome, follow-up display, validation failure, and terminal status; keep secrets out; prove installed operation writes only to the configured state root and that log failures fail visibly. | **VERIFIED LOCALLY** — immutable resources and mutable `NEOHUNTER_HOME` state are separate; JSONL events cover required transitions; log failures surface; isolated installed operation writes only its configured SQLite/event state. |
| HP-20 | The canonical and adversarial suites passed despite HP-15 and HP-16, and the local REL-05 record was stale. Release CI built an artifact but never installed or launched it. | Add independent negative controls for empty/short manifests, isolated artifact contents and launch, catalog scale, complete operator fields, structured events, and installed state isolation; make release CI run the isolated artifact smoke test; rerun canonical, adversarial, artifact, hosted-CI, and clean-commit freshness checks before restoring any Hunter PROD claim. Keep broader ZTF DR24 scientific-capability gate M8 explicitly separate and open until its own evidence closes it. | **LOCAL AND HOSTED VERIFIED; POST-MERGE PENDING** — clean commit `7b8bb59e` passed 2,335 canonical tests at 100% coverage, 85 adversarial controls, isolated artifact validation, and REL-05 freshness. PR CI run `30427815869`, including `hunter-distribution`, and E2E run `30427816053` passed. Clean post-merge verification remains required. |

Execution order: formalize HP-10’s value contracts first so selection has a
valid objective; integrate HP-11’s exact-position feasibility into that
selector; close HP-12 resource lifecycle defects; add the HP-13 persistent
terminal without duplicating the canonical pipeline; close HP-14 with bounded
target concurrency and serialized deterministic persistence. The 2026-07-27
re-audit then reopens the claim through HP-15 to HP-20. Remediate in dependency
order: fail-closed lifecycle semantics; distributable runtime/configuration;
durable 10,000-plus planning catalog; complete operator tables; structured
events; independent artifact and acceptance controls. Only then run canonical
and adversarial verification on a clean commit, merge only with passing CI, and
repeat verification on the clean merge commit.

External MPC/NEOCP submission, impact claims, the absence of a discovery, and
a scientifically valid null result are not Hunter PROD limitations. They are,
respectively, a required human safety boundary, an authority boundary, a
non-guaranteed scientific outcome, and a valid search result. Cross-project
history sharing is `not-applicable` for NEO field/candidate identities unless
future evidence establishes a governing identity shared with the stellar
Hunter projects.

Closure evidence:
`docs/evidence/live/2026-07-25-hunter-prod-final-remediation.md`.
Implementation commit `3437e4799c4988ed36e019ea28f4756f5c550c92`
passed all six canonical reliability stages (2,279 tests, 100% `src/`
coverage) and all 53 then-current adversarial negative controls. Clean HP-13
implementation commit `9f7e5cadf046970ad36d24a5baee18300b5d796c`
passed all six canonical stages (2,307 tests, 100% `src/` coverage), all 81
expanded adversarial controls, and the freshness check. The final
documentation commit repeats both workflows and the freshness check before
merge.

HP-15 through HP-20 local closure evidence:
`docs/evidence/live/2026-07-29-hunter-prod-artifact-and-state-closure.md`.

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
