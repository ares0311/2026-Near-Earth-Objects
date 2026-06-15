# CLAUDE.md — NEO Detection & Ranking Project

This file is read automatically by Claude Code at session start.
It contains the facts a coding agent needs to work productively without re-reading every document.

---

## MANDATORY SESSION-START PROTOCOL

**At the start of every session, before planning or executing any steps, you must:**
0. Run `git pull origin main` — the local repo resets to a checkpoint at each session start; pull ensures all files reflect the latest committed state before reading them.
1. Call `Read` on `CLAUDE.md` — do not rely on memory or prior context. (This file; re-read to reactivate all standing rules.)
2. Call `Read` on `AGENTS.md` — do not rely on memory or prior context.
3. Call `Read` on `docs/PRODUCTION_READINESS.md` — do not rely on memory or prior context.

These steps are non-negotiable. No planning or code changes may happen before all four are complete.

---

## PRIMARY DIRECTIVE

**You may ONLY work on tasks that advance this project to PRODUCTION.**

Before proposing or executing any task, apply this gate:

> *Does this task close or directly unblock a named T1 or T2 gap from `docs/PRODUCTION_READINESS.md`?*

If the answer is NO, do not do it. In particular:
- **Never add new public helper APIs** unless they directly unblock a named gap. The v0.77–v0.87 API accumulation cycle (110 helpers, zero production impact) must never recur.
- **Never add new Skills scripts** that are single-function wrappers. Only add a Skill if it is operationally necessary for a named gap.
- **Never add new documentation files** that duplicate existing content.
- **Never propose log modules, schemas, or scaffolding** that do not directly unblock a named T1 or T2 gap.
- **Never repeat work listed under "What Is Complete"** in `docs/PRODUCTION_READINESS.md`.

If the highest-priority T1 gap cannot be resolved because a human blocker is unresolved, **state that explicitly** and limit scope to T2 gaps or documentation sync.

---

## Standing Rules

- Before switching branches or editing tracked files, check for
  `Logs/tier3_pilot.active.json`. If present, do not alter the shared checkout
  until the operator run exits and removes the marker.

- **Python runtime is 3.14.3 — always use `uv run`**: The project venv is
  Python 3.14.3, managed by uv from `uv.lock`. Never invoke bare `python`,
  `pytest`, `mypy`, or `ruff` directly — always prefix with `uv run` so the
  correct interpreter and locked dependencies are used. CI enforces the same
  via `astral-sh/setup-uv@v5` with `python-version: "3.14"`.
  Example: `PYTHONPATH=src uv run python -m pytest`

