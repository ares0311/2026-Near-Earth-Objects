# MISSION.md — Authoritative Project Goal and Pipeline Strategy

**Read this before reading anything else. This file and
`docs/neo_discovery_agent_brief.md` are jointly authoritative.**

Last updated: 2026-07-02 (operator decision: brief supersedes the prior
WISE/DECam/TESS-primary strategy — see §Operator Decision below)

---

## The Goal

Find genuinely NEW Near-Earth Objects (NEOs) in astronomical data that professional
NEO pipelines have not yet processed. Candidates that survive automated and operator
review are submitted to the Minor Planet Center (MPC). If confirmed, this supports
a publishable scientific paper.

We do NOT claim discovery. We claim to have found **candidates for expert review**.

## Operator Decision (2026-07-02): The Brief Is Now the Primary Pipeline

Jerome W. Lindsey III has decided that `docs/neo_discovery_agent_brief.md`
**supersedes** the WISE/DECam/TESS-primary strategy this file previously
described. This is a deliberate reversal of the 2026-07-01 reconciliation
(commit `a1934808`), which had kept WISE/DECam/TESS as primary and treated
the brief as reference-only. That reconciliation is now void.

**What this means concretely:**

- **ZTF DR24 historical replay is now the primary discovery path**, not a
  training-only or benchmark-only reference. The brief's own precedent
  (Fink-FAT: 111,275,131 processed ZTF alerts → 389,530 Solar System
  candidates → 327 new orbits, 65 unreported in MPC at publication time) is
  the proof this is not circular — ZTF's own real-time pipeline processing
  alerts does not mean every alert was linked into a reported orbit. Historical
  reprocessing of the full archive with a dedicated linker can still surface
  candidates ZTF's own pipeline never assembled into a discovery.
- **Fink/Fink-FAT and SNAPS are architecture and benchmark references** for
  the linker and ranker, per the brief.
- **WISE/NEOWISE, DECam, and TESS are demoted to secondary/paused.** Their
  code (`fetch_wise_archive`, `fetch_decam_archive`, `fetch_tess_ffis`,
  `fetch_discovery`), the Gate P1–P5 evidence, and
  `docs/SURVEY_NATIVE_CONFIDENCE_POLICY.md` are **not deleted** — they remain
  a working, previously-verified secondary path and a decision record. They
  are simply no longer the pipeline the operator wants developed next.
- **Live ZTF alert-stream monitoring and live ATLAS remain training/reference
  only** — that specific prohibition is unchanged and is not what this
  decision reverses. The distinction is: *live, real-time* ZTF/ATLAS alert
  consumption is still circular (ZTF ZAPS/ATLAS already process and submit
  from that stream in real time); *archival, historical-replay* reprocessing
  of ZTF DR24 is not circular, per the brief's own argument and the Fink-FAT
  precedent.
- **The production-capability gate register (`docs/PRODUCTION_READINESS.md`
  P1–P5) was written against the WISE/DECam/TESS pipeline.** Those gates
  stay CLOSED as a historical record of verified work on that path, but they
  no longer define production readiness for the *current* primary pipeline.
  New gates for the ZTF DR24 historical-replay pipeline must be defined
  before that pipeline can be called production-capable. Do not claim
  production readiness for the new pipeline until that happens.

## Brief Requirements (from `docs/neo_discovery_agent_brief.md`, now binding)

- Candidate language: use "candidate NEO," "candidate moving object,"
  "unassociated moving-source candidate," or equivalent non-confirming terms.
- Historical replay discipline: no future-catalog leakage — reconstruct the
  known-object catalog state as of the start of the replay window, and never
  use catalog knowledge gained after the replay window ends.
- Source-verification discipline: verify public APIs, auth requirements,
  schema behavior, rate limits, and current counts before building ingestion
  jobs. Phase 0 deliverables (`data_sources_verified.md`, `schema_snapshot/`,
  `sample_ingest_report.md`, `auth_requirements.md`,
  `pretrained_model_audit.md`) are required before Phase 1 ingestion begins.
- Model discipline: build the rule-based historical-replay baseline before
  any ML; build known-object exclusion before candidate ranking; build
  simple linear tracklet linking before graph/neural linking; train
  LightGBM/XGBoost before experimenting with end-to-end neural ranking.
  Pretrained/deep models are feature extractors or baselines only, and
  require a `pretrained_model_audit.md` entry before use.
- Every candidate score is a prioritization score, not a discovery or
  confirmation.

---

## The Pipeline (per the brief's architecture)

