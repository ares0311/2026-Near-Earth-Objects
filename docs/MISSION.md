# MISSION.md — Authoritative Project Goal and Pipeline Strategy

**Read this before reading anything else. This file overrides any conflicting guidance.**

Last updated: 2026-06-26

---

## The Goal

Find genuinely NEW Near-Earth Objects (NEOs) in astronomical data that professional
NEO pipelines have not yet processed. Candidates that survive automated and operator
review are submitted to the Minor Planet Center (MPC). If confirmed, this supports
a publishable scientific paper.

We do NOT claim discovery. We claim to have found **candidates for expert review**.

---

## The Two-Part Data Strategy

### Part 1: Training Data (use ZTF and ATLAS)

ZTF and ATLAS are used ONLY to train and calibrate the ML models:
- Tier 1 XGBoost: trained on ZTF real/bogus labels
- Tier 2 CNN: trained on ZTF image triplet labels
- Tier 3 Transformer: trained on MPC tracklet sequences
- Ensemble stacker: trained on ZTF-origin validation samples

Once trained, the models are FROZEN. ZTF and ATLAS are NOT queried during discovery.

### Part 2: Discovery Data (use unreviewed archives)

The discovery fetch layer targets data that professional NEO pipelines have NOT
already processed. In priority order:

| Source | Why it's unreviewed | Access |
|---|---|---|
| **TESS Full-Frame Images (FFIs)** | TESS is an exoplanet mission. No NEO detection pipeline runs on FFIs. Full sky, 30-min cadence, 2018–present. | NASA MAST (public) |
| **DECam/NOIRLab archival data** | Dark Energy Survey and other DECam programs image large sky areas but are not NEO-focused. No systematic NEO linking applied. | NOIRLab Astro Data Lab (public) |
| **WISE/NEOWISE raw images** | NEOWISE team characterizes KNOWN objects via thermal modeling. The raw archival images have not been systematically searched for new NEO discoveries via source linking. Infrared finds low-albedo objects that optical surveys miss. | NASA IPAC (public) |
| **Rubin/LSST early data** | As Rubin comes online (2025–2027), early data releases will contain untapped NEO discovery potential before the LSST Solar System Processing pipeline catches up. | LSST Science Platform |

**NEVER use ZTF/ALeRCE or ATLAS as the discovery source.** ZTF ZAPS and the ATLAS
pipeline have already processed those streams and submitted to MPC. Searching them
for new NEOs is circular.

---

## The Pipeline

```
Unreviewed Archive (TESS / DECam / WISE)
    │
    ▼
fetch.py: retrieve image data or source catalogs from archive APIs
    │
    ▼
preprocess.py: extract point sources, difference images, photometry
    │
    ▼
detect.py: identify moving sources (motion > 0.05 arcsec/hr)
    │
    ▼
link.py: THOR-style tracklet linking across nights (≥3 detections, ≥2 nights)
    │
    ▼
orbit.py: Gauss IOD + differential correction → orbital elements + MOID
    │
    ▼
classify.py: ML ensemble (Tier 1 XGBoost + Tier 2 CNN + Tier 3 Transformer)
    │
    ▼
score.py: hazard assessment, discovery priority ranking
    │
    ▼
ready_for_submission() gate:
  MOID ≤ 0.05 AU
  orbit quality code ≥ 2
  real_bogus score ≥ 0.90
  not a known MPC object
    │
    ▼ (if gate passes)
Skills/adversarial_review.py: 13-challenge automated rejection attempt
  → REJECT: discard candidate
  → BORDERLINE / SURVIVE: pass to operator
    │
    ▼
Operator review (Jerome W. Lindsey III): reviews SURVIVE/BORDERLINE candidates
    │
    ▼
[HUMAN GATE] Jerome decides which candidates to submit
    │
    ▼
Skills/export_ades_report.py: format in MPC ADES PSV format
    │
    ▼
Submit to MPC (observatory code XXX until permanent code assigned)
    │
    ▼
MPC: calculates digest2 automatically
  digest2 > 65 → posted to NEOCP
  NEOCP → global follow-up observatories confirm independently
  Scout/Sentry → impact probability (automated; we do not assert this)
    │
    ▼
MPC assigns provisional designation → MPEC publication
    │
    ▼
Paper: "We identified N candidates from TESS/DECam/WISE using this pipeline.
        Here is the methodology and the candidates submitted to MPC."
```

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
proceeds to operator review.

A separate, candidate-specific rejection model may be built once a specific candidate
is found — that model is tailored to the specific object, its orbit, its photometry,
and any alternative explanations (artifact, known MBA, satellite, etc.). This model
cannot be specified in advance because it depends on what is found.

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
- Additional fetch sources for ZTF/ATLAS discovery (they are training data only)
- Any code that asserts impact probability
- Any code that contacts NASA PDCO directly

The v0.40–v0.87 accumulation cycle added 374 public APIs with zero production value.
This must not recur. Every new function must be called by the pipeline or by a Skill
that the operator actually runs.

---

## Training Data Cleanup (TODO)

The ML models are trained and weights are committed:
- `models/tier1_xgb.json` — Tier 1 XGBoost (KEEP)
- `models/tier2_cnn.pt` — Tier 2 CNN (KEEP)
- `models/tier3_transformer.pt` — Tier 3 Transformer (KEEP)
- `models/ensemble_stacker.pkl` — Ensemble meta-learner (KEEP if present)

Raw training data cached locally (ZTF alert JSONs, MPC observation downloads,
ALeRCE sequence files) should be DELETED from the operator's Mac once models
are confirmed working. These are reproducible from public sources. Storage
freed is significant (estimated several GB). Operator action required:

```bash
# After confirming model weights load correctly via:
PYTHONPATH=src uv run python Skills/validate_model_weights.py

# Delete cached training data (NOT the model weights):
rm -rf ~/.neo_cache/training/
rm -rf data/ztf_alerts_raw/
rm -rf data/mpc_sequences_raw/
rm -rf data/alerce_sequences_raw/
# Confirm models/ directory still intact:
ls -lh models/
```

---

## Immediate Next Steps (ordered)

1. **Redesign `fetch.py` discovery layer** — replace `fetch_ztf` / `fetch_atlas`
   discovery path with `fetch_tess_ffis`, `fetch_decam_archive`, `fetch_wise_archive`.
   ZTF/ATLAS fetch functions stay for training use only.

2. **PR for dead code removal** — 374 dead helper APIs and their tests removed
   (commit `0c49d83` on `claude/general-session-rvaEE`). Needs PR and CI.

3. **Jerome contacts MPC** about observatory code for a data-analysis pipeline
   (not a telescope). See `docs/MPC_SUBMISSION_POLICY.md §TODO for Future Agents`.

4. **Run pipeline on TESS FFIs or DECam data** — first real discovery attempt
   on unreviewed data. Operator action after Step 1 is merged.

---

## Doom Loop Prevention

Every session must read this file first. If a proposed task does not advance
Step 1–4 above, do not do it. Specifically:

- Do not add more helper functions to src/ modules
- Do not add more Skills that wrap individual functions
- Do not write more documentation that restates this document
- Do not re-train ML models unless a specific failure is diagnosed
- Do not re-run ZTF/ATLAS queries for discovery purposes

If the highest-priority step is blocked by a human decision, say so and stop.
Do not fill the gap with busywork.