- **Always comment all code**: Every function, class, script, shell command, and non-trivial code block must include comments explaining what it does and why. This applies to all Python source files, all Skills scripts, all shell commands given to the operator, and all inline code snippets in documentation. No exceptions. This rule overrides any default behavior that would omit comments.
- **caffeinate all long-running Mac commands**: Any operator command expected to run longer than ~30 seconds must be prefixed with `caffeinate -i` to prevent macOS from sleeping mid-run. This applies to all downloads, training runs, and pipeline executions. Example: `caffeinate -i uv run python Skills/download_ztf_training_alerts.py ...`
- **All long-running scripts must print live progress with ETA**: Any script or pipeline stage that runs for more than a few seconds MUST emit per-item or per-batch progress lines to **stdout**, including: items processed / total, current status, running accepted counts, elapsed time, and estimated time remaining (ETA). Silent long-running processes are unacceptable — the operator must always be able to see that the process is alive and estimate when it will finish. This rule applies to all Skills scripts that loop over network queries, training epochs, or large data processing. Use `print(..., flush=True)` (stdout, NOT stderr — stderr is not reliably interleaved with stdout in the operator's terminal). ETA format: `elapsed {m}m{s:02d}s  ETA {m}m{s:02d}s`. ETA must be computed from a measurable quantity (bytes read, items processed, batches done) — elapsed-only heartbeats are not acceptable as a substitute for ETA.
- **Diagnose root cause before writing any fix (symptom-loop prevention)**:
  Before writing code to fix a hang, missing output, wrong output, or performance problem, you MUST first state the root cause in one sentence from first principles. If you cannot state the root cause, do NOT write code — re-read the diagnostic output and reason about it until you can. Applying a workaround (e.g., a heartbeat, a retry, a timeout) without identifying the root cause is prohibited.

- **Physically impossible output is a diagnostic signal — stop and reason**:
  If operator output contains a value that is physically impossible (e.g., a 7.1 MB file read in 0.0 s; a network call completing faster than a round-trip), STOP. That value tells you the operation did NOT do what you assumed. Reason about what mechanism produces that value before writing any code. Example: "file read in 0.0 s" means the OS returned without reading bytes (mmap, cached descriptor, or placeholder) — the actual I/O will happen later, elsewhere.

- **Failed fix → re-diagnose, not re-patch**:
  If a fix lands (PR merged, operator re-runs) and the operator reports the same category of failure, the root cause was not correctly identified. Do NOT apply another layer of the same pattern (another heartbeat, another print, another retry). Re-diagnose from the original operator output as if no fix had been attempted. The second failure is proof the first diagnosis was wrong.

- **State predicted output before submitting a PR**:
  Before opening any PR that fixes a hang or missing output, write explicitly: (a) the root cause in one sentence, (b) what the operator's console WILL show after the fix, and (c) what it will show if the root cause was still wrong. If you cannot answer all three, re-diagnose before writing the PR.

- **Operator always runs from main — no exceptions**: The operator's Mac always runs code from the `main` branch. Never instruct the operator to `git checkout` a feature branch or `git pull origin <feature-branch>`. Feature branch code must not be given to the operator to run until it is merged to main.
- **Merge PR before giving operator commands**: Before giving the operator any command that depends on a code fix or new script, the PR containing that fix must be merged to `main` first. Wait for CI to pass, merge the PR, confirm the merge, then give the operator the command.
- **Always prepend `git pull origin main` to operator command sequences**: Every block of operator commands must begin with `git pull origin main` to ensure the operator has the latest merged code before running anything.
- **Close PRs promptly**: After CI passes, merge and close the PR immediately. Do not accumulate open PRs. One PR at a time; merge before opening the next.
- **Skills directory**: Any standalone `.py` utility script created to perform a task must be saved in `Skills/` at the project root.
- **No impact claims**: Never assert a probability of Earth impact from internally computed data alone. Always defer to MPC/CNEOS for authoritative hazard assessment.
- **Alert protocol is sacred**: The NASA/MPC alert pathway (see §Alert Protocol) must never be triggered on unconfirmed detections. Require independent confirmation first.
- **Dead code must be removed, not tested**: If a function or class has no reachable callers, delete it rather than adding a test.
- **Conservative by default**: When uncertain about classification, flag for human review. Never output "confirmed NEO" for internally detected objects.
- **Calibration promotion is KPI-based**: Production calibration is approved only
  when the quantitative gate in `docs/PRODUCTION_READINESS.md` passes on held-out
  real labeled data. Reliability diagrams are evidence artifacts, not a human
  approval gate. Any failed or missing KPI blocks promotion.

---

## Project

**Near-Earth Object Detection and Ranking Pipeline**
Automated pipeline for detecting, linking, classifying, and ranking Near-Earth Object (NEO) candidates from publicly available survey photometry, with MPC-compatible reporting and a NASA alert pathway for high-confidence hazard signals.

Repository: `<owner>/neo-detection` (to be created)
Active branch: `main`

---

## Scientific Context

Near-Earth Objects are small solar system bodies with perihelion distances $q < 1.3$ AU. They are divided into four dynamical classes:

| Class | Definition |
|---|---|
| Amor | $1.017 < q < 1.3$ AU |
| Apollo | $a > 1.0$ AU, $q < 1.017$ AU |
| Aten | $a < 1.0$ AU, $Q > 0.983$ AU |
| IEO (Atira) | $Q < 0.983$ AU |

Potentially Hazardous Asteroids (PHAs) are NEOs with absolute magnitude $H \leq 22$ (diameter $\gtrsim 140$ m) and Minimum Orbit Intersection Distance (MOID) $\leq 0.05$ AU. The pipeline must identify and flag PHA candidates.

The global NEO survey is dominated by:
- **ZTF** (Zwicky Transient Facility) — primary data source; public alert stream
- **ATLAS** — Asteroid Terrestrial-impact Last Alert System; 24–48 hr warning capability
- **Pan-STARRS** — deep survey; public catalog access
- **CSS** (Catalina Sky Survey) — MPC-feeding survey

As of 2026, approximately 35,000 NEOs are known. Rubin/LSST is expected to discover 100,000+ more over its 10-year survey.

---

## Architecture

```
Fetch → Preprocess → Detect → Link → Classify → Score → Alert
```

Each stage produces a typed, immutable result object. No shared mutable state.

### Module Build Order

| Module | Status | Tests | Description |
|---|---|---|---|
| `schemas.py` | complete | test_schemas.py | All pipeline data models (Pydantic, frozen) |
| `fetch.py` | complete | test_fetch.py | ZTF/ATLAS/MPC data retrieval |
| `preprocess.py` | complete | test_preprocess.py | Difference image handling, source extraction |
| `detect.py` | complete | test_detect.py | Moving object detection; streak/trail identification |
| `link.py` | complete | test_link.py | Tracklet linking across nights |
| `classify.py` | complete | test_classify.py | ML real/bogus + NEO type classification |
| `orbit.py` | complete | test_orbit.py | Preliminary orbit fitting; MOID calculation |
| `score.py` | complete | test_score.py | Hazard ranking; PHA flag; novelty score |
| `alert.py` | complete | test_alert.py | MPC report formatting; NASA alert protocol |
| `calibration.py` | complete | test_calibration.py | Classifier calibration (Platt / isotonic PAVA) |

Build in the order listed. Each module depends on all prior modules.

---

## Data Sources

### Primary Survey Data

**ZTF (recommended primary source)**
- Public alert stream via IRSA (`ztfquery` Python package or direct API)
- 3-night cadence over the full northern sky; $g$, $r$, $i$ bands
- Difference-image alerts include cutouts (science, reference, difference) — ideal for CNN input
- Access: `pip install ztfquery`; IRSA account required (free)
- Key fields per alert: `ra`, `dec`, `jd`, `magpsf`, `sigmapsf`, `fid`, `rb` (real/bogus score), `drb` (deep learning real/bogus), `ssdistnr`, `ssmagnr`

**ATLAS Forced Photometry Server**
- Public REST API; forced photometry at any sky position
- Orange ($o$) and cyan ($c$) bands; 2-day cadence
- Useful for confirming candidates found in ZTF
- Access: `https://fallingstar-data.com/forcedphot/`

**Minor Planet Center (MPC)**
- Known object catalog: `astroquery.mpc` or direct MPC API
- NEO Confirmation Page (NEOCP): unconfirmed candidates needing follow-up
- Submit formatted reports for new detections
- Access: `from astroquery.mpc import MPC`

**JPL Horizons / CNEOS**
- Ephemerides for known objects: `astroquery.jplhorizons`
- Close approach tables: CNEOS API
- Scout and Sentry impact monitoring output (read-only reference)

### Astrometric Reference
- **Gaia DR3** via `astroquery.gaia` — sub-milliarcsecond astrometry for calibration

---

## Core Design Decisions

### DECISION-001: ZTF as Primary Survey
ZTF provides the richest freely available alert stream with pre-computed difference images, a native real/bogus score, and a well-documented Python API. It is the most scientifically productive single choice for a new project without telescope access.

### DECISION-002: Tiered ML Architecture
Follow the same three-tier approach as the exoplanet pipeline:
- **Tier 1**: Gradient-boosted trees (XGBoost/LightGBM) on tabular features — fast, interpretable, works with small labeled sets (~500 examples)
- **Tier 2**: CNN on ZTF image triplets (science / reference / difference cutouts) — proven for real/bogus classification (Duev et al. 2019)
- **Tier 3**: Transformer on tracklet sequences — frontier method for multi-night linking and NEO type classification (Lin et al. 2022)

### DECISION-003: No Autonomous Impact Claims
The pipeline produces a ranked candidate list and hazard flags. It never autonomously asserts a probability of Earth impact. The alert pathway requires a computed MOID ≤ 0.05 AU AND independent MPC confirmation before any NASA notification.

### DECISION-004: MPC-Compatible Output First
All detections must be expressible in MPC 80-column format or the newer MPC JSON format. This ensures interoperability with the global NEO community regardless of downstream ML additions.

### DECISION-005: Conservative Classification
Mirror the exoplanet pipeline's conservatism:
- `None` feature scores fail gate conditions
- Unknown objects default to "candidate" not "confirmed NEO"
- PHAs require orbit quality code ≥ 2 before flagging

---

## Key Types (schemas.py)

All models use `ConfigDict(frozen=True)` — immutable after construction.

```python
Mission = Literal["ZTF", "ATLAS", "PanSTARRS", "CSS", "MPC"]

NEOClass = Literal["amor", "apollo", "aten", "ieo", "unknown"]

HazardFlag = Literal["pha_candidate", "close_approach", "nominal", "unknown"]

AlertPathway = Literal[
    "mpc_submission",        # Report to MPC for confirmation
    "neocp_followup",        # Object on NEOCP; request observations
    "nasa_pdco_notify",      # High-confidence PHA; follow NASA protocol
    "internal_candidate",    # Below threshold for external reporting
    "known_object",          # Matches MPC catalog
]

# Core signal
@dataclass(frozen=True)
class Tracklet:
    object_id: str
    observations: tuple[Observation, ...]  # ≥2 obs per tracklet
    arc_days: float
    motion_rate_arcsec_per_hour: float
    motion_pa_degrees: float

# Feature vector (all OptScore = float | None, bounded [0,1])
class CandidateFeatures(BaseModel):
    # Detection quality
    real_bogus_score: OptScore
    streak_score: OptScore
    psf_quality_score: OptScore
    # Motion
    motion_consistency_score: OptScore
    arc_coverage_score: OptScore
    nights_observed_score: OptScore
    # Photometry
    brightness_score: OptScore       # proxy for size
    color_score: OptScore             # g-r, r-i
    lightcurve_variability_score: OptScore
    # Orbit (populated after orbit.py)
    orbit_quality_score: OptScore    # 0=poor, 1=good
    moid_score: OptScore             # 1 = MOID ≤ 0.05 AU
    neo_class_confidence: OptScore
    pha_flag_confidence: OptScore
    # Catalog
    known_object_score: OptScore     # 0 = new, 1 = known

# Posterior over NEO classification hypotheses
class NEOPosterior(BaseModel):
    neo_candidate: Score             # genuine new NEO
    known_object: Score              # matches MPC catalog
    main_belt_asteroid: Score        # MBA on unusual orbit
    stellar_artifact: Score          # cosmic ray / satellite / artifact
    other_solar_system: Score        # comet, TNO, etc.

class HazardAssessment(BaseModel):
    hazard_flag: HazardFlag
    moid_au: float | None
    estimated_diameter_m: float | None
    absolute_magnitude_h: float | None
    neo_class: NEOClass
    alert_pathway: AlertPathway
    explanation: CandidateExplanation

class ScoredNEO(BaseModel):
    tracklet: Tracklet
    features: CandidateFeatures
    posterior: NEOPosterior
    hazard: HazardAssessment
    metadata: ScoringMetadata
```

---

## Pipeline Stage Specifications

### 1. fetch.py
**Inputs**: sky region (RA, Dec, radius) or target list, date range, survey selection
**Process**:
- Query ZTF alert stream via IRSA or `ztfquery`
- Download ATLAS forced photometry for confirmed positions
- Query MPC for known objects in the search field
- Query JPL Horizons for ephemerides of known NEOs

**Output**: `FetchResult(alerts, provenance: FetchProvenance)`

**Notes**:
- Lazy-import all survey-specific libraries inside functions
- Cache raw alerts to disk; never re-download what is already cached
- Record survey, filter, limiting magnitude, and epoch in provenance

### 2. preprocess.py
**Inputs**: raw alerts with image cutouts
**Process**:
- Validate difference image quality (PSF, background RMS)
- Normalize cutout pixel values to [0,1] for CNN input
- Extract aperture photometry and morphological features
- Apply astrometric correction relative to Gaia DR3

**Output**: `PreprocessResult(sources, provenance: PreprocessProvenance)`

**Notes**:
- No external image-subtraction pipeline needed — ZTF alerts already include difference cutouts
- For ATLAS: use forced-photometry magnitudes directly

### 3. detect.py
**Inputs**: preprocessed source catalog
**Process**:
- Filter on real/bogus score (`rb ≥ 0.65` default threshold; configurable)
- Identify moving sources: compare positions across epochs; compute apparent motion rate
- Flag streaks/trails (fast-moving NEOs may trail in 30s ZTF exposures)
- Cross-match against MPC known object ephemerides to separate new vs. known

**Output**: `DetectResult(candidates: list[RawCandidate], known_matches: list[KnownMatch])`

### 4. link.py
**Inputs**: single-night candidates across multiple nights
**Process**:
- Implement a simplified tracklet linker (THOR-inspired; Moeyens et al. 2021):
  - Pair detections consistent with solar system object motion (0.01–60 arcsec/hr)
  - Extend pairs to triplets and longer arcs using a $\chi^2$ orbit-consistency test
- Require ≥3 detections on ≥2 nights for a reportable tracklet
- Compute arc length, motion rate, position angle, and rate uncertainty

**Output**: `LinkResult(tracklets: list[Tracklet])`

**Notes**:
- Pure numpy/scipy implementation; no external orbit-determination dependency at this stage
- `orbit.py` handles full orbit fitting downstream

### 5. classify.py
**Inputs**: linked tracklets + image cutouts
**Process** (three-tier, build in order):

**Tier 1 — XGBoost on tabular features**
- Features: real/bogus score, motion rate, arc length, nights observed, brightness, color index, streak score, PSF elongation, MPC match distance
- Labels: ZTF real/bogus labels + MPC confirmed NEO catalog
- Output: `real_bogus_score`, `neo_class_confidence` as `OptScore`

**Tier 2 — CNN on image triplets** (build after Tier 1 is calibrated)
- Input: 63×63 pixel cutout triplets (science, reference, difference) normalized to [0,1]
- Architecture: adapted from Duev et al. (2019) — three parallel convolutional branches merged at dense layer
- Pre-trained weights from ZTF real/bogus training set (public) available as starting point
- Fine-tune on confirmed NEO vs. artifact subset
- Output: calibrated real/bogus probability

**Tier 3 — Transformer on tracklet sequences** (frontier; build after Tier 2)
- Input: sequence of (RA, Dec, magnitude, time, filter) observations per tracklet, tokenized per observation
- Architecture: standard encoder-only transformer (BERT-style) with positional encoding based on observation time
- Task: multi-class classification (neo_candidate / known_object / main_belt / artifact / other)
- Training data: MPC observation history for confirmed NEOs + MBA sample + artifact labels from ZTF
- Reference: Lin et al. (2022) applied transformers to asteroid light-curve classification

**Ensemble (Tier 3 output)**
- Stacking meta-learner (logistic regression) over Tier 1 + Tier 2 + Tier 3 outputs
- Calibrate final probabilities via `calibration.py` (Platt or isotonic)

### 6. orbit.py
**Inputs**: linked tracklets (≥3 nights recommended)
**Process**:
- Initial orbit determination via Gauss's method (pure Python/numpy)
- Improve with differential correction (least-squares fit to observed positions)
- Compute orbital elements: $a$, $e$, $i$, $\Omega$, $\omega$, $M_0$
- Classify as Amor/Apollo/Aten/IEO/MBA from $(a, e, q, Q)$
- Compute MOID (Minimum Orbit Intersection Distance) relative to Earth's orbit
- Assign orbit quality code (1 = arc < 1 day, 2 = multi-night, 3 = multi-week, 4 = opposition)

**Notes**:
- Use `astropy` for coordinate transformations
- For short arcs (<24 hr), MOID is unreliable — flag accordingly
- Do not use `skyfield` or `rebound` in v0; keep dependencies minimal

### 7. score.py
**Inputs**: classified tracklets with orbital elements
**Process**:
- Compute `HazardAssessment` for each candidate:
  - `moid_au` from `orbit.py`
  - `estimated_diameter_m` from absolute magnitude H using geometric albedo assumption ($p_v = 0.14$ default)
  - `hazard_flag`: PHA candidate if MOID ≤ 0.05 AU AND $H \leq 22$
  - `alert_pathway` from ordered gate (see §Alert Protocol)
- Compute derived scores:
  - `discovery_priority`: combination of novelty, orbit quality, and PHA flag
  - `followup_value`: based on brightness, arc length, orbit uncertainty
  - `scientific_interest`: unusual orbital elements, extreme $a$ or $e$, short MOID

### 8. alert.py
**Inputs**: `ScoredNEO` objects
**Process**:
- Format MPC 80-column observation report for any `alert_pathway` ≥ `mpc_submission`
- Generate human-readable candidate summary
- For `nasa_pdco_notify`: generate structured alert package (see §Alert Protocol)
- Log all alert actions with timestamps and provenance

---

## Alert Protocol

This section defines the mandatory decision tree for external reporting. **No step may be skipped.**

```
Computed MOID ≤ 0.05 AU
AND orbit quality code ≥ 2
AND Tier 1 real_bogus_score ≥ 0.90
AND NOT matched to MPC known object
         │
         ▼
Step 1: Submit to MPC via standard report format
        (astroquery.mpc or direct HTTP POST to minorplanetcenter.net)
         │
         ▼
Step 2: Monitor NEOCP for independent confirmation
        (wait ≥ 24 hours or ≥ 2 independent observatory confirmations)
         │
         ▼
Step 3: If CNEOS Scout/Sentry assigns impact probability ≥ 0.01%:
        → Open GitHub Issue tagged [HAZARD-ALERT]
        → Generate report to:
            NASA PDCO: https://www.nasa.gov/planetarydefense/contact
            IAU CBAT:  https://www.cbat.eps.harvard.edu/
        → Do NOT publicly announce impact probability;
          defer all public communication to NASA/CNEOS
```

**Guardrails**:
- Never skip MPC submission and independent confirmation before Step 3
- Never quote an impact probability in any public output
- Never suppress a genuine alert out of uncertainty — report and let authorities assess
- Store full provenance (observations, orbit fit, MOID computation) with every alert

---

## ML Training Data

| Dataset | Source | Size | Use |
|---|---|---|---|
| ZTF real/bogus labels | Duev et al. (2019) / Broker APIs | ~100,000 alerts | Tier 1 + Tier 2 training |
| MPC confirmed NEO catalog | `astroquery.mpc` | ~35,000 objects | Positive labels |
| MPC MBA sample | `astroquery.mpc` | large | Negative labels for NEO classifier |
| ZTF NEO observation history | IRSA | varies | Tracklet sequence training |
| ATLAS detections of known NEOs | ATLAS server | varies | Tier 1 feature validation |

**Label quality note**: Use only MPC-numbered objects as high-confidence positives. Provisional designations may be reassigned and should be treated with lower weight.

---

## Scoring Model

### Hypotheses

| Symbol | Hypothesis | Prior |
|---|---|---|
| $H_\text{neo}$ | Genuine new NEO candidate | 0.05 |
| $H_\text{ko}$ | Known MPC object | 0.30 |
| $H_\text{mba}$ | Main-belt asteroid | 0.35 |
| $H_\text{art}$ | Instrumental artifact | 0.25 |
| $H_\text{other}$ | Other solar system body | 0.05 |

Priors are deliberately pessimistic about new NEOs (most moving objects are known MBAs or artifacts). Adjust priors for high-ecliptic-latitude fields where MBA contamination is lower.

### Log-Score Model

$$\ell_i = \log P(H_i) + \sum_k w_{ik}\,\phi_k(\mathbf{D})$$

$$p_i = \frac{\exp(\ell_i - \ell_{\max})}{\sum_j \exp(\ell_j - \ell_{\max})}$$

All features $\phi_k \in [0,1]$; missing features contribute 0 (neutral).

### Key Feature Weights (planet_candidate analogue → neo_candidate)

```
log_score_neo =
    log_prior_neo
    + 2.0 * real_bogus_score
    + 1.5 * arc_coverage_score
    + 1.5 * nights_observed_score
    + 1.2 * motion_consistency_score
    + 1.0 * orbit_quality_score
    - 2.5 * known_object_score
    - 2.0 * stellar_artifact_score
    - 1.5 * main_belt_consistency_score
```

---

## Quality Commands

**Always use `uv run` — never call `python` or `pytest` directly.**
The project venv is Python 3.14.3 managed by uv from `uv.lock`. Using bare
`python` risks picking up a different system interpreter and diverging from CI.

```bash
# Lint
uv run ruff check .
uv run ruff check . --fix

# Type-check
uv run python -m mypy src

# Tests (PYTHONPATH=src set via env for uv run)
PYTHONPATH=src uv run python -m pytest

# macOS local runs with XGBoost/OpenMP may need deterministic threading
OMP_NUM_THREADS=1 PYTHONPATH=src uv run python -m pytest

# All three
uv run ruff check . && uv run python -m mypy src && PYTHONPATH=src uv run python -m pytest
```

CI uses `uv sync --extra dev` (from `uv.lock`) then `uv run` — identical to
the local venv. Python version is pinned to 3.14 in `.github/workflows/ci.yml`.

Live integration tests (require network access to ZTF/ATLAS/MPC) must be marked:

```python
@pytest.mark.integration_live
```

and excluded from CI.

---

## Guardrails

- Never output "confirmed NEO" for internally detected objects
- Never state or imply an impact probability without MPC/CNEOS confirmation
- Always expose artifact and known-object evidence alongside every candidate score
- Store scoring model version and observation provenance with every result
- Prefer conservative classifications; when uncertain, flag for human review
- The alert protocol is non-negotiable and must be followed in full

---

## Key Literature

- Bellm, Eric C., et al. "The Zwicky Transient Facility: System Overview, Performance, and First Results." *PASP*, vol. 131, 2019, p. 018002.
- Duev, Dmitry A., et al. "Real-bogus Classification for the Zwicky Transient Facility Using Deep Learning." *MNRAS*, vol. 489, no. 3, 2019, pp. 3582–3590.
- Lin, Hsing-Wen, et al. "Astronomical Image Time Series Classification Using CONVolutional Neural nETworks (ConvNet)." *AJ*, vol. 163, 2022, p. 154.
- Moeyens, Joachim, et al. "THOR: An Algorithm for Cadence-independent Asteroid Discovery." *AJ*, vol. 162, no. 4, 2021, p. 143.
- Ye, Quanzhi, et al. "Hundreds of New Near-Earth Asteroids Found with ZTF." *AJ*, vol. 159, no. 2, 2020, p. 70.
- Jedicke, Robert, et al. "Observational Selection Effects in Asteroid Surveys." *Asteroids III*, Univ. of Arizona Press, 2002, pp. 71–87.
- Mainzer, Amy, et al. "Initial Performance of the NEOWISE Reactivation Mission." *ApJ*, vol. 792, no. 1, 2014, p. 30.

---

## Current State (v0.87.9)

All 10 pipeline modules are complete. The offline suite passes 3528 tests, with
2 live/integration checks deselected. CI is expected to
remain green on Python 3.14 with the 100% coverage target. Background
automation uses one unified CLI with top-level SQLite audit logs, offline
readiness checks, live policy validation, no-secret credential inventories,
approval bundles, operator handoffs, and fail-closed signoff readiness. All
three ML tiers now have trained weights: Tier 1 XGBoost (val_acc=99.95%),
Tier 2 CNN (val_acc=91.3%), and Tier 3 Transformer (val_macro_f1=0.9400,
best epoch 17/30). **T1-D calibration KPI gate PASSED for all tiers
(2026-06-14)**: Tier 1 XGBoost, Tier 2 CNN, and ensemble stacker all passed
all 7 KPIs; `promotion_gate_passed=true`. **T1-A is now CLOSED.** Ensemble
stacker (10-feature logistic regression meta-learner over Tier 1 + Tier 2):
AUC=0.9809, Brier=0.0211, ECE=0.0000; `models/stacker_coef.json` produced.
Production is now blocked only on T1-C (first real end-to-end pipeline run on
live ZTF data) and T1-B live dry-run policy sign-off. Jerome W. Lindsey III
approved the five-class label policy and a 50-sequence-per-class pilot on
2026-06-10.

The first operator pilot attempt was retained as diagnostic evidence. Its
200-row manifest contained 28 duplicate comet rows, reducing collection to 172
unique objects, and its MPC checkpoint recorded 103 zero-result queries without
distinguishing provider errors. Corrected uniqueness, provider-error circuit
breaker, parallel-mode circuit-breaker bias fix, and held-out Tier 3
training-report gates are merged. The MPC fetcher now correctly classifies
None-table returns and query-level errors as insufficient_observations rather
than provider failures, preventing false circuit-breaker trips on bad
designations.

A second pilot run (post-v0.87.2) fetched 0 observations for all 400
candidates because the MPCORB NEA.txt catalog uses extended packed
designations for numbered asteroids ≥100000 (e.g. `A0004` for asteroid 100004)
which `_unpack_designation()` did not handle — all were passed literally to
`MPC.get_observations()` which returned None. Fixed in v0.87.3 (PR #85). All
three MPCORB packed formats are now handled: leading-zero numeric (`00433` →
`433`), 7-char provisional (`K23A00A` → `2023 AA`), and base-62 extended
numeric (`A0004` → `100004`).

A third pilot run (post-v0.87.3) returned `insufficient_observations` for all
400 candidates because `MPC.get_observations()` now returns epoch as
`astropy.Quantity(value, unit='d')` in newer astroquery versions. `float()` on
a dimensioned Quantity raises `TypeError`, silently caught in the row-parsing
`try/except`, discarding every row. Fixed in v0.87.4 (PR #86): epoch is
extracted via `.jd` (for astropy Time objects), `.value` (for Quantities), or
plain `float()` for legacy scalars.

A fourth pilot run (post-v0.87.4) returned `insufficient_observations` for all
400 candidates because PR #86 only fixed the `epoch` column. astroquery
0.4.11+ assigns `u.deg` units to `RA` and `DEC` columns and `u.mag` to `mag`
as well — `float(Quantity('90.0 deg'))` raises `TypeError` in the same
per-row `except Exception: pass` block. Fixed in v0.87.5 (PR #87): added
`_mpc_to_float()` helper dispatching `.jd` / `.value` / `float()` and
applied it to all four numeric columns. Pilot rerun pending operator execution.

### Skills

| Script | Purpose |
|---|---|
| `Skills/smoke_test.py` | Happy-path check for all modules; exits 0 on success |
| `Skills/evaluate_calibration.py` | Brier/ECE evaluation for Platt and isotonic calibrators |
| `Skills/generate_training_labels.py` | Download Tier 1 labels or build the approved four-class MPC Tier 3 pilot manifest |
| `Skills/batch_score.py` | Score a list of tracklets from a JSON file; print ranked table |
| `Skills/run_pipeline.py` | Full end-to-end pipeline run |
| `Skills/injection_recovery.py` | Injection-recovery test: injects synthetic NEOs, measures detection/link/score rates |
| `Skills/check_mpc_known.py` | Cross-match candidate observations against MPC known object catalog |
| `Skills/visualize_tracklets.py` | Plot sky positions and light curves for a tracklet JSON file |
| `Skills/export_mpc_report.py` | Export MPC 80-column reports from a scored NEO JSON file |
| `Skills/benchmark_pipeline.py` | Time classify + score on N synthetic tracklets; print throughput table |
| `Skills/train_tier1_xgboost.py` | Train Tier 1 XGBoost on ZTF alerts + MPC labels; saves `models/tier1_xgb.json`; run from Mac with `caffeinate -i` |
| `Skills/train_tier2_cnn.py` | Fine-tune CNN on labeled ZTF cutout CSV; saves `models/tier2_cnn.pt` |
| `Skills/train_tier3_transformer.py` | Train Transformer on MPC tracklet CSV; saves `models/tier3_transformer.pt` |
| `Skills/tune_linker.py` | Parametric sweep of `position_tolerance_arcsec` × `chi2_threshold` vs link/score rate |
| `Skills/background.py` | Unified background automation CLI with run, readiness, live dry-run, summary, detail, history, and signoff subcommands |
| `Skills/neo_mcp_server.py` | Project-scoped MCP guard server for bounded file reads, read-only git inspection, and fixed offline validation/readiness commands |
| `Skills/stress_test_high_motion.py` | Stress-test linker across 3 motion bins (1–10, 10–30, 30–60 arcsec/hr); saves results to `data/` |
| `Skills/build_cutout_dataset.py` | Convert ZTF alert JSON (base64 cutouts) to `.npz` + CSV index for Tier 2 CNN training |
| `Skills/build_sequence_dataset.py` | Validate five classes, create designation-grouped splits, and tokenize Tier 3 sequences |
| `Skills/fetch_alerce_artifact_sequences.py` | Acquire bounded public ALeRCE bogus-object histories for the Tier 3 artifact class |
| `Skills/run_tier3_pilot.py` | One-command, fail-closed Tier 3 pilot with commit pinning, reserve pools, resumable checkpoints, and top-level SQLite stage logs |
| `Skills/validate_mpc_report.py` | Validate MPC 80-column observation report files; CLI with `--json` flag |
| `Skills/diagnose_pipeline.py` | Run each pipeline stage with synthetic data; report pass/fail per stage |
| `Skills/compare_baselines.py` | Compare two injection-recovery JSON baselines; exits 1 on regression |
| `Skills/simulate_survey.py` | Generate synthetic ZTF-like survey observations for a sky field |
| `Skills/export_ranked_table.py` | Export a ranked ScoredNEO table to CSV or HTML |
| `Skills/check_orbit_quality.py` | Check orbit quality and fit preliminary orbit for tracklets from JSON |
| `Skills/generate_obs_schedule.py` | Generate prioritized follow-up observation schedule with urgency tiers |
| `Skills/photometric_calibration.py` | Per-field photometric zero-point fit and magnitude correction |
| `Skills/export_mpc_bulk.py` | Bulk export MPC 80-column reports for a list of ScoredNEOs to a directory |
| `Skills/filter_candidates.py` | Filter scored NEO JSON by hazard flag, alert pathway, or minimum priority |
| `Skills/summarise_run.py` | Print or JSON-export a pipeline run summary from scored NEO JSON |
| `Skills/plot_sky_coverage.py` | RA/Dec scatter plot of tracklet positions colour-coded by hazard flag |
| `Skills/export_candidate_report.py` | Per-candidate plain-text reports from scored NEO JSON; `--split` writes one file per candidate |
| `Skills/tag_neo_class.py` | Batch-tag NEO class for tracklets or ScoredNEO dicts using `classify_neo_class` from orbit.py |
| `Skills/check_tisserand.py` | Batch-compute Tisserand parameter for tracklets/ScoredNEO dicts; flags T_J < threshold as comet-like |
| `Skills/export_followup_requests.py` | Generate NEOCP follow-up request files for candidates above priority threshold; supports `--obs-code` and `--out-dir` |
| `Skills/ephemeris_check.py` | Predict sky positions for tracklets at a given JD; observer-ready RA/Dec/dist table; `--jd` and `--json` flags |
| `Skills/flag_comet_candidates.py` | Combined Tisserand + eccentricity comet-candidate flag; `--threshold`, `--min-ecc`, `--json` flags |
| `Skills/assess_survey_coverage.py` | Survey field coverage report (area, limiting mag, source count, fields per night); `--json` flag |
| `Skills/grade_tracklets.py` | Batch-grade tracklets from JSON (A/B/C/D) using arc, nights, and astrometric RMS; `--json` flag |
| `Skills/query_mpc_observations.py` | Inspect one MPC history or collect a bounded, resumable, versioned Tier 3 raw sequence dataset |
| `Skills/fetch_atlas_data.py` | Fetch ATLAS forced photometry for a sky position; `--token`, `--force-refresh`, `--json` flags |
| `Skills/plot_calibration.py` | Plot reliability diagram from scored NEO or prob/label JSON; saves PNG; prints Brier/ECE/log-loss |
| `Skills/export_survey_summary.py` | Export per-candidate detection summary from pipeline run JSON to CSV or HTML |
| `Skills/triage_candidates.py` | Urgency-sorted triage table from scored NEO JSON; `--urgency`, `--pathway`, `--json` flags |
| `Skills/validate_pipeline_run.py` | Validate pipeline run JSON for required keys, MOID plausibility, and no impact-probability phrases; `--json` flag |
| `Skills/export_atlas_lightcurve.py` | Export ATLAS forced-photometry lightcurve for a sky position; `--format png\|csv\|json`, `--out`, `--token`, `--force-refresh` flags |
| `Skills/analyze_field_detections.py` | Field-level detection statistics and mission/filter breakdowns; `--json` flag |
| `Skills/export_candidate_dossiers.py` | Export conservative per-candidate dossier files; `--out-dir`, `--json` flags |
| `Skills/fetch_recent_neos.py` | Fetch recent MPC NEO observations; `--days`, `--force-refresh`, `--json` flags |
| `Skills/export_ades_report.py` | Export MPC ADES PSV reports for scored candidates |
| `Skills/fetch_known_phas.py` | Fetch known PHA records with cache support; `--force-refresh`, `--json` flags |
| `Skills/get_top_candidates.py` | Top-N candidates by discovery priority from scored NEO JSON; `--n`, `--json` flags |

### Docs

| File | Purpose |
|---|---|
| `docs/PIPELINE_SPEC.md` | Full stage-by-stage pipeline specification |
| `docs/SCORING_MODEL.md` | Bayesian scoring model: hypotheses, priors, feature weights |
| `docs/TRAINING_GUIDE.md` | Step-by-step ML training guide: Tier 1–3 training, calibration, injection-recovery |
| `docs/DATA_SOURCES.md` | External data sources: ZTF, ATLAS, MPC, JPL Horizons, Gaia DR3 |
| `docs/API_REFERENCE.md` | Public function signatures and schema field reference for all modules |
| `docs/BACKGROUND_SEARCH_AUTOMATION.md` | Implemented one-run background automation, SQLite logs, and scheduler notes |
| `docs/ORBIT_FITTING.md` | Technical reference for orbit fitting: Gauss's method, differential correction, MOID, Tisserand parameter |
| `docs/ALERT_PROTOCOL.md` | Technical reference for alert-pathway decision tree, gate conditions, MPC submission, NEOCP monitoring, NASA PDCO notification |
| `docs/CLASSIFICATION_GUIDE.md` | Technical reference for three-tier ML classification, morphology, ensemble stacking, calibration, and conservative classification policy |
| `docs/QUALITY_METRICS.md` | Reference for all pipeline quality metrics: detection, astrometric, photometric, orbital, calibration, and hazard scoring |
| `docs/THREAT_ASSESSMENT.md` | Technical reference for threat score formula, components, interpretation guidelines, and CLI usage |
| `docs/DETECTION_GUIDE.md` | Technical reference for detect.py: RB threshold, streak detection, clustering, known-object matching, detection efficiency, DetectionSummary |
| `docs/LINKING_GUIDE.md` | Technical reference for link.py: tracklet formation, arc statistics, satellite trail rejection, deduplication, quality grades |
| `docs/FETCH_GUIDE.md` | Technical reference for fetch.py: ZTF/ATLAS/MPC/Horizons retrieval, caching, depth estimation, survey merging, filtering |
| `docs/PREPROCESS_GUIDE.md` | Technical reference for preprocess.py: difference image quality, photometry, astrometric calibration, SNR, scatter, zero-point |
| `docs/CALIBRATION_GUIDE.md` | Technical reference for calibration helpers and metrics |
| `docs/ALERT_PATHWAY_GUIDE.md` | Alert pathway helper and guardrail guide |
| `docs/SCHEMA_REFERENCE.md` | Schema model reference |

### Data

| File | Purpose |
|---|---|
| `data/sample_tracklets.json` | Two synthetic tracklets for testing batch Skills |
| `data/README.md` | Data directory documentation and format reference |
| `data/injection_recovery_baseline.json` | Injection-recovery results (n=50, seed=42): 100% detection, 62% link, 62% score |
| `data/injection_recovery_n200.json` | Injection-recovery results (n=200, seed=42): 100% detection, 100% link, 100% score |
| `data/stress_test_high_motion.json` | Stress-test results: 100% link rate across all three motion bins |
| `background/config.json` | Automated offline background automation configuration |
| `background/config.schema.json` | JSON Schema for background automation config |
| `background/live_review_policy.example.json` | Example M4 live dry-run review policy; not approved for live network by default |
| `background/live_review_policy.schema.json` | JSON Schema for live dry-run review policy |
| `background/targets.json` | Stable background automation fixture manifest |

### Coverage by Module (v0.87.0)

| Module | Coverage |
|---|---|
| `schemas.py` | 100% |
| `score.py` | 100% |
| `calibration.py` | 100% |
| `link.py` | 100% |
| `alert.py` | 100% |
| `preprocess.py` | 100% |
| `orbit.py` | 100% |
| `detect.py` | 100% |
| `classify.py` | 100% |
| `fetch.py` | 100% (ztfquery, ATLAS, astroquery.mpc, jplhorizons all mocked) |

### Remaining Operational Milestones

| Milestone | Description |
|---|---|
| 4 | Production live ZTF/ATLAS/Pan-STARRS runs with real credentials and scheduler policy |
| 5 | Trained Tier 2 CNN weights from labeled ZTF cutouts |
| 6 | Trained Tier 3 Transformer weights from multi-night MPC/ZTF sequences |
| 7 | Production ensemble calibration on fresh labeled survey data |

### Immediate Next Steps

- Sync docs and changelog after each version bump so `AGENTS.md`, `CLAUDE.md`, `README.md`, and `CHANGELOG.md` stay aligned.
- Inspect background SQLite schema status with `Skills/background.py schema-status-summary` before running operators against older logs.
- Preview background SQLite migrations with `Skills/background.py init-log-db-preview` before running `init-log-db`.
- Use `Skills/background.py schema-operations-summary` to confirm packet-decision command readiness before recording packet-linked decisions.
- Use `Skills/background.py operator-next-action` for one schema-gated conservative next-command recommendation.
- Run `Skills/background.py blueprint-compliance-summary` after background automation changes to confirm blueprint definition-of-done status.
- Persist blueprint compliance snapshots with `Skills/background.py record-blueprint-compliance-summary` after scheduled background cycles.
- Persist operator-facing operations snapshots with `Skills/background.py record-operations-snapshot` after scheduled background cycles.
- Generate internal signoff packets with `Skills/background.py latest-unsigned-signoff-packet` before recording reviewer decisions.
- Inspect persisted packet-decision readiness with `Skills/background.py signoff-packet-decision-readiness` before asking for a packet-linked decision.
- Use `Skills/background.py record-signoff-from-packet` when a reviewer is ready to report a decision from a persisted packet.
- Use `Skills/background.py internal-follow-up-disposition` after internal review to summarize signed fixture follow-ups without approving live search or external submission.
- Use `Skills/background.py live-credential-inventory --write-report Logs/reports/credential_inventory_latest.json` to review env/Keychain credential presence without printing or committing secret values.
- Collect labeled training data via `Skills/generate_training_labels.py`.
- Run credentialed live-data dry runs for ZTF/ATLAS/Pan-STARRS only when tokens and review policy are explicitly configured.
- Train and evaluate Tier 2/Tier 3 model weights on real labeled data.
- Commit `models/tier1_xgb.json` after `.gitignore` update to allow `models/*.json` is merged.

### Key Changes in v0.87.9 (T1-A CLOSED — ensemble stacker KPIs passed)

- `Skills/train_ensemble_stacker.py`: implemented and debugged end-to-end
  ensemble stacking training (PRs #97–#101). Five bugs fixed across four
  operator runs: (1) alert lookup used wrong CSV column (`filename` vs
  `cutout_path`) — fixed to use `entry_idx` from NPZ stem; (2) numpy array
  truthiness `array or fallback` — fixed with walrus operator `is not None`
  check; (3) `IsotonicCalibrator.fit()` requires numpy arrays not Python lists
  — removed `.tolist()` from `calibrator.fit/predict`; (4) KPI functions
  (`brier_score`, `compute_roc_auc`, etc.) use numpy arithmetic — removed
  `.tolist()` from all KPI calls; (5) binary KPI evaluation included MPC
  samples with T2=uniform, suppressing AUC — fixed to evaluate only on
  ZTF-origin samples (source="ztf") where both T1 and T2 features are real.
- `build_stacking_dataset` now returns a `sources` list ("ztf"/"mpc"/
  "synthetic") per sample; `evaluate_stacker_kpis` accepts `sources_val` and
  filters to ZTF-origin samples for binary calibration evaluation.
- Ensemble stacker KPI results (2026-06-14, operator run, 10s total):
  AUC=0.9809, Brier=0.0211, ECE=0.0000, Log-loss=0.0761, CV ECE
  mean=0.0247, Bootstrap Brier CI upper=0.0330, Bootstrap ECE CI upper=0.0225
  — all 7 KPIs PASS; `promotion_gate_passed=true` on 394 ZTF val samples.
- `docs/PRODUCTION_READINESS.md`: T1-A step 12 marked DONE; T1-A status
  updated to CLOSED; checklist rows updated to [x].
- 3528 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.87.9.

### Key Changes in v0.87.7 (T1-D calibration KPI gate passed)

- `Skills/evaluate_calibration.py`: fixed series of macOS PyTorch deadlocks
  that caused the CNN section to hang indefinitely (PRs #91–#95):
  - **BytesIO pre-read** (PR #91): torch.load on a file path uses mmap and
    returns 0.0s but defers byte reads to load_state_dict, blocking on
    Dropbox-backed files. Fixed by reading into BytesIO in 64KB chunks with
    per-chunk ETA before any torch call.
  - **Matmul warmup** (PR #93): first ATen tensor compute in a new process
    triggers Accelerate/BLAS lazy init (~20s). Fixed with dummy 256×256 matmul
    warmup before load_state_dict.
  - **Conv2d warmup** (PR #94): matmul warmup only activates BLAS paths;
    conv2d dispatches through a separate route (FBGEMM/oneDNN) that lazy-
    compiles on first call. Fixed with dummy 1×1×63×63 CNN forward pass.
  - **Thread-pool deadlock** (PR #95): ATen thread-pool spawn deadlocks on
    macOS when OMP_NUM_THREADS is unconstrained. Fixed by setting
    OMP_NUM_THREADS=1 and MKL_NUM_THREADS=1 via os.environ before import
    torch, and calling torch.set_num_threads(1) immediately after import.
  - **Heartbeats** on all blocking calls (matmul warmup, conv warmup,
    per-batch forward pass) so no call is ever silent.
- T1-D calibration KPI gate results (2026-06-14, operator run, 24s total):
  - Tier 1 XGBoost (Isotonic): Brier=0.0000, ECE=0.0000, Log-loss=0.0004,
    ROC AUC=1.0000 — all 7 KPIs PASS.
  - Tier 2 CNN (Isotonic): Brier=0.0462, ECE=0.0132, Log-loss=0.2398,
    ROC AUC=0.9593 — all 7 KPIs PASS.
  - `promotion_gate_passed=true`; report at `Logs/reports/calibration_report.json`.
- `CLAUDE.md` Standing Rules hardened (PR #92): four new rules to prevent
  symptom-loop debugging (diagnose root cause before writing code; physically
  impossible output is a diagnostic signal; failed fix → re-diagnose; state
  predicted output before submitting PR). ETA rule updated to require
  measurable-quantity ETA; elapsed-only heartbeats explicitly prohibited.
- `docs/PRODUCTION_READINESS.md`: T1-D marked CLOSED; checklist updated;
  T1-A progress updated to reflect calibration gate passed.
- 3511 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.87.7.

### Key Changes in v0.87.6 (ALeRCE progress output; Tier 3 training complete)

- `Skills/fetch_alerce_artifact_sequences.py`: Added `_print_progress()` helper
  with elapsed time and ETA emitted to stderr after every OID in both sequential
  and parallel acquisition paths. The ALeRCE stage had zero print statements —
  a violation of the standing rule requiring live progress on all long-running
  scripts — making it appear frozen to operators.
- Tier 3 Transformer (operator run, 2026-06-13): Fifth pilot run succeeded.
  MPC collected 50 sequences per class in 3m49s (200 total); ALeRCE collected
  50 stellar_artifact sequences (329 observations). Training on the five-class
  pilot splits: best epoch 17/30, val_macro_f1=0.9400, val_loss=0.2492. Weights
  saved at `models/tier3_transformer.pt` (operator Mac).
- `docs/PRODUCTION_READINESS.md`: Tier 3 row updated to DONE; checklist items 7
  and 9 marked done; T1-A progress block updated.
- 3511 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.87.6.

### Key Changes in v0.87.5 (astropy Quantity all-columns fix)

- `src/fetch.py`: `fetch_mpc_observations` — astroquery 0.4.11+ assigns units
  to ALL four numeric columns: `epoch→u.d`, `RA→u.deg`, `DEC→u.deg`,
  `mag→u.mag`. PR #86 fixed `epoch` only; `float(Quantity('90.0 deg'))` still
  raised `TypeError` for RA, DEC, and mag, silently discarded per-row, causing
  all 400 fourth-pilot candidates to return `insufficient_observations`.
  Fix: added `_mpc_to_float(val)` helper (dispatches `.jd` / `.value` /
  `float()`) and replaced all four `float(...)` column extractions with it.
- `tests/test_fetch.py`: 2 new tests — `test_all_columns_as_quantities`
  (epoch, RA, DEC, mag all as Quantities — the exact astroquery 0.4.11+ case)
  and `test_ra_dec_as_quantities` (RA/DEC as Quantities, plain float epoch).
- 3511 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.87.5.

### Key Changes in v0.87.4 (astropy Quantity epoch fix)

- `src/fetch.py`: `fetch_mpc_observations` — `MPC.get_observations()` now
  returns epoch as `astropy.Quantity(value, unit='d')` in newer astroquery.
  `float(dimensioned_Quantity)` raises `TypeError`; silently caught inside the
  row-parsing `try/except`, discarding every observation for every designation.
  This was the root cause of all 400 pilot candidates returning
  `insufficient_observations` on the third pilot run. Fix: dispatch on
  `hasattr(epoch_val, "jd")` → `.jd`, `hasattr(epoch_val, "value")` → `.value`,
  else plain `float()`. (PR #86)
- `src/alert.py`: split compound `if obs is not None and hasattr(...) and len(...)` into
  nested `if` statements to eliminate Python 3.14.6 intermittent branch-coverage
  miss in `validate_alert_package`.
- `tests/test_fetch.py`: 2 new tests — `test_epoch_as_astropy_quantity_value`
  and `test_epoch_as_astropy_time_jd` — covering both epoch dispatch branches.
- 3509 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.87.4.

### Key Changes in v0.87.3 (designation unpacking)

- `Skills/generate_training_labels.py`: `_unpack_designation()` — added branch
  for extended packed numbers (asteroids ≥100000): 5-char strings with leading
  letter and 4 digits (e.g. `A0004` → `100004`, `Z9999` → `359999`, `a0001`
  → `360001`). This was the root cause of all 400 pilot candidates returning
  zero MPC observations on the second pilot run.
- `src/alert.py`: converted remaining `elif` to independent `if` in
  `validate_alert_package` to fix Python 3.14.6 branch-coverage miss.
- `tests/test_tier3_pilot.py`: 7 new regression tests covering all three packed
  formats and end-to-end designation parse.
- 3507 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.87.3.

### Key Changes in v0.87.2 (pilot robustness)

- `src/fetch.py`: `fetch_mpc_observations` — added `None`-table guard (MPC returns `None`
  for unknown designations; was causing `TypeError` treated as provider failure); added
  `_INFRA_ERRORS` tuple to distinguish infrastructure failures (`ConnectionError`,
  `TimeoutError`, `OSError`) from query-level errors; query-level errors now return `[]`
  regardless of `raise_on_error` so they are classified as `insufficient_observations`
  rather than `query_error` and do not feed the circuit breaker.
- `src/alert.py`: two remaining `elif` chains in `validate_alert_package` converted to
  independent `if` statements to fix Python 3.14.5 branch-coverage miss.
- `Skills/query_mpc_observations.py`: parallel circuit-breaker effective threshold raised
  to `max_consecutive_query_errors + (workers - 1)` to compensate for `as_completed()`
  ordering bias; error messages now include failing designation names and error types.
- `tests/test_fetch.py`: 4 new tests covering None-table, query-level non-raise, and
  infrastructure-raise behaviour in `fetch_mpc_observations`.
- `tests/test_sequence_acquisition.py`: 2 new tests covering parallel threshold scaling
  and diagnostic message content.
- 3500 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.87.2.

### Key Changes in v0.87.1 (training milestone)

- `Skills/train_tier1_xgboost.py`: new — trains 5-class XGBoost on ZTF labeled alerts (rb/drb features) + MPC NEO/MBA catalog labels; 80/20 stratified val split; inverse-frequency class weights; saves `models/tier1_xgb.json`; auto-loaded by `classify._load_xgb_model`.
- `.gitignore`: added `!models/*.json` to allow `models/tier1_xgb.json` to be committed alongside `models/tier2_cnn.pt`.
- `docs/PRODUCTION_READINESS.md`: T1-A step 8 marked DONE; step 9 added (commit model JSON); checklist updated (Tier 1 XGBoost ✓).
- Tier 1 XGBoost training results: val_acc=99.95%, macro AUC=1.000, 11,100 examples (8,588 ZTF real + 1,412 ZTF bogus + 500 MPC NEO + 500 MPC MBA + 100 synthetic minor-class), 300 estimators, max_depth=5.

### Key Changes in v0.87.0

- `schemas.py`: added `SurveyNightRecord` — frozen model: night_jd, survey, n_obs, n_tracklets, limiting_mag, area_sq_deg.
- `fetch.py`: added `compute_observation_time_span(fetch_result)` — max JD − min JD across valid alerts; None for fewer than 2 finite JDs.
- `preprocess.py`: added `compute_cutout_dynamic_range(obs)` — max minus min pixel value in float32 difference cutout; None if absent or empty.
- `detect.py`: added `compute_detection_gap_days(result)` — max JD gap between consecutive candidate detections; None for fewer than 2 candidates.
- `link.py`: added `compute_inter_night_motion(tracklet)` — mean angular displacement between consecutive distinct nights in arcsec/night; None for fewer than 2 distinct nights.
- `classify.py`: added `compute_classification_entropy_summary(neos)` — dict: mean_entropy, std_entropy, min_entropy, max_entropy across scored NEOs; empty dict if none.
- `orbit.py`: added `compute_mean_longitude(elements)` — mean longitude λ = Ω + ω + M₀ (mod 360°); None for missing attributes.
- `score.py`: added `compute_batch_priority_stats(neos)` — dict: mean, std, min, max of discovery_priority; empty dict if no valid priorities.
- `alert.py`: added `format_alert_pathway_summary(neos)` — multi-line text block with pathway counts and fractions sorted by frequency.
- `calibration.py`: added `compute_negative_predictive_value(probs, labels, threshold=0.5)` — NPV = TN/(TN+FN); 0.0 for empty input or no negative predictions.
- 3475 tests passing; 100% coverage target maintained; ruff + mypy clean.
- Version bumped to 0.87.0.

### Key Changes in v0.86.0

- `schemas.py`: added `NightObservationSummary` — frozen model: night_jd, n_obs, n_candidates, mean_rb, limiting_mag, survey.
- `fetch.py`: added `get_faintest_observation(fetch_result)` — Observation with highest valid magnitude (< 90); None if no valid alerts.
- `preprocess.py`: added `compute_photometric_noise_level(observations)` — MAD of valid observation magnitudes; None for fewer than 2 valid mags.
- `detect.py`: added `compute_candidate_sky_density(result, field_radius_deg)` — candidates per square degree using solid-angle formula; 0.0 for empty or non-positive radius.
- `link.py`: added `compute_max_observation_gap(tracklet)` — maximum gap in days between consecutive observations sorted by JD; None for fewer than 2 observations.
- `classify.py`: added `get_highest_confidence_neo(neos)` — ScoredNEO with highest posterior neo_candidate probability; None if list is empty.
- `orbit.py`: added `compute_orbit_complexity(elements)` — scalar complexity index [0, 1]: 0.5×min(e,1) + 0.5×min(|i|,90)/90; 0.0 for missing attributes.
- `score.py`: added `compute_candidate_priority_spread(neos)` — standard deviation of discovery_priority values; 0.0 for fewer than 2 valid priorities.
- `alert.py`: added `count_ready_for_submission(neos)` — count of candidates passing the ready_for_submission gate.
- `calibration.py`: added `compute_positive_predictive_value(probs, labels, threshold=0.5)` — PPV = TP/(TP+FP); 0.0 for empty input or no positive predictions.
- 3420 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.86.0.

### Key Changes in v0.85.0

- `schemas.py`: added `ScoredNEOBatch` — frozen model: batch_id, pipeline_version, created_at_jd, n_candidates.
- `fetch.py`: added `get_latest_observation(fetch_result)` — Observation with highest JD; None if no valid alerts.
- `preprocess.py`: added `compute_cutout_fill_fraction(obs)` — fraction of non-zero pixels in difference-image float32 cutout; None if absent or decode error.
- `detect.py`: added `compute_mean_motion_rate(result)` — mean apparent motion rate (arcsec/hr) across all candidates; None if empty.
- `link.py`: added `compute_arc_coverage_fraction(tracklet, survey_window_days)` — arc_days / survey_window, clamped [0, 1].
- `classify.py`: added `compute_composite_neo_score(features)` — weighted composite of real_bogus (0.35), arc_coverage (0.25), nights_observed (0.25), orbit_quality (0.15); [0, 1].
- `orbit.py`: added `compute_specific_angular_momentum(elements)` — h = sqrt(GM·a·(1−e²)) in AU² yr⁻¹; None for invalid/hyperbolic orbits.
- `score.py`: added `compute_weighted_hazard_index(neo)` — composite: 0.4×threat + 0.3×MOID_proximity + 0.3×orbit_quality; [0, 1].
- `alert.py`: added `format_neo_summary_table(neos, max_rows=20)` — plain-text ASCII ranked table with header, separator, and data rows.
- `calibration.py`: added `compute_sharpness(probs)` — mean squared deviation from 0.5; [0, 0.25]; 0.25 = perfectly sharp.
- 3367 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.85.0.

### Key Changes in v0.84.0

- `schemas.py`: added `AlertSummaryRecord` — frozen model: neo_id, alert_pathway, hazard_flag, discovery_priority, moid_au, submitted_at_jd.
- `fetch.py`: added `get_brightest_observation(fetch_result)` — return Observation with lowest mag (< 90); None if none.
- `preprocess.py`: added `compute_image_rms(obs)` — RMS pixel value of difference-image float32 cutout; None if absent or decode error.
- `detect.py`: added `get_brightest_candidate(result)` — RawCandidate containing the observation with the smallest valid magnitude.
- `link.py`: added `compute_position_angle_dispersion(tracklet)` — std dev of consecutive pair position angles in degrees; 0.0 for exactly 2 obs.
- `classify.py`: added `compute_mean_neo_probability(neos)` — mean posterior neo_candidate probability across scored NEOs; None if no valid posteriors.
- `orbit.py`: added `compute_aphelion_velocity(elements)` — speed at aphelion in km/s via vis-viva equation; None for invalid/hyperbolic orbits.
- `score.py`: added `count_by_alert_pathway(neos)` — dict[pathway → count] across all scored NEOs.
- `alert.py`: added `format_candidate_summary_line(neo)` — compact single-line summary with ID, pathway, hazard flag, priority, MOID.
- `calibration.py`: added `compute_calibration_spread(probs, labels, n_bins=10)` — std dev of per-bin calibration errors; 0.0 for < 2 non-empty bins.
- 3309 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.84.0.

### Key Changes in v0.83.0

- `schemas.py`: added `FieldCoverageReport` — frozen model: field_id, ra_deg, dec_deg, area_sq_deg, n_obs, n_tracklets, limiting_mag, pipeline_version.
- `fetch.py`: added `count_observations_by_filter(fetch_result)` — dict[filter_band → count] across all alerts.
- `preprocess.py`: added `compute_cutout_contrast_ratio(obs)` — peak/median pixel ratio in difference cutout; None if absent or median zero.
- `detect.py`: added `count_candidates_above_rb(result, threshold=0.65)` — count of candidates with max real_bogus ≥ threshold.
- `link.py`: added `compute_tracklet_span_nights(tracklet)` — number of distinct integer nights spanned.
- `classify.py`: added `count_by_dominant_hypothesis(neos)` — dict[hypothesis → count] across scored NEOs.
- `orbit.py`: added `compute_perihelion_velocity(elements)` — speed at perihelion in km/s via vis-viva.
- `score.py`: added `compute_pha_fraction(neos)` — fraction of candidates flagged pha_candidate.
- `alert.py`: added `validate_obs_code(obs_code)` — (bool, str) validity check on MPC obs code format.
- `calibration.py`: added `compute_fraction_calibrated(probs, labels, threshold=0.1, n_bins=10)` — fraction of bins within threshold of perfect calibration.
- 3251 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.83.0.

### Key Changes in v0.82.0

- `schemas.py`: added `ObservationQualityReport` — frozen model: field_id, epoch_jd, n_obs, mean_snr, mean_fwhm_arcsec, n_saturated, limiting_mag.
- `fetch.py`: added `group_observations_by_night(fetch_result)` — dict[int_jd → list[Observation]] grouped by floor(jd); skips non-finite JDs.
- `preprocess.py`: added `compute_cutout_peak_value(obs)` — peak pixel value in difference cutout; None if no cutout or decode error.
- `detect.py`: added `compute_rb_score_distribution(result, n_bins=10)` — equal-width histogram of max RB scores per candidate; excludes None scores.
- `link.py`: added `estimate_observation_cadence(tracklet)` — mean inter-observation time in hours; None for <2 obs.
- `classify.py`: added `filter_by_neo_probability(neos, min_prob=0.5)` — filter ScoredNEOs by posterior neo_candidate probability.
- `orbit.py`: added `compute_argument_of_perihelion_rate(elements)` — secular ω precession rate in deg/yr from solar J2 perturbation.
- `score.py`: added `get_top_candidates(neos, n=10)` — top-N ScoredNEOs by discovery_priority descending.
- `alert.py`: added `count_submissions_by_pathway(neos)` — dict[pathway → count] for candidates passing ready_for_submission gate.
- `calibration.py`: added `compute_calibration_resolution(probs, labels, n_bins=10)` — normalized resolution score [0, 1] measuring class separation.
- 3189 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.82.0.

### Key Changes in v0.81.0

- `schemas.py`: added `PipelineHealthReport` — frozen model for pipeline health snapshot (n_modules_tested, coverage_pct, lint_clean, mypy_clean, test_count, pipeline_version).
- `fetch.py`: added `compute_magnitude_distribution(fetch_result, n_bins=10)` — equal-width histogram of alert magnitudes (bin_edges, counts, n_total); excludes sentinel mags ≥ 90.
- `preprocess.py`: added `compute_cutout_noise_level(obs)` — std dev of difference-image float32 pixels; None if no valid cutout.
- `detect.py`: added `filter_by_streak_score(result, min_streak_score=0.5)` — return new DetectResult keeping candidates where max compute_streak_metric ≥ threshold.
- `link.py`: added `compute_field_tracklet_density(tracklets, field_radius_deg)` — tracklets per sq-deg for a circular field using solid-angle formula.
- `classify.py`: added `batch_dominant_hypothesis(neos)` — list of {object_id, hypothesis, probability} dicts for each scored NEO.
- `orbit.py`: added `compute_longitude_ascending_node_rate(elements)` — secular nodal precession rate in deg/yr from solar J2 perturbation.
- `score.py`: added `filter_by_discovery_priority(neos, min_priority=0.5)` — list of ScoredNEOs with discovery_priority ≥ threshold.
- `alert.py`: added `format_complete_mpc_submission(neo, obs_code)` — complete paste-ready MPC submission (header + blank line + 80-col obs block).
- `calibration.py`: added `compute_max_calibration_error(probs, labels, n_bins=10)` — MCE: maximum bin-wise |mean_prob − fraction_positive|.
- 3128 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.81.0.

### Key Changes in v0.60.0

- `background.py`: added `background_operator_next_action_summary(config_path, db_path, input_path)` to schema-gate the operator workflow and recommend the next conservative local command.
- `Skills/background.py`: added `operator-next-action` for machine-readable next-command triage.
- The operator summary blocks on incomplete SQLite schemas before consulting operations snapshots, includes packet-decision readiness for current schemas, and preserves no-network/no-external-submission guardrails.
- 3 new tests (2123 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.60.0.

### Key Changes in v0.59.0

- `background.py`: added `background_schema_operations_summary(db_path)` to combine schema status, migration preview, packet-decision command readiness, and the next safe operator action.
- `Skills/background.py`: added `schema-operations-summary` for read-only schema operations triage.
- The operations summary reports whether packet-decision commands are ready and recommends `init-log-db` only when the current SQLite schema is incomplete.
- 4 new tests (2120 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.59.0.

### Key Changes in v0.58.0

- `background.py`: added `background_schema_migration_preview(db_path)` to preview additive SQLite log migration effects without creating or changing a database.
- `Skills/background.py`: added `init-log-db-preview` for no-write operator review before running `init-log-db`.
- Migration preview reports missing tables, would-create tables, current schema state, the init command, and guardrail flags while preserving no-network, no-external-submission, no-signoff, no-packet, and no-report-write behavior.
- 4 new tests (2116 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.58.0.

### Key Changes in v0.57.0

- `background.py`: added `background_schema_status_summary(db_path)` for read-only inspection of expected top-level SQLite log tables.
- `background.py`: added `migrate_background_log_db(db_path)` to run the additive `init_log_db` migration and report before/after schema state.
- `Skills/background.py`: added `schema-status-summary` and `init-log-db` subcommands.
- Schema inspection and migration reports explicitly preserve the no-network, no-external-submission, no-signoff, no-packet, and no-report-write guardrails.
- 4 new tests (2112 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.57.0.

### Key Changes in v0.56.0

- `background.py`: added `signoff_packet_decision_readiness(db_path)` and `latest_undecided_signoff_packet(db_path)` for no-network review of persisted packets that still need packet-linked decisions.
- `Skills/background.py`: added `signoff-packet-decision-readiness` and `latest-undecided-signoff-packet` subcommands.
- Packet-decision readiness now reports ready, blocked, signed, and already decided packet states without recording a signoff, writing a packet, or enabling live/external action.
- 5 new tests (2108 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.56.0.

### Key Changes in v0.55.0

- `background.py`: added `record_signoff_from_packet(...)` and `signoff_packet_decision_summary(db_path)` to record reviewer decisions from persisted internal signoff packets.
- `Skills/background.py`: added `record-signoff-from-packet` and `signoff-packet-decision-summary` subcommands.
- `init_log_db`: added top-level SQLite table `signoff_packet_decision_log` for packet-linked reviewer decisions and resulting operations snapshots.
- Packet-based decisions validate the packet, unsigned follow-up state, and target/run match before writing a normal human signoff plus decision audit row. Each packet decision also records a post-decision operations snapshot while keeping network access and external submission disabled.
- 5 new tests (2103 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.55.0.

### Key Changes in v0.54.0

- `background.py`: added `signoff_packet(run_id, db_path)`, `latest_unsigned_signoff_packet(db_path)`, `write_signoff_packet(...)`, `record_signoff_packet(...)`, and `signoff_packet_log_summary(db_path)` for internal human-review packets that do not record signoff decisions.
- `Skills/background.py`: added `signoff-packet`, `latest-unsigned-signoff-packet`, `write-signoff-packet`, `record-signoff-packet`, and `signoff-packet-log-summary` subcommands.
- `init_log_db`: added top-level SQLite table `signoff_packet_log` for persisted signoff packet metadata.
- 5 new tests (2098 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.54.0.

### Key Changes in v0.53.0

- `background.py`: added `background_operations_snapshot(config_path, db_path, input_path)`, `record_background_operations_snapshot(...)`, and `background_operations_snapshot_log_summary(db_path)` to aggregate and persist conservative operator-facing background status snapshots.
- `Skills/background.py`: added `operations-snapshot`, `record-operations-snapshot`, and `operations-snapshot-log-summary` subcommands.
- `validation_summary`: now exposes `total_follow_up` directly for aggregate operation-state consumers.
- 4 new tests (2093 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.53.0.

### Key Changes in v0.52.0

- `background.py`: added `record_blueprint_compliance_summary(db_path, input_path)` and `blueprint_compliance_log_summary(db_path)` to persist background blueprint compliance snapshots in top-level SQLite logs.
- `Skills/background.py`: added `record-blueprint-compliance-summary` and `blueprint-compliance-log-summary` subcommands.
- 3 new tests (2089 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.52.0.

### Key Changes in v0.51.0

- `background.py`: added `background_blueprint_compliance_summary(db_path, input_path)` to audit background automation against `BACKGROUND_SEARCH_AUTOMATION_BLUEPRINT.md`.
- `Skills/background.py`: added `blueprint-compliance-summary` subcommand.
- Follow-up report drafts now explicitly include uncertainty language alongside negative evidence and limitations.
- 3 new tests (2086 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.51.0.

### Key Changes in v0.50.0

- Added 10 public APIs across alert, calibration, classify, detect, fetch, link, orbit, preprocess, schemas, and score modules.
- 2083 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.50.0.

### Key Changes in v0.49.0

- Added 10 public APIs for mission counts, calibration error, class probability ranges, angular separation, field overlap, tracklet completeness, orbital arc quality, cutout peak positions, and hazard summaries.
- Version bumped to 0.49.0.

### Key Changes in v0.48.0

- Added 10 public APIs for NEOCP submission formatting, calibration uniformity, posterior stability, variability, MPC orbit catalogs, sky density, Earth Tisserand parameter, compactness, tracklet clusters, and weighted risk.
- Version bumped to 0.48.0.

### Key Changes in v0.47.0

- Added 10 public APIs for discovery reports, calibration drift, Tier 1 confidence, brightness trends, NEOCP confirmations, motion summaries, aphelion distance, PSF asymmetry, night summaries, and survey completeness.
- Version bumped to 0.47.0.

### Key Changes in v0.46.0

- Added 10 public APIs for ADES PSV export, reliability, posterior update, field source counts, known NEO lists, tracklet arc nights, perihelion distance, radial profiles, observation coverage, and priority ranks.
- Version bumped to 0.46.0.

### Key Changes in v0.45.0

- Added 10 public APIs for observation logs, expected positive rate, NEO class distribution, cadence, MPC orbit elements, motion-rate filtering, orbital velocity, streak angle, residual summaries, and hazard grades.
- Version bumped to 0.45.0.

### Key Changes in v0.44.0

- Added 10 public APIs for alert age, resolution score, class entropy summary, detection gaps, NEOCP objects, inter-night gaps, mean anomaly at JD, cutout symmetry, astrometric residuals, and weighted hazard scoring.
- Version bumped to 0.44.0.

### Key Changes in v0.43.0

- Added 10 public APIs for ready-to-submit counts, discrimination, Tier 1 score distributions, angular velocity, known NEO ephemerides, velocity dispersion, inclination class, image gradients, observation clusters, and arc-quality bonuses.
- Version bumped to 0.43.0.

### Key Changes in v0.42.0

- Added 10 public APIs for bulk summaries, Brier skill score, class entropy stats, streak density, field completeness, night span, longitude of perihelion, cutout contrast, ephemeris points, and weighted priority.
- Version bumped to 0.42.0.

### Key Changes in v0.41.0

- Added 10 public APIs for alert-flag counts, calibration sharpness, batch morphology, magnitude filtering, recent MPC NEO retrieval, tracklet quality, mean motion, pixel histograms, survey statistics, and combined priority.
- Version bumped to 0.41.0.

### Key Changes in v0.40.0

- Added 10 public APIs for true anomaly, observation depth, position-angle consistency, calibration gain, close-approach scoring, candidate dossiers, Pan-STARRS moving objects, background level, candidate reports, and average precision.
- Version bumped to 0.40.0.

### Key Changes in v0.39.0

- Added 10 public APIs for eccentric anomaly, source extent, great-circle residuals, confusion matrices, size estimates, follow-up windows, CSS alerts, cutout entropy, orbital summaries, and F1 score.
- Version bumped to 0.39.0.

### Key Changes in v0.38.0

- `background.py`: added `record_live_dry_run_operator_handoff(config_path, db_path, report_dir)` and `live_dry_run_operator_handoff_log_summary(db_path)` to write operator handoffs and persist them in top-level SQLite logs.
- `Skills/background.py`: added `record-live-dry-run-operator-handoff` and `live-dry-run-operator-handoff-log-summary` subcommands.
- 3 new tests (1361 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.38.0.

### Key Changes in v0.37.0

- `background.py`: added `live_dry_run_operator_handoff(config_path)` and `write_live_dry_run_operator_handoff(config_path, report_dir)` to render a conservative no-network Markdown handoff for operator review.
- `Skills/background.py`: added `live-dry-run-operator-handoff` and `write-live-dry-run-operator-handoff` subcommands.
- 4 new tests (1358 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.37.0.

### Key Changes in v0.36.0

- `background.py`: added `record_live_dry_run_approval_bundle(config_path, db_path)` and `live_dry_run_approval_bundle_log_summary(db_path)` to persist no-network approval-bundle reviews in top-level SQLite logs.
- `Skills/background.py`: added `record-live-dry-run-approval-bundle` and `live-dry-run-approval-bundle-log-summary` subcommands.
- 3 new tests (1354 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.36.0.

### Key Changes in v0.35.0

- `background.py`: added `live_dry_run_approval_bundle(config_path)` to aggregate scheduler readiness, policy contract validation, provider readiness, dry-run planning, and blocker status into one no-network review object.
- `Skills/background.py`: added `live-dry-run-approval-bundle` for operator review before any mock live dry-run execution attempt.
- 3 new tests (1351 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.35.0.

### Key Changes in v0.34.0

- `Skills/background.py`: added `live-provider-readiness-summary` to expose no-network provider readiness from the unified CLI.
- CLI coverage now checks default blocked provider output and approved temp-config readiness with credentials.
- 1 new test (1348 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.34.0.

### Key Changes in v0.33.0

- `Skills/background.py`: added `live-policy-contract-summary` to expose no-network live review policy contract validation from the unified CLI.
- CLI coverage now checks both a valid default policy contract and an unsafe policy that allows external submission.
- 1 new test (1347 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.33.0.

### Key Changes in v0.32.0

- `background.py`: added `live_policy_contract_summary(config_path)` for no-network validation of the live review policy file and schema contract.
- `automation_readiness_summary` and `live_dry_run_plan`: now include live review policy contract status and report `LIVE_REVIEW_POLICY_CONTRACT_INVALID` for structural policy failures.
- The intentionally unapproved example policy remains contract-valid, while unsafe policies that allow external submission or omit required files are blocked before any live action.
- 3 new tests (1346 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.32.0.

### Key Changes in v0.31.0

- `background.py`: added `live_provider_capabilities()` and `live_provider_readiness(config_path)` for no-network provider-specific M4 readiness checks.
- `automation_readiness_summary` and `live_dry_run_plan`: now include provider-by-provider credential, policy, rate-limit, and submission-safety readiness details.
- Live mode now reports `LIVE_PROVIDER_NOT_READY` when any provider has missing credentials, policy approval gaps, unsupported live queries, submission capability, or insufficient rate-limit policy.
- 3 new tests (1343 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.31.0.

### Key Changes in v0.30.0

- `background.py`: added `LiveDryRunProvider` and `MockLiveDryRunProvider` for injected no-network survey dry-run probes.
- `live_dry_run_execute` and `record_live_execution_attempt`: now accept an optional provider map, aggregate per-survey query results, and report missing providers.
- Provider results are rejected if they claim network access or external submission, preserving the M4 no-submission guardrail.
- 2 new tests (1340 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.30.0.

### Key Changes in v0.29.0

- `background.py`: added `live_dry_run_execute(config_path)`, `record_live_execution_attempt(config_path, db_path)`, and `live_execution_log_summary(db_path)`.
- `init_log_db`: added top-level SQLite table `live_execution_log` for auditable dry-run execution attempts.
- `Skills/background.py`: added `live-dry-run-execute` and `live-execution-log-summary` subcommands.
- Live dry-run execution remains mock-only: no network access is performed and external submission remains disabled.
- 2 new tests (1338 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.29.0.

### Key Changes in v0.28.0

- `background.py`: added `live_dry_run_plan(config_path)`, `record_live_dry_run_plan(config_path, db_path)`, and `live_dry_run_plan_log_summary(db_path)`.
- `background/live_review_policy.example.json` and `background/live_review_policy.schema.json`: added a formal live review policy contract for M4 dry-run approval.
- `background/config.json`: requires `ATLAS_TOKEN` for ATLAS dry-run readiness, treats public ZTF/Pan-STARRS as no-credential by default, and points to the example review policy.
- `Skills/background.py`: added `live-dry-run-plan`, `record-live-dry-run-plan`, and `live-dry-run-plan-log-summary` subcommands.
- `automation_readiness_summary`: now validates live review policy fields and reports policy-specific blockers before any network access.
- 1 new test (1336 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.28.0.

### Key Changes in v0.27.0

- `background.py`: added `automation_readiness_log_summary(db_path)` and `record_automation_readiness(config_path, db_path)`.
- `init_log_db`: added top-level SQLite table `automation_readiness_log` for scheduler/live-readiness snapshots.
- `Skills/background.py`: added `record-automation-readiness` and `automation-readiness-log-summary` subcommands.
- `docs/BACKGROUND_SEARCH_AUTOMATION.md` and `docs/API_REFERENCE.md`: documented persisted readiness checks and new CLI/API entries.
- 2 new tests (1335 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.27.0.

### Key Changes in v0.26.0

- `schemas.py`: `BackgroundRunMode` now supports `automated`; `BackgroundConfig` added scheduler readiness fields, live review policy, and required credential environment variable names.
- `background.py`: added `automation_readiness_summary(config_path)` and `launchd_plist(config_path)`; live network mode now reports explicit blockers before any network action.
- `Skills/background.py`: added `automation-readiness` and `launchd-plist` subcommands.
- `background/config.json`: default mode is automated offline scheduling with live network disabled and required credential names declared.
- `docs/BACKGROUND_SEARCH_AUTOMATION.md`: updated scheduler guidance for automated offline runs and macOS launchd template generation.
- 4 new tests (1333 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.26.0.

### Key Changes in v0.25.0

- `orbit.py`: added `compute_perihelion_date(elements)` — next perihelion passage JD from mean anomaly and orbital period; None for hyperbolic/parabolic orbits or non-positive period.
- `detect.py`: added `flag_moving_sources(observations, min_rate_arcsec_hr)` — return observations with apparent motion rate ≥ threshold; uses `compute_motion_vector` pairwise; cosine-Dec-corrected.
- `link.py`: added `validate_tracklet(tracklet)` — (bool, reasons) tuple checking ≥2 obs, non-negative arc/rate, sorted JDs, no duplicate obs_ids.
- `classify.py`: added `compute_artifact_probability(features)` — log-score artifact probability [0, 1] using stellar_artifact_score, psf_quality_score, real_bogus_score, streak_score, motion_consistency_score.
- `score.py`: added `compute_observation_priority(neo)` — [0, 1] urgency score weighting last-observation gap (0.3), discovery_priority (0.4), and orbit uncertainty (0.3).
- `alert.py`: added `validate_alert_package(package)` — (bool, issues) tuple enforcing required keys, non-empty observations, valid alert_pathway, and guardrail_statement containing "NOT".
- `fetch.py`: added `fetch_panstarrs_catalog(ra_deg, dec_deg, radius_deg, epoch_jd, force_refresh)` — PanSTARRS DR2 cone search via astroquery.mast; disk-cached; returns list[Observation].
- `preprocess.py`: added `compute_difference_image_snr(obs)` — peak-to-background RMS SNR from 63×63 difference-image cutout; None if no cutout or zero background.
- `schemas.py`: added `AlertPackage` — frozen model: neo_id, alert_pathway, moid_au, observations, submission_timestamp_jd, guardrail_statement.
- `calibration.py`: added `compute_precision_recall_curve(probs, labels)` — PR curve dict with precisions, recalls, thresholds, average_precision; anchored at (recall=0, precision=1) for correct AP.
- `Skills/validate_pipeline_run.py`: new — validate pipeline run JSON for required keys, MOID plausibility [0, 10] AU, no impact-probability phrases, valid pathways; exits 0/1; `--json` flag.
- `Skills/export_atlas_lightcurve.py`: new — ATLAS forced-photometry lightcurve export; `--format png|csv|json`, `--out`, `--token`, `--force-refresh` flags.
- `docs/PREPROCESS_GUIDE.md`: new — technical reference for preprocess.py: difference image quality, photometry, astrometric calibration, SNR, scatter, zero-point.
- 87 new tests (1329 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.25.0.

### Key Changes in v0.24.0

- `orbit.py`: added `compute_absolute_magnitude(observed_mag, r_au, delta_au, phase_deg, g=0.15)` — inverse IAU HG phase function; returns H from apparent magnitude, distances, and phase angle; NaN for degenerate geometry.
- `detect.py`: added `compute_motion_vector(obs1, obs2)` — dict with dra_arcsec_hr, ddec_arcsec_hr, rate_arcsec_hr, pa_deg; cosine-Dec-corrected; zero vector for identical JDs.
- `link.py`: added `merge_overlapping_tracklets(tracklets)` — union-find merge of tracklets sharing ≥1 obs_id; picks longest-arc representative; deduplicates and recomputes arc_days.
- `classify.py`: added `compute_neo_probability(features)` — log-score model probability for neo_candidate hypothesis vs all others; uses CLAUDE.md feature weights; [0, 1].
- `score.py`: added `compute_discovery_score(neo)` — weighted combination of discovery_priority (0.5), orbit_quality_score (0.3), brightness_score (0.2); clamped [0, 1].
- `alert.py`: added `format_submission_checklist(neo)` — multi-line checklist with ✓/✗ per alert-protocol gate condition (rb≥0.90, quality≥2, MOID≤0.05, not known, neo_prob≥0.50) plus Step 1/2/3 status.
- `fetch.py`: added `filter_by_survey(fetch_result, surveys)` — return new FetchResult containing only observations whose mission is in the supplied list.
- `preprocess.py`: added `estimate_zero_point(observations, catalog_mags)` — median(obs.mag − catalog_mag) zero-point offset; None if <2 valid pairs; excludes sentinel mags ≥ 90.
- `schemas.py`: added `ObservationStatistics` — frozen model: n_obs, mean_mag, mag_range, mean_real_bogus, n_filters, arc_days.
- `calibration.py`: added `compute_roc_auc(probs, labels)` — ROC AUC via trapezoidal rule; 0.5 for single-class or empty input; NumPy 1.x/2.x compatible.
- `docs/FETCH_GUIDE.md`: new — technical reference for fetch.py: ZTF/ATLAS/MPC/Horizons retrieval, caching, depth estimation, merging, filtering.
- 75 new tests (1242 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.24.0.

### Key Changes in v0.23.0

- `orbit.py`: added `compute_apparent_magnitude(elements, target_jd, albedo=0.14)` — approximate V-band apparent magnitude using IAU HG phase function; returns NaN for degenerate geometry.
- `detect.py`: added `count_detections_by_filter(observations)` — dict mapping filter_band → count; None filter_band mapped to "unknown".
- `link.py`: added `filter_by_nights_observed(tracklets, min_nights=2)` — keep only tracklets spanning ≥ min distinct integer-JD nights.
- `classify.py`: added `get_posterior_vector(posterior)` — 5-element numpy array [neo_candidate, known_object, main_belt_asteroid, stellar_artifact, other_solar_system].
- `score.py`: added `compute_followup_urgency(neo)` — URGENT/HIGH/MEDIUM/ROUTINE tier based on hazard_flag, MOID, and discovery_priority.
- `alert.py`: added `count_pending_alerts(neos)` — dict of alert_pathway → count; only pathways with ≥1 candidate included.
- `fetch.py`: added `estimate_survey_depth(fetch_result)` — 95th-percentile magnitude from valid alerts; None if no valid magnitudes.
- `preprocess.py`: added `compute_photometric_scatter(observations)` — RMS scatter of magnitudes; None for <2 valid observations.
- `schemas.py`: added `PhotometricSolution` — frozen model: zero_point, color_coeff, extinction_coeff, rms_scatter, n_stars, filter_band, epoch_jd.
- `calibration.py`: added `compare_calibrators(probs_list, labels, names)` — dict of name → calibration_report for multiple calibrator comparisons.
- `Skills/triage_candidates.py`: new — urgency-sorted triage table; `--urgency`, `--pathway`, `--json` flags.
- `docs/LINKING_GUIDE.md`: new — tracklet formation, arc statistics, satellite trail rejection, deduplication, quality grades.
- 78 new tests (1167 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.23.0.

### Key Changes in v0.22.0

- `orbit.py`: added `compute_synodic_period(elements)` — synodic period vs Earth in days; inf for a ≤ 0 or a = 1 AU.
- `detect.py`: added `compute_detection_efficiency(observations, limiting_mag)` — fraction of obs brighter than limiting_mag; 0.0 if empty; sentinel mag ≥ 90 counts as missed.
- `link.py`: added `summarize_arc_statistics(tracklets)` — aggregate dict: n_tracklets, mean/max arc_days, fraction_multi_night.
- `classify.py`: added `compute_classification_table(neos)` — list of dicts per NEO: object_id, dominant_hypothesis, probability, entropy_bits.
- `score.py`: added `filter_by_alert_pathway(neos, pathway)` — filter ScoredNEO list by exact alert_pathway match.
- `alert.py`: added `format_impact_notification(neo)` — PDCO-ready notification dict with full provenance, observation list, and guardrail statements.
- `fetch.py`: added `fetch_ztf_alerts(ra, dec, radius, start_jd, end_jd, force_refresh)` — ZTF IRSA cone search; disk-cached; returns list[Observation].
- `preprocess.py`: added `compute_image_quality_metrics(observations)` — dict: n_sources, mean/median_fwhm_arcsec, mean_snr, background_rms.
- `schemas.py`: added `DetectionSummary` — frozen model: field_id, epoch_jd, survey, n_candidates, n_known_matches, n_new, limiting_mag.
- `calibration.py`: added `calibration_report(probs, labels)` — comprehensive dict: brier_score, ece, log_loss, n_samples, mean_prob, fraction_positive.
- `Skills/plot_calibration.py`: new — reliability diagram plot from scored NEO or prob/label JSON; saves PNG; prints Brier/ECE/log-loss.
- `Skills/export_survey_summary.py`: new — per-candidate detection summary export to CSV or HTML; sorted by discovery_priority.
- `docs/DETECTION_GUIDE.md`: new — technical reference for detect.py: RB threshold, streak/trail detection, clustering, known-object matching, detection efficiency, DetectionSummary.
- 71 new tests (1089 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.22.0.

### Key Changes in v0.21.0

- `orbit.py`: added `compute_heliocentric_distance(elements, target_jd)` — heliocentric distance in AU at target JD via `predict_ephemeris`; inf for non-positive semi-major axis; NaN on error.
- `detect.py`: added `estimate_sky_background(observations, percentile)` — percentile of pixel values across difference-image cutouts; None if no valid cutouts.
- `link.py`: added `filter_by_arc_length(tracklets, min_arc_days)` — keep only tracklets with arc_days ≥ threshold (default 1.0).
- `classify.py`: added `calibrate_posterior(posterior, calibrator)` — re-calibrate NEOPosterior with Laplace smoothing (alpha=0.05) or optional calibrator; always normalised to 1.0.
- `score.py`: added `compute_threat_score(neo)` — geometric mean of MOID proximity, H-magnitude size proxy, and orbit quality; [0, 1]; 0.5 sentinel for unknown components.
- `alert.py`: added `generate_mpc_cover_letter(neo)` — formal plain-text MPC submission cover letter with mandatory guardrail "Do NOT publicly announce any impact probability."
- `fetch.py`: added `fetch_atlas_forced(ra_deg, dec_deg, start_jd, end_jd, atlas_token, force_refresh)` — ATLAS forced photometry via REST API with task queuing, polling, and disk cache.
- `preprocess.py`: added `normalize_photometry(observations, zero_point, reference_zero_point)` — zero-point correction; drops corrected mags outside [0, 35]; returns new Observation list.
- `schemas.py`: added `ObservationBatch` — frozen Pydantic model grouping Observations from the same survey field and night (batch_id, field_id, night_jd, mission, observations, limiting_mag).
- `calibration.py`: added `reliability_diagram(probs, labels, n_bins)` — equal-width bin reliability diagram; returns dict with bin_centers, fraction_positive, bin_counts; empty bins excluded.
- `Skills/fetch_atlas_data.py`: new — ATLAS forced photometry CLI; `--token`, `--force-refresh`, `--json` flags.
- `docs/THREAT_ASSESSMENT.md`: new — threat score formula, component breakdowns, interpretation table, alert gate conditions.
- 69 new tests (1018 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.21.0.

### Key Changes in v0.20.0

- `orbit.py`: added `compute_phase_angle(elements, target_jd)` — Sun–target–observer phase angle via law of cosines; returns NaN on degenerate geometry.
- `detect.py`: added `compute_psf_fwhm(obs)` — PSF FWHM in arcsec from 2D Gaussian moment fit; returns None if no cutout or degenerate.
- `link.py`: added `compute_tracklet_grade(tracklet)` — A/B/C/D quality grade from arc length, nights observed, and astrometric RMS.
- `classify.py`: added `summarize_classifications(neos)` — aggregate summary dict: total, dominant_hypothesis_counts, mean_entropy_bits, mean_real_bogus_score, pha_candidate_count.
- `score.py`: added `compute_novelty_score(neo, catalog_elements)` — orbital distance from nearest known NEO in (a, e, i) space; 1.0 = fully novel.
- `alert.py`: added `generate_observation_request(neo, obs_code)` — structured NEOCP follow-up request with urgency tier (URGENT/HIGH/MEDIUM/ROUTINE) and guardrail.
- `fetch.py`: added `fetch_mpc_observations(designation)` — query MPC observation history for a designation; caches to disk; returns list[Observation].
- `preprocess.py`: added `compute_astrometric_scatter(observations)` — RMS of linear RA/Dec fit residuals in arcsec; None for <2 obs or identical JDs.
- `schemas.py`: added `PipelineConfig` — frozen Pydantic model capturing sky position, time window, survey selection, and detection thresholds for a pipeline run.
- `calibration.py`: added `compute_log_loss(probs, labels, eps)` — binary cross-entropy with clipping; returns 0.0 for empty inputs.
- `Skills/grade_tracklets.py`: new — batch-grade tracklets from JSON; `--json` flag.
- `Skills/query_mpc_observations.py`: new — query MPC observation history for a designation; `--json` flag.
- `docs/QUALITY_METRICS.md`: new — comprehensive quality metrics reference for all pipeline stages.
- 69 new tests (949 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.20.0.

### Key Changes in v0.19.0

- `orbit.py`: added `orbital_energy(elements)` — specific orbital energy in AU²/yr²; negative = bound, inf for a ≤ 0.
- `detect.py`: added `compute_trail_length(obs)` — trail length in arcsec from difference-image second moments.
- `link.py`: added `assess_link_confidence(tracklet)` — [0, 1] confidence from linear-fit RMS residual vs 10 arcsec reference.
- `classify.py`: added `batch_morphology(tracklet)` — modal_class, class_counts, streak_fraction across all observations.
- `score.py`: added `compute_impact_energy(diameter_m, velocity_km_s, density_kg_m3)` — kinetic impact energy in megatons TNT.
- `alert.py`: added `format_alert_summary(neos, max_rows)` — plain-text ranked summary table with hazard flag, pathway, MOID, priority.
- `fetch.py`: added `count_known_objects_in_field(ra_deg, dec_deg, radius_deg)` — count MPC known objects in a circular field; returns 0 on failure.
- `preprocess.py`: added `detect_bad_pixels(obs, sigma_threshold)` — MAD-based sigma clipping; returns list of (row, col) tuples.
- `schemas.py`: added `SurveyField` — frozen Pydantic model for survey field metadata (field_id, ra_deg, dec_deg, radius_deg, limiting_mag, n_sources, jd).
- `calibration.py`: added `cross_validate_calibration(probs, labels, n_folds, metric)` — K-fold CV returning (mean, std). Fixed `bootstrap_confidence_interval` empty-guard for numpy arrays.
- `Skills/assess_survey_coverage.py`: new — survey field coverage report; `--json` flag.
- `docs/CLASSIFICATION_GUIDE.md`: new — three-tier ML classification reference.
- 81 new tests (880 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.19.0.

### Key Changes in v0.18.0

- `orbit.py`: added `ephemeris_uncertainty(elements, target_jd)` — sky-plane uncertainty propagated from quality code; scales with propagation time.
- `detect.py`: added `cluster_detections(observations, radius_arcsec)` — greedy spatial clustering; returns list of Observation tuples.
- `link.py`: added `compute_arc_statistics(tracklet)` — summary dict: n_observations, n_nights, arc_days, mean_motion_arcsec_hr, motion_pa_std_deg.
- `classify.py`: added `classify_morphology(obs)` — source morphology from image moments: 'point_source', 'extended', or 'streak'.
- `score.py`: added `absolute_magnitude_from_diameter(diameter_m, albedo)` — H from diameter and albedo; returns inf for zero/negative inputs. Fixed formula.
- `alert.py`: added `format_discovery_circular(neo)` — IAU CBET-style discovery circular; does not transmit.
- `fetch.py`: added `build_observation_window(ra_deg, dec_deg, ...)` — validated ObservationWindow factory with ValueError for bad inputs.
- `preprocess.py`: added `compute_source_snr(obs)` — peak-to-background SNR from difference-image cutout.
- `schemas.py`: added `CloseApproachEvent` — frozen model for a close approach event.
- `calibration.py`: added `bootstrap_confidence_interval(probs, labels, n_bootstrap, metric)` — bootstrap 95% CI for Brier or ECE.
- `Skills/ephemeris_check.py`: new — ephemeris prediction table at user-specified JD.
- `Skills/flag_comet_candidates.py`: new — combined T_J + eccentricity comet-candidate flag.
- `docs/ALERT_PROTOCOL.md`: new — alert pathway technical reference.
- 70 new tests (799 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.18.0.

### Key Changes in v0.17.0

- `orbit.py`: added `batch_predict_ephemeris(elements_list, target_jd)` — batch sky-position prediction; per-element error isolation.
- `orbit.py`: added `resonance_check(elements, tolerance)` — mean-motion resonance detection with Jupiter; checks T_J/T_asteroid ratio against p:q pairs; returns resonance label or None.
- `detect.py`: added `compute_streak_metric(obs)` — streak severity from difference-image second moments; [0, 1]; handles degenerate zero-eigenvalue (perfectly elongated) case.
- `link.py`: added `split_tracklet(tracklet, split_jd)` — split tracklet at a JD boundary into two sub-tracklets; raises ValueError if either part has fewer than 2 observations.
- `classify.py`: added `dominant_hypothesis(posterior)` — return (name, probability) for highest-probability class; ("unknown", 0.0) for all-zero posterior.
- `score.py`: added `close_approach_candidates(neos, max_moid_au)` — filter by MOID ≤ threshold; None MOID excluded.
- `alert.py`: added `ready_for_submission(neo)` — boolean gate for all alert-protocol preconditions; returns (bool, unmet list); fixed field name orbit_quality_code → quality_code.
- `fetch.py`: added `filter_alerts_by_motion(alerts, min_rate, max_rate)` — filter by ssdistnr-based motion proxy; observations without ssdistnr pass through.
- `preprocess.py`: added `estimate_source_density(observations, field_radius_deg)` — source count per square degree via great-circle centroid.
- `schemas.py`: added `TrackletSummary` — lightweight frozen model for tracklet display/export.
- `Skills/check_tisserand.py`: new — batch Tisserand parameter check; comet-like flag; `--threshold` and `--json` CLI flags.
- `Skills/export_followup_requests.py`: new — NEOCP follow-up request generator; `--min-priority`, `--out-dir`, `--obs-code`, `--summary` CLI flags.
- `docs/ORBIT_FITTING.md`: new — orbit fitting technical reference.
- 146 new tests (729 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.17.0.

### Key Changes in v0.16.0

- `orbit.py`: added `classify_neo_class(elements)` — derive NEO dynamical class from orbital elements.
- `orbit.py`: added `tisserand_parameter(elements)` — Tisserand parameter relative to Jupiter; T_J < 3 distinguishes comets.
- `detect.py`: added `filter_by_real_bogus(result, threshold)` — filter DetectResult by max real/bogus score.
- `link.py`: added `deduplicate_tracklets(tracklets)` — remove tracklets with ≥ 50% overlapping obs_ids; longer arc wins.
- `score.py`: added `pha_candidates(neos)` — filter to PHA candidates only.
- `score.py`: added `compute_statistics(neos)` — aggregate NEOStatistics (counts, priority, class distribution).
- `classify.py`: added `posterior_entropy(posterior)` — Shannon entropy of NEOPosterior in bits.
- `alert.py`: added `format_neocp_report(neo, obs_code)` — plain-text NEOCP follow-up request with guardrails.
- `fetch.py`: added `merge_survey_alerts(results)` — merge and deduplicate multiple FetchResults.
- `preprocess.py`: added `compute_color_index(obs1, obs2)` — magnitude difference for observations in different bands.
- `schemas.py`: added `NEOStatistics` — frozen Pydantic model for aggregate pipeline statistics.
- `Skills/export_candidate_report.py`: new — per-candidate plain-text reports; `--split` writes one file per candidate.
- `Skills/tag_neo_class.py`: new — batch-tag NEO class using `classify_neo_class`.
- `docs/TRAINING_GUIDE.md`: new — step-by-step ML training guide (Tier 1–3, calibration, injection-recovery).
- 77 new tests; 660 total; 100% coverage maintained.
- Version bumped to 0.16.0.

### Key Changes in v0.15.0

- `orbit.py`: added `compute_orbital_period` — Kepler's third law; T = 365.25 × √(a³) days.
- `link.py`: added `filter_high_motion(tracklets, min_rate_arcsec_hr)` — filter by motion rate threshold (default 10 arcsec/hr).
- `score.py`: added `followup_priority_table(neos)` — flat ranked table dict list sorted by discovery priority.
- `classify.py`: added `batch_explain(tracklets)` — batch version of `explain_classification`.
- `alert.py`: added `alert_summary_table(neos)` — flat per-NEO alert summary with ready_to_submit flag.
- `fetch.py`: added `summarise_fetch_result(result)` — summary dict of a FetchResult.
- `preprocess.py`: added `flag_saturated_sources(result, saturation_mag)` — return obs_ids of likely saturated sources.
- `schemas.py`: added `CandidateSummary` — lightweight frozen Pydantic model for NEO display/export.
- `Skills/filter_candidates.py`: new — filter scored NEO JSON by hazard flag, pathway, or priority.
- `Skills/summarise_run.py`: new — human-readable or JSON pipeline run summary.
- `Skills/plot_sky_coverage.py`: new — RA/Dec scatter plot colour-coded by hazard flag (matplotlib).
- `docs/API_REFERENCE.md`: updated with all v0.14.0 and v0.15.0 APIs.
- 55 new tests; 583 total; 100% coverage maintained.
- Version bumped to 0.15.0.

### Key Changes in v0.14.0

- `orbit.py`: added `close_approach_table` — tabulate geocentric distance over a time window.
- `link.py`: added `estimate_motion_uncertainty` — rate and PA error from linear fit residuals.
- `score.py`: added `discovery_report` — comprehensive nested summary dict for human review.
- `classify.py`: added `explain_classification` — structured classification breakdown with Tier 1 importances. Fixed Pydantic v2.11 `model_fields` deprecation.
- `alert.py`: added `draft_mpc_submission` — complete MPC submission bundle with guardrail cover letter.
- `schemas.py`: added `ObservationWindow` — frozen typed model for sky/time search queries.
- `fetch.py`: added `estimate_limiting_magnitude` — survey depth proxy from faint-end magnitude tail.
- `preprocess.py`: added `quality_summary` — per-field PSF quality, background RMS, and elongation statistics.
- `detect.py`: added `streak_candidates` — filter `DetectResult` for streak/trail detections only.
- `background.py`: added `audit_report` — consolidated cross-log audit report.
- `Skills/generate_obs_schedule.py`: prioritized follow-up observation schedule with urgency tiers.
- `Skills/photometric_calibration.py`: per-field photometric zero-point fit via Gaia DR3.
- `Skills/export_mpc_bulk.py`: bulk MPC 80-column report export with manifest.
- `docs/SCORING_MODEL.md`: updated with ranking, discovery report, motion uncertainty, close-approach table, and photometric calibration.
- 63 new tests; 528 total; 100% coverage maintained.
- Version bumped to 0.14.0.

### Key Changes in v0.13.0

- `fetch.py`: added `fetch_batch` — fetch multiple sky positions in one call.
- `preprocess.py`: added `preprocess_batch` — batch preprocessing from `FetchResult` list.
- `detect.py`: added `detect_batch` — batch detection from `PreprocessResult` list.
- `link.py`: added `merge_tracklets` — merge two tracklets into a longer deduplicated arc.
- `orbit.py`: added `propagate_orbit` (Keplerian propagation), `predict_ephemeris` (geocentric RA/Dec at target JD).
- `score.py`: added `rank_candidates` — sort `ScoredNEO` list by priority with PHA tier.
- `alert.py`: added `generate_alert_package` — bundle all alert artifacts into one dict.
- `schemas.py`: added `PipelineResult` — immutable top-level pipeline run container.
- `Skills/simulate_survey.py`: synthetic ZTF-like survey generator.
- `Skills/export_ranked_table.py`: CSV/HTML ranked table export.
- `Skills/check_orbit_quality.py`: orbit quality CLI for tracklet JSON.
- `tests/conftest.py`: extended with `build_raw_candidate`, `build_scored_neo`, and `scored_neo`/`raw_candidate` fixtures.
- `docs/PIPELINE_SPEC.md`: updated with all v0.13.0 APIs and `PipelineResult` container.
- 54 new tests; 465 total; 100% coverage maintained.
- Version bumped to 0.13.0.

### Key Changes in v0.12.0

- `link.py`: added `_is_satellite_trail` — rejects purely E-W or N-S fast-moving pairs (≥30 arcsec/hr) as satellite/debris trails.
- `classify.py`: added `classify_batch` and `get_tier1_feature_importances` public APIs.
- `orbit.py`: added `arc_quality_report` — returns quality dict with codes 1–4.
- `score.py`: added `score_batch`; `ScoringMetadata.close_approach_au` now populated from MOID when orbit quality ≥ 2.
- `schemas.py`: added `close_approach_au: float | None = None` to `ScoringMetadata`.
- `alert.py`: added `format_mpc_json` and `batch_process_alerts` public APIs.
- `Skills/validate_mpc_report.py`: new — validate MPC 80-column report format.
- `Skills/diagnose_pipeline.py`: new — per-stage diagnostic runner with synthetic data.
- `Skills/compare_baselines.py`: new — compare injection-recovery baselines; regression detection.
- `docs/API_REFERENCE.md`: updated with all v0.12.0 public APIs.
- 34 new tests; 411 total; 100% coverage maintained.
- Version bumped to 0.12.0.

### Key Changes in v0.11.0

- `link.py`: fixed chi² error proxy (`max(mag_err * 0.1, 0.1)` → `max(mag_err, 0.5)`) — link rate 62% → 100%
- `link.py`: added `_predict_from_arc` (quadratic polyfit for ≥3 obs, linear fallback) for more accurate position prediction
- `fetch.py`: added `force_refresh` flag to bypass on-disk cache; ATLAS token now falls back to `ATLAS_TOKEN` env var
- `alert.py`: added public `monitor_neocp` with injectable sleep for NEOCP polling loop
- `classify.py`: added `retrain_tier1` and `retrain_stacker` public APIs for incremental retraining
- `Skills/run_pipeline.py`: added `--atlas-token`, `--force-refresh`, `--neocp-timeout-hours`, `--neocp-poll-interval` flags
- `Skills/stress_test_high_motion.py`: stress-test linker across 3 motion bins; all bins 100%
- `Skills/build_cutout_dataset.py`: build `.npz` + CSV index from ZTF alert JSON for Tier 2 training
- `Skills/build_sequence_dataset.py`: build flat token CSV from tracklet JSON for Tier 3 training
- `Skills/train_tier2_cnn.py`: updated to read `.npz` cutout files from `cutout_path` column
- `Skills/train_tier3_transformer.py`: updated to read flat `tok_i_j` columns
- `Skills/smoke_test.py`: added `monitor_neocp` and `retrain` smoke tests
- `Skills/check_mpc_known.py`: added `--neocp` CLI flag and `check_neocp` function
- `data/injection_recovery_n200.json`: n=200 baseline: 100% detection, link, score
- `data/stress_test_high_motion.json`: stress-test results
- CHANGELOG.md: full Keep-a-Changelog history added (v0.1.0–v0.11.0)
- 31 new tests; 377 total; 100% coverage maintained
- Version bumped to 0.11.0.

### Key Changes in v0.10.0

- Removed deprecated background wrapper scripts; `Skills/background.py` is the single supported CLI.
- Added versioned background target manifest support and `background/config.schema.json`.
- Added run detail, target history, signoff readiness, and unsigned follow-up audit views.
- Added CLI and manifest regression tests; 346 total; 100% coverage.
- Version bumped to 0.10.0.

### Key Changes in v0.9.0

- `link.py`: fixed prediction bug — `_predict_position` now uses `obs_c.jd` instead of integer night key; link rate 2% → 62%
- `Skills/tune_linker.py`: parametric sweep of tolerance × chi² vs link/score rate
- 4 new tests (regression test for prediction fix + arc_below_min_obs + tune_linker smoke); 328 total; 100% coverage
- Injection-recovery baseline updated: 62% link rate (n=50, seed=42)
- Version bumped to 0.9.0

### Key Changes in v0.8.0

- `classify.py`: added `_build_ensemble` (sklearn LogisticRegression meta-learner) + `ensemble_predict` public API
- `Skills/injection_recovery.py`: added `--json PATH` flag to save results
- Baseline injection-recovery run saved to `data/injection_recovery_baseline.json`
- 8 new tests; 324 total; 100% coverage maintained
- Version bumped to 0.8.0

### Key Changes in v0.7.0

- fetch.py: 75% → 100% via mocks for ztfquery, ATLAS network, astroquery.mpc, jplhorizons
- CI coverage gate raised from 95% → 100%; actual coverage 100.00%
- New Skills: `benchmark_pipeline.py`, `train_tier2_cnn.py`, `train_tier3_transformer.py`
- New infra: `.github/ISSUE_TEMPLATE/` (bug + feature request templates), `models/` directory
- Version bumped to 0.7.0 in `pyproject.toml` and `src/__init__.py`

### Key Changes in v0.6.0

- torch installed; CNN (Tier 2) and Transformer (Tier 3) paths fully tested (100% classify.py coverage)
- Alert module: `process_alert` accepts `cneos_assessment` parameter for PDCO path testing
- Coverage gate raised from 85% → 95% in CI; actual coverage 97.44%
- 40 new tests added across orbit, detect, preprocess, calibration, classify, alert modules
- Version bumped to 0.6.0 in `pyproject.toml` and `src/__init__.py`