```
ZTF DR24 / public ZTF archive (bounded historical time window)
    │
    ▼
Source verifier (Phase 0): confirm Fink/IRSA-ZTF/JPL SBDB/MPC access,
    auth, schema, rate limits — before any ingestion code depends on them
    │
    ▼
Historical replay ingestor: pull the bounded window with raw payloads,
    hashes, timestamps, full provenance
    │
    ▼
Known-object exclusion: time-aware catalog snapshot lookup — suppress
    detections already associated with a known object AT OBSERVATION TIME
    │
    ▼
Alert/image quality filter: rule-based artifact rejection; real/bogus
    score if available
    │
    ▼
Feature builder: motion rate, direction consistency, brightness, filter,
    SNR, sky position, quality flags, detection count, time span
    │
    ▼
Tracklet linker: linear motion + time/direction consistency (Fink-FAT-style
    reference architecture)
    │
    ▼
Candidate ranker: LightGBM/XGBoost — NOT the existing three-tier ZTF
    classifier, which was trained for live real/bogus classification, not
    historical-replay candidate ranking. This is new work.
    │
    ▼
Retrospective validator: compare ranked candidates against later MPC/JPL
    outcomes WITHOUT future-catalog leakage — recall, purity@K, false
    positive rate
    │
    ▼
Candidate report generator: auditable Markdown/JSON reports, no discovery
    claim, explicit "unconfirmed until validated by appropriate authority"
    caveat
    │
    ▼ (only for a candidate an operator chooses to pursue for real-world submission)
Skills/adversarial_review.py → operator review → Skills/export_ades_report.py
    → MPC submission → NEOCP → MPC provisional designation → paper
```

The final four stages (adversarial review through paper) are unchanged from
the existing pipeline and are already implemented — they operate on whatever
`ScoredNEO`-shaped candidate reaches them, regardless of source. What's new
is everything upstream of "Candidate ranker."

---

## Authoritative Reporting Body

**Minor Planet Center (MPC)** is the sole external submission target.
- Format: ADES PSV (mandatory since 2024)
- Observatory code: use `XXX` for initial submissions; MPC issues permanent code
- Web: https://minorplanetcenter.net/submit-observations
- After MPC posts to NEOCP, global observatories confirm independently — we do nothing

Do NOT contact NASA PDCO directly. Scout handles that automatically if warranted.

---

## Rejection Model (Adversarial Review)

`Skills/adversarial_review.py` tries to REJECT each candidate with 13 challenges
before any operator sees it. The logic: attempt to disprove that we found anything.
If the null hypothesis (that we found nothing) cannot be rejected, the candidate
proceeds to operator review. This stays unchanged under the new pipeline — it is
source-agnostic and consumes whatever `ScoredNEO` packet is produced.

---

## What to Report

- Candidates described as "consistent with NEO orbits" — never as "confirmed"
- All candidates are provisional until MPC assigns a designation
- No impact probability claims — defer entirely to CNEOS Scout/Sentry
- No "confirmed NEO" output anywhere in the pipeline

---

## What NOT to Build

**Do NOT add:**
- Public helper APIs that are not called by the pipeline
- Documentation files that repeat what other docs say
- Skills scripts that wrap a single function
- Live ZTF alert-stream or live ATLAS discovery code (still circular —
  distinct from ZTF DR24 archival historical replay, which is now the
  primary path)
- Any code that asserts impact probability
- Any code that contacts NASA PDCO directly

The v0.40–v0.87 accumulation cycle added 374 public APIs with zero production value.
This must not recur. Every new function must be called by the pipeline or by a Skill
that the operator actually runs.

---

## Immediate Next Steps (ordered, per the brief's phased plan)

1. **Phase 0 — Source verification** (required before any ingestion code is
   written): **materially complete as of v0.90.18** in
   `docs/evidence/phase0/`. JPL SBDB, MPC get-obs, and IRSA ZTF image metadata
   are live-verified; Fink schema access is blocked externally at TLS
   handshake; pretrained model use is deferred. Do not invent Fink schema
   behavior. Refresh these artifacts only when source behavior changes.
2. **Phase 1 — ZTF DR24 + Fink/SNAPS historical replay prototype**: bounded
   historical time window, known-object exclusion, rule-based quality
   filters, handcrafted tabular features, linear tracklet linker, logistic
   regression baseline, then LightGBM/XGBoost candidate ranker.
3. **Phase 2 — Validation**: compare against later MPC/JPL outcomes; recall
   and purity@K; logistic regression vs. LightGBM/XGBoost ablation.
4. **Use the ZTF DR24 production-capability gates** in
   `docs/ZTF_DR24_PRODUCTION_GATES.md`. The existing P1–P5 register describes
   the now-secondary WISE/DECam/TESS path; the Z0-Z7 gates control production
   readiness for ZTF DR24 historical replay.

---

## Doom Loop Prevention

Every session must read this file first. If a proposed task does not advance
the phases above, do not do it. Specifically:

- Do not add more helper functions to src/ modules
- Do not add more Skills that wrap individual functions
- Do not write more documentation that restates this document
- Do not re-train ML models unless a specific failure is diagnosed
- Do not query live ZTF/ATLAS alert streams for discovery purposes
  (archival ZTF DR24 historical replay is the exception — see above)
- Do not claim the new pipeline is production-capable before the Z0-Z7 gates in
  `docs/ZTF_DR24_PRODUCTION_GATES.md` are closed

If the highest-priority step is blocked by a human decision, say so and stop.
Do not fill the gap with busywork.
