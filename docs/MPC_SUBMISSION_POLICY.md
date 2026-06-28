# MPC Submission Policy — NEO Detection Pipeline

**Established**: 2026-06-21  
**Updated**: 2026-06-27 (discovery-paper framing; WISE/NEOWISE as primary data source)  
**Operator**: Jerome W. Lindsey III  
**Supersedes**: The prior "blocked until qualified expert review" guardrail in CLAUDE.md and AGENTS.md.

---

## Background

The project goal is a **defensible discovery paper**: find new NEOs in unreviewed archival
data (WISE/NEOWISE, DECam/NOIRLab, TESS FFIs), submit candidates to MPC, obtain a
provisional designation via independent NEOCP confirmation, and publish. This is not a
citizen-science reporting tool — every candidate must survive automated adversarial review
and operator review before any external submission.

The pipeline was previously configured with a guardrail stating that MPC submission was
"blocked until qualified expert review." Research (2026-06-21) revealed this was based on
a misunderstanding. The MPC, NEOCP, and CNEOS Scout chain *is* the expert review system.
No observatory — amateur or professional — arranges its own expert reviewer before
submitting to MPC.

Reference programs that operate this way without in-house astronomers:
- **IASC** (International Astronomical Search Collaboration): 50,000 participants,
  ~12,000 asteroid detections, ~5 NEOs confirmed, operating since ~2010.
- Amateur observatories worldwide hold MPC observatory codes and submit regularly.

---

## How the Global Infrastructure Works (and Why No In-House Expert Is Needed)

```
Pipeline quality gates pass
(MOID ≤ 0.05 AU, quality ≥ 2, rb ≥ 0.90, not known object)
         │
         ▼
Step 1: Submit observations to MPC  ←── YOU DO THIS
        ADES PSV format (preferred) or MPC 80-column
        Observatory code required (see §Getting an Observatory Code)
         │
         ▼
Step 2: MPC calculates digest2 score (automated, ~minutes)
        digest2 > 65 → object posted to NEOCP automatically
        digest2 ≤ 65 → object linked to known catalog or archived
         │
         ▼ (if digest2 > 65)
Step 3: NEOCP = global expert confirmation (automatic, ~hours)
        Professional follow-up observatories worldwide monitor NEOCP
        continuously and take confirmation images without being asked.
        This IS the independent expert confirmation step.
         │
         ▼ (simultaneous with Step 3)
Step 4: Scout (CNEOS/JPL) monitors NEOCP around the clock
        Computes short-term impact probability for every NEOCP object
        within minutes of posting. No action required from this pipeline.
         │
         ▼ (if Scout detects impact risk)
Step 5: Scout automatically alerts NASA PDCO
        Do NOT contact PDCO directly. Scout handles this.
        Do NOT publicly state impact probabilities. Defer to Scout/Sentry/PDCO.
         │
         ▼ (if object confirmed as new NEO)
Step 6: MPC assigns provisional designation, publishes MPEC
        Sentry takes over for long-term (100-year) impact monitoring.
```

---

## Getting an Observatory Code (One-Time Operator Action)

Before submitting any observations to MPC, the project needs a permanent 3-character
observatory code. This is a one-time setup step.

**Process**:
1. Prepare a batch of astrometric observations in ADES PSV format.
2. Submit using observatory code `XXX` (the standard placeholder for new observers).
3. Include a header with: longitude, latitude, altitude, and observer contact.
4. Use the same email address for the submission and for the MPC code request form at
   `https://minorplanetcenter.net/new_obscode_request`.
5. MPC assigns a permanent code within ~1 week.

**Notes**:
- No professional affiliation required.
- Astrometric accuracy must be ≤ 2 arcsec vs. Gaia-based ephemeris.
- Use `PYTHONPATH=src uv run python Skills/export_mpc_report.py` to generate
  ADES PSV output from a scored NEO JSON file.

---

## Two-Stage Review Process (Updated 2026-06-26)

The operator (Jerome W. Lindsey III) has established that the project goal is a
**defensible discovery paper**, not a citizen-science reporting tool. The pipeline
generates candidates; they must pass two review stages before any external submission:

```
Pipeline scores candidates
          │
          ▼
Stage 1: Adversarial Review (Skills/adversarial_review.py)
         Automated agent tries to REJECT each candidate by finding fatal flaws.
         Verdicts: SURVIVE / BORDERLINE / REJECT
         Only SURVIVE/BORDERLINE candidates advance.
          │
          ▼
Stage 2: Operator Review (Jerome)
         Jerome reviews survivors manually and decides which to submit.
          │
          ▼
Stage 3: MPC Submission (once observatory code resolved — see §TODO)
         Submit ADES PSV observations → MPC assigns provisional designation
          │
          ▼
Stage 4: Independent Confirmation
         NEOCP follow-up observatories confirm or refute the candidate.
          │
          ▼
Stage 5: Discovery Paper
         Journal paper documents the discovery with MPC designation as proof.
```

**Adversarial review challenges** (offline, always run):
1. Orbit quality (quality_code ≥ 2 required; 1 = WARNING; 0 = FAIL)
2. Arc length (< 0.5 days = FAIL; < 1.0 days = WARNING)
3. Multi-night requirement (< 2 distinct nights = FAIL; exactly 2 = WARNING)
4. Real/bogus gate (< 0.90 = FAIL; 0.90–0.92 borderline = WARNING)
5. Known-object posterior (> 0.50 = FAIL; > 0.20 = WARNING)
6. Artifact posterior (> 0.30 = FAIL; > 0.15 = WARNING)
7. NEO dominance (neo_candidate posterior < 0.30 = FAIL; < 0.50 = WARNING)
8. MBA confusion (main_belt_asteroid posterior > 0.40 = FAIL; > 0.25 = WARNING)
9. Motion rate plausibility (< 0.05 or > 200 arcsec/hr = FAIL)
10. MOID-arc consistency (MOID ≤ 0.10 AU claimed from sub-day arc = WARNING)
11. Motion consistency (score < 0.40 = FAIL; < 0.60 = WARNING)

**Adversarial review challenges** (live, run when not --offline):
12. MPC field scan (> 10 known objects in 0.5° cone = FAIL; > 0 = WARNING)
13. Cross-survey confirmation (cross-check primary detection against a secondary archive; no confirmation = WARNING)

**Verdict rules**:
- REJECT: any FAIL → do not advance
- BORDERLINE: no FAIL, ≥2 WARNINGs → operator scrutiny required
- SURVIVE: no FAIL, 0–1 WARNINGs → advance to operator review

---

## Submission Gates (What the Pipeline Already Enforces)

`ready_for_submission()` in `alert.py` enforces all required pre-submission checks:

| Gate | Threshold | Rationale |
|------|-----------|-----------|
| MOID | ≤ 0.05 AU | NEO/PHA zone — worth reporting |
| Orbit quality code | ≥ 2 | Multi-night arc; MOID is reliable |
| real_bogus score | ≥ 0.90 | High-confidence real detection |
| Alert pathway | ≠ `known_object` | Must not be an already-catalogued object |

These gates are necessary but not sufficient.  A candidate must also pass
adversarial review and operator review before any external submission.

---

## Permanent Guardrails (Never Removed)

These guardrails are not affected by this policy change:

- **Never assert impact probability**: Never state or imply a probability of Earth
  impact in any pipeline output. Defer to Scout/Sentry/CNEOS for all hazard statements.
- **Never contact NASA PDCO directly**: Scout does this automatically when warranted.
  Direct contact is neither required nor appropriate for citizen-science submissions.
- **Never publicly announce a candidate before MPC confirmation**: Submit to MPC and
  wait for MPEC publication before any public statement.
- **Never output "confirmed NEO"** for any internally detected object. All objects
  are "candidates" until MPC assigns a provisional designation.
- **Never skip the quality gates**: The gates in `ready_for_submission()` are the
  minimum bar. Do not lower them.

---

## Format Reference

**Preferred**: ADES PSV (pipe-separated values), adopted by MPC as preferred format
since 2018, mandatory for new observatory code requests since 2024.

**Accepted**: MPC 80-column (MPC1992 / obs80 format) — still accepted but superseded.

**Subject line for NEO candidates**: Include `NEO CANDIDATE` in submission email subject.

**Pipeline output tools**:
- `Skills/export_mpc_report.py` — MPC 80-column format
- `Skills/export_ades_report.py` — ADES PSV format (preferred for new submissions)

---

## Scope of This Policy

This policy authorizes MPC submission of **observation reports** for candidates passing
all pipeline quality gates. It does not authorize:

- Any claim of a new NEO discovery until MPC assigns a provisional designation.
- Any statement of impact probability.
- Any direct contact with NASA PDCO or IAU CBAT.
- Any submission on behalf of another observer's data.

This policy was established by operator decision on 2026-06-21 based on research into
MPC submission best practices for citizen-science programs.

---

## TODO for Future Agents — Escalation Path (Unresolved)

**Status**: Open as of 2026-06-21. Operator-approved direction: implement a
viable escalation path so that when the pipeline detects a high-quality
candidate, there is a concrete, executable submission mechanism.

**The unresolved question**: This pipeline re-reduces *publicly archived survey data*
(WISE/NEOWISE via IRSA, DECam/NOIRLab NSC DR2, TESS FFIs via MAST) — it does not
make original telescope observations. MPC observation reports normally require the
submitting observatory to be the original observer and to hold a registered observatory
code tied to a specific observing site.

**Known constraints**:
- This project has no telescope and makes no original observations.
- An observatory code (3-char MPC identifier) is normally issued to a specific
  instrument/site, not to a data-analysis pipeline.
- The existing `ready_for_submission()` gates and ADES PSV export
  (`Skills/export_ades_report.py`) are implemented; the missing piece is
  authorization to submit.
- The primary discovery data source is WISE/NEOWISE archival photometry (IRSA,
  no credentials required); secondary sources are DECam/NOIRLab and TESS FFIs.

**Research needed** (for the agent that picks this up):
1. Determine whether a data-analysis pipeline re-reducing public archival data
   from WISE/NEOWISE, DECam/NOIRLab, or TESS can submit MPC reports, and if so,
   under what observatory code.
2. Contact MPC to ask specifically: "We reduce publicly archived WISE/NEOWISE
   infrared detections using our own pipeline to identify new NEO candidates.
   Can we submit observation reports, and if so, what observatory code applies?"
3. Investigate whether IRSA/NOIRLab/MAST have data-use policies that affect
   downstream MPC submissions from their public data products.
4. Document the answer in this file and update `Skills/export_ades_report.py`
   and `alert.py` accordingly.

**Until this is resolved**:
- `run_pipeline.py` will print an escalation notice for every candidate that
  passes `ready_for_submission()`, directing the operator to this TODO.
- No actual MPC submission should be made.
- `alert.py` must fail closed for live MPC submission unless all of the
  following are true: the operator intentionally sets
  `NEO_MPC_SUBMISSION_APPROVED=1`, a real non-placeholder MPC observatory code
  is provided, and the candidate has passed the pipeline quality gates plus
  adversarial/operator review.
- The operator (Jerome W. Lindsey III) retains the decision on when to
  contact MPC and how to characterize the data source.
