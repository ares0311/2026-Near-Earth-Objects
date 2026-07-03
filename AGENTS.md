# AGENTS.md — NEO Detection & Ranking Project

This file is read automatically by Codex at session start.
It contains the facts a coding agent needs to work productively without re-reading every document.

---

## Standing Rules

- **Skills directory**: Any standalone `.py` utility script created to perform a task must be saved in `Skills/` at the project root.
- **No impact claims**: Never assert a probability of Earth impact from internally computed data alone. Always defer to MPC/CNEOS for authoritative hazard assessment.
- **Alert protocol is sacred**: The NASA/MPC alert pathway (see §Alert Protocol) must never be triggered on unconfirmed detections. Require independent confirmation first.
- **Protect active operator runs**: Before switching branches or editing tracked
  files, check for `Logs/tier3_pilot.active.json`. If present, do not alter the
  shared checkout until the operator run exits and removes the marker.

- **Python runtime is 3.14.3 — always use `uv run`**: The project venv is
  Python 3.14.3, managed by uv from `uv.lock`. Never invoke bare `python`,
  `pytest`, `mypy`, or `ruff` directly — always prefix with `uv run` so the
  correct interpreter and locked dependencies are used. CI enforces the same
  via `astral-sh/setup-uv@v5` with `python-version: "3.14"`.
  Example: `PYTHONPATH=src uv run --python 3.14 python -m pytest`
- **Local system profile governs optimization defaults**: `docs/SYSTEM_PROFILE.md`
  is a committed directive for local resource sizing. Optimize project code,
  tests, and operator commands for that profile unless portability or a task
  requirement says otherwise. Do not hardcode machine-specific assumptions into
  scientific logic; expose performance-sensitive behavior through configuration
  or documented runtime defaults.
- **Use local compute deliberately**: When implementing or running AI training,
  first target the local Apple GPU/Metal acceleration described in
  `docs/SYSTEM_PROFILE.md` (for example PyTorch MPS) when the framework supports
  it, and report any CPU fallback explicitly. Other CPU-heavy local code should
  use bounded multithreading or multiprocessing by default, sized from
  `docs/SYSTEM_PROFILE.md`, while avoiding native-library oversubscription and
  keeping live external-service concurrency conservative. Performance-sensitive
  worker counts, device selection, batch sizes, and thread limits must be
  configurable or documented runtime defaults, not hidden machine-specific
  constants.
- **Discovery paper goal — NOT citizen science**: Jerome W. Lindsey III is the
  project operator and reviewer. The goal is a **defensible discovery paper**:
  find new NEOs in unreviewed archival data, submit candidates to MPC, obtain a
  provisional designation via independent NEOCP confirmation, and publish.
  We NEVER claim discovery — only "candidates consistent with NEO orbits."
  Two review stages gate every submission: (1) automated adversarial review
  (`Skills/adversarial_review.py` — 13 challenges, tries to REJECT each
  candidate), then (2) operator review. Only SURVIVE/BORDERLINE candidates
  proceed to MPC submission. See `docs/MISSION.md` and
  `docs/neo_discovery_agent_brief.md` (jointly authoritative) plus
  `docs/MPC_SUBMISSION_POLICY.md` for the full submission policy.
  Do NOT reinstate a "blocked until expert review" guardrail — MPC/NEOCP/Scout
  IS the expert review system. Do NOT frame this as citizen science.
  **MANDATORY READ**: `docs/near_earth_objects_research_brief.md` — ranked
  space assets, frontier AI methods, submission best practices. Read at every
  session start per CLAUDE.md §MANDATORY SESSION-START PROTOCOL.
  **MANDATORY READ**: `docs/neo_discovery_agent_brief.md` — authoritative
  workflow brief for candidate language, historical replay, source
  verification, no future-catalog leakage, pretrained-model audits, and
  auditable candidate-ranker design.
- **Repository artifact policy supports `git add .`**: The standard operator
  cadence may use `git add .`, so `.gitignore` must protect local/generated
  outputs by default. Treat `Logs/**` as local operational output and never
  commit it except `Logs/.gitkeep` and `Logs/reports/.gitkeep`. When run
  evidence must be visible to future agents, promote a compact, sanitized
  summary into `docs/evidence/` or `data/evidence/` instead of committing raw
  `Logs/` files. Production model artifacts in `models/` must be explicitly
  allowlisted by filename; do not use broad `!models/*.pt` or `!models/*.json`
  rules. Before committing, inspect `git status --short`, the staged filename
  list, and ignore behavior for generated outputs; if `git add .` would capture
  local run debris, fix `.gitignore` and untrack it before committing.
- **Always evaluate parallelism for operator commands expected to take longer than 3 minutes**:
  Before handing off any operator command, evaluate whether the work is
  parallelizable (independent items with no shared mutable state) rather
  than defaulting to a single sequential run: shard across concurrent
  terminal tabs for network-bound work, use bounded local multiprocessing
  for CPU-bound work (sized per `docs/SYSTEM_PROFILE.md`), or — if the
  tool already checkpoints per-item independently — just tell the
  operator to run existing commands in separate tabs with no code
  changes. State explicitly whether parallelism was considered and why it
  was or wasn't applied. If it's ambiguous whether parallelizing is worth
  the complexity, ask the operator rather than deciding unilaterally.
- **Progressively probe toward the safe concurrency ceiling — don't stay pinned to the conservative starting point**:
  `docs/SYSTEM_PROFILE.md`'s "usually 4 to 6 workers" for external-service
  work is a conservative first-batch starting point, not a permanent
  ceiling. After a batch completes with zero errors/rate-limiting/latency
  degradation, the next batch against that same service may step
  concurrency up by a bounded increment (~+2, up to ~1.5x); step back down
  immediately on any bad signal; a service's own documented rate limit is
  always authoritative and must never be exceeded; record the empirically
  safe level per service in `docs/SYSTEM_PROFILE.md` or a dated evidence
  file. Still ask the operator before escalating against a small/
  community-run resource. See CLAUDE.md's Standing Rules for detail.
- **Parallel/sharded Skills scripts must write a live-updating shared manifest**:
  Any Skills script supporting concurrent operator-launched processes
  (e.g. `--shard-index`/`--shard-count` for parallel terminal tabs) must
  have every process append its completion summary to one shared,
  file-locked manifest (e.g. `manifest.jsonl`) the moment it finishes —
  not only write an isolated per-process report. Provide a `--status`
  check that is safe to run at any time (never fails closed on
  incomplete progress) and a separate `--merge`/finalize check that does
  fail closed if any expected shard has not reported in. Re-running a
  shard replaces, not duplicates, its manifest entry. See CLAUDE.md's
  Standing Rules for the full implementation checklist.
- **The manifest must live in a committed path and be auto-pushed — git is the relay, not the operator's filesystem**:
  A local-only manifest does not solve "avoid pasting console output"
  because the agent has no access to the operator's machine, only to what
  is pushed to GitHub. Write manifests to `Logs/reports/` (already
  allowlisted in `.gitignore`, unlike the rest of `Logs/**`), and have the
  script itself `git add`/`commit`/`push` just that one file at the end of
  every invocation (retry with `pull --rebase` on conflict, never raise on
  final failure). Scope the auto-push narrowly to that one data file only,
  never source code. Provide `--sync` to backfill from checkpoints
  predating this behavior. See CLAUDE.md's Standing Rules for detail.

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
- **ZTF** (Zwicky Transient Facility) — **primary discovery source as of
  2026-07-02** via ZTF DR24 archival historical replay (see
  `docs/MISSION.md §Operator Decision`). Live ZTF alert-stream consumption
  remains prohibited; only bounded archival historical replay is permitted.
- **ATLAS** — training and recovery-evidence source; 24–48 hr warning-capable
  survey stream already processed for operational discovery
- **Pan-STARRS** — deep survey; public catalog access
- **CSS** (Catalina Sky Survey) — MPC-feeding survey
- **WISE/NEOWISE, DECam, and TESS** — **secondary/paused discovery sources**
  as of 2026-07-02 (were primary through v0.90.10); code and Gate P1–P5
  evidence preserved but not the active development target

`docs/neo_discovery_agent_brief.md` adds the authoritative rule that ZTF/Fink,
Fink-FAT, and SNAPS are methodology, benchmark, source-verification, and
candidate-ranker references unless a future documented production decision
proves a non-duplicative discovery-submission path.

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
| `fetch.py` | complete | test_fetch.py | WISE/DECam/TESS discovery layer + ZTF/ATLAS/MPC (training) |
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

**WISE/NEOWISE** (primary discovery target — unreviewed archive)
- Infrared detections of 158,000+ minor planets; no credentials required
- Access: IRSA WISE/NEOWISE catalogs via `astroquery.ipac.irsa` or IRSA TAP
- Key value: closest to Sun coverage, IR sensitivity, no ground survey overlap

**TESS FFIs** (discovery target — unreviewed archive)
- Full Frame Images contain moving-object trails not processed by planet-finding pipeline
- Access: MAST public archive, no credentials required for public data

**ZTF** (training-data source ONLY — NOT for discovery)
- Public alert stream via IRSA (`ztfquery` Python package or direct API)
- Already processed by ZTF ZAPS — do NOT use for discovery
- 3-night cadence over the full northern sky; $g$, $r$, $i$ bands
- Key fields: `ra`, `dec`, `jd`, `magpsf`, `rb` (real/bogus score), `drb`, `ssdistnr`

**ATLAS Forced Photometry Server** (training-data source ONLY — NOT for discovery)
- Public REST API; forced photometry at any sky position
- Already processed by ATLAS pipeline — do NOT use for discovery
- Orange ($o$) and cyan ($c$) bands; 2-day cadence

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

### DECISION-001: ZTF DR24 historical replay as primary discovery path (SUPERSEDED 2026-07-02)
**Superseded by operator decision 2026-07-02** (see `docs/MISSION.md
§Operator Decision`): `docs/neo_discovery_agent_brief.md` now supersedes the
WISE-primary strategy below. ZTF DR24 archival historical replay is the
primary discovery path; WISE/DECam/TESS are secondary/paused. Live
ZTF/ATLAS alert-stream discovery remains prohibited — the change is
specifically that bounded, time-aware *archival* ZTF DR24 reprocessing is
now permitted and primary, per the brief's Fink-FAT precedent.

**Original decision (2026-06-27, now secondary)**: ZTF provided the richest freely available alert stream for ML training (Tier 1 + Tier 2 labels). ZTF ZAPS and the ATLAS pipeline already process and submit discoveries from live streams — running the pipeline on live ZTF/ATLAS for discovery would produce duplicate submissions. WISE/NEOWISE (IRSA, no credentials), TESS FFIs, and DECam/NOIRLab were the primary discovery targets. See `docs/near_earth_objects_research_brief.md §Ranked Space Assets`.

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
  - Pair detections consistent with solar system object motion (0.05–60 arcsec/hr)
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

**Always use `uv run` — never call `python`, `pytest`, `mypy`, or `ruff` directly.**
The project venv is Python 3.14.3 managed by uv from `uv.lock`.

```bash
# Lint
uv run --python 3.14 ruff check .
uv run --python 3.14 ruff check . --fix

# Type-check
uv run --python 3.14 python -m mypy src

# Tests
PYTHONPATH=src uv run --python 3.14 python -m pytest

# macOS local runs with XGBoost/OpenMP may need deterministic threading
OMP_NUM_THREADS=1 PYTHONPATH=src uv run --python 3.14 python -m pytest

# All three
uv run --python 3.14 ruff check . && uv run --python 3.14 python -m mypy src && PYTHONPATH=src uv run --python 3.14 python -m pytest
```

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
- Production calibration promotion is quantitative and fail-closed. Apply the
  KPI gate in `docs/PRODUCTION_READINESS.md` to held-out real labeled data;
  reliability diagrams provide supporting evidence but do not require human
  calibration approval.

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

## Current State (v0.90.27)

All 10 legacy pipeline modules are complete. The offline suite passes on Python
3.14, all three legacy ML tiers have trained weights, and the WISE/DECam/TESS
production-capability gates P1/P2/P3/P5 are closed as historical evidence.
However, the operator pivot on 2026-07-02 makes ZTF DR24 archival historical
replay the current primary discovery path. The WISE/DECam/TESS path is
secondary/paused and must not be treated as proof that the new ZTF DR24 path is
production-capable.
For the ZTF DR24 path, Gate Z1 bounded ingest and Gate Z2 time-aware
known-object exclusion are code-complete but still require operator live
verification. Gate Z3 is not blocked on linker scaffolding: the existing
linear-motion linker already satisfies the Fink-FAT-style tracklet-linking
shape. The active blocker is finding and verifying a per-source ZTF DR24
detection source that yields real candidate detections (RA/Dec/time/magnitude)
instead of only image/exposure metadata. The older ALeRCE-backed ZTF provider
is real bounded-pilot evidence, but
`docs/evidence/phase0/alerce_source_detection_assessment.md` records that it
does not close the DR24 Gate Z3 source question unless verified for the current
historical-replay protocol. v0.90.24
also ported the missing
macOS CNN model-load warmups into `src/classify.py`; that fix needs one
operator Mac re-run before it is field-confirmed.
Console output is now fully compliant with `docs/CONSOLE_OUTPUT_SPEC.md` —
every stage print includes `elapsed {M}m{S:02d}s` and ETA is computed from
a measurable quantity (surveys done/total, tracklets done/total).

**Production gap status (as of 2026-06-22)**:
- T1-A (Incomplete Trained ML Model Set): **CLOSED.** All Tier 1/2/3 weights
  trained; ensemble stacker KPIs passed (AUC=0.9809, Brier=0.0211, ECE=0.0000);
  `promotion_gate_passed=true`.
- T1-B (No Live Credentials): **CLOSED.** ATLAS token and ZTF IRSA credentials
  confirmed PRESENT via `source Skills/verify_live_credentials.sh`; live
  connection test OK. Credentials stored in macOS Keychain under service names
  `neo-detection:ATLAS_TOKEN`, `neo-detection:ZTF_IRSA_USERNAME`,
  `neo-detection:ZTF_IRSA_PASSWORD` — never stored in repo. Bounded live
  dry-run policy is signed in `background/live_review_policy.example.json`;
  execution still fails closed on missing provider credentials and never
  authorizes external submission or impact-probability claims.
- T1-C (Real-Data Recovery And Operator Review Evidence): **CLOSED
  2026-06-20.** ATLAS Option A follow-up run `atlas_recovery_c1712df0f32c`
  recovered 5/5 prequalified objects (100%); audit passed; operator
  review by Jerome W. Lindsey III found no blocking findings. Full evidence:
  `docs/evidence/t1c/2026-06-20-option-a-screening-prequalification.md`.
- T1-D (No Ensemble Calibration): **CLOSED.** All KPIs passed 2026-06-14.
- T2-C (No External Expert Review): **CLOSED 2026-06-21.** Architecture
  evidence packet signed by Jerome W. Lindsey III (operator sign-off); all 5
  attestation items checked.
- T2-D (No CI for E2E/Integration/Model-Weight Tests): **CLOSED 2026-06-21.**
  `e2e.yml` has smoke/diagnose/injection/model-weights jobs; `integration.yml`
  gated on secrets.
- T2-A (Integration Tests vs Real APIs): **CLOSED 2026-06-21.** Both
  `test_fetch_ztf_live_small_region` and `test_fetch_atlas_live_small_region`
  PASSED on operator Mac. Evidence: `docs/evidence/t2a/`.
- T2-B (Adversarial/Robustness Testing): **CLOSED 2026-06-22.** All 10
  synthetic adversarial tests in `tests/test_adversarial.py` pass in CI.
  Real-data false-positive audit vs known-artifact catalog is a future
  operator-run step and is not a current blocker.

See `docs/PRODUCTION_READINESS.md` for the full gap register.

### Handoff notes (2026-07-02) — v0.90.27 (CURRENT)

**Current merged state through PR #163**:

- v0.90.20 built `Skills/ztf_dr24_bounded_ingest.py` for bounded,
  checkpointed IRSA ZTF DR24 science-image metadata ingest. It is offline
  tested but needs one operator live run before Gate Z1 can close.
- v0.90.21 built `src/known_object_exclusion.py` for time-aware,
  fail-closed known-object filtering from documented `first_obs` evidence.
  It needs operator live confirmation that `first_obs` returns real dates on
  the already-verified JPL SBDB `sb-group=neo` query before Gate Z2 can close.
- v0.90.22 corrected Gate Z3: do not build another linker just to satisfy the
  brief. `src/link.py` already provides the linear-motion tracklet linker. The
  real dependency gap is a verified per-source ZTF DR24 detection source; Gate
  Z1 currently ingests image/exposure metadata only.
- v0.90.23 added progress output to `Skills/injection_recovery.py` so long
  model cold starts are never silent.
- v0.90.24 ported the missing macOS CNN-load warmups into
  `src/classify.py`, fixing the likely real operator deadlock path. This
  cannot be field-confirmed in the Linux sandbox and needs one Mac operator
  re-run.
- v0.90.25 synchronized the durable docs with that state.
- v0.90.26 resolved the legacy ALeRCE wording trap: ALeRCE remains real
  source-level ZTF pilot evidence, but it is not current DR24 production
  evidence until documented as suitable for bounded historical replay.
- v0.90.27 adds `docs/evidence/phase0/alerce_source_detection_assessment.md`
  from official ALeRCE docs. It verifies source-level detection fields exist,
  but finds no doc evidence for DR24 static-archive or no-future-leakage
  suitability.
  Future agents should continue at Gate Z3 by verifying a per-source ZTF DR24
  detection source from official documentation or live evidence. Do not rerun
  exhausted WISE diagnostics, do not restart Gate Z1 scaffolding, and do not
  guess endpoints or schemas.

### Handoff notes (2026-07-02) — v0.90.19

**Phase 0 source verification for the ZTF DR24 historical-replay pipeline is
now materially complete except for the external Fink TLS blocker.** Evidence is
committed under `docs/evidence/phase0/`:

- `data_sources_verified.md`: live operator-observed results show JPL SBDB,
  MPC get-obs, and IRSA ZTF image metadata all returning HTTP 200.
- `auth_requirements.md`: those three probes required no credentials for the
  tested read-only calls; Fink auth remains unknown because both Fink probes
  failed before HTTP response.
- `phase0_probe_results.json`: raw captured headers/body previews. MPC get-obs
  uses a GET with JSON body `{"desigs": ["433"]}`; JPL SBDB uses
  `sb-group=neo`.
- `schema_snapshot/README.md`, `sample_ingest_report.md`, and
  `pretrained_model_audit.md`: complete the brief's Phase 0 deliverable set
  without inventing ingestion or approving pretrained models.
- `2026-07-02-root-cause-findings.md`: root causes recorded. JPL's brief
  example `neo=Y` was wrong; MPC get-obs requires a JSON body; Fink is an
  external TLS-handshake failure reproduced across Python and curl; v0.90.17
  fixed stale checkpoint reuse by hashing full probe definitions; v0.90.18
  commits the refreshed evidence packet and missing Phase 0 deliverables.

**Highest-priority next production work**: work Gate Z1 from
`docs/ZTF_DR24_PRODUCTION_GATES.md` by starting a bounded ZTF DR24 historical
replay ingest prototype: IRSA ZTF metadata access, no-future-catalog-leakage
known-object exclusion, Fink-FAT-style linear linking, auditable handcrafted
features, and a logistic-regression baseline before any LightGBM/XGBoost or
pretrained model work. Do not block on Fink unless a Phase 1 task specifically
requires Fink schema access; the verified IRSA/JPL/MPC path is enough to begin
bounded prototype design.

### Handoff notes (2026-07-02) — v0.90.12 — MAJOR PIVOT

**Operator decision: ZTF DR24 historical replay is now the primary discovery
pipeline, superseding WISE/DECam/TESS.** Full record: `docs/MISSION.md
§Operator Decision (2026-07-02)`. Key points:

- `docs/neo_discovery_agent_brief.md` supersedes the 2026-07-01
  reconciliation that kept WISE/DECam/TESS primary. Build the brief's Phase
  1 pipeline next: ZTF DR24 archival historical replay, time-aware
  known-object exclusion, Fink-FAT-style tracklet linker, LightGBM/XGBoost
  candidate ranker.
- WISE/DECam/TESS code and all Gate P1–P5 evidence are preserved, not
  deleted — secondary/paused, not the active target.
- Live ZTF/ATLAS alert-stream discovery is still prohibited. Only bounded,
  time-aware archival ZTF DR24 reprocessing is newly permitted.
- The `docs/PRODUCTION_READINESS.md` P1–P5 gates describe the now-secondary
  WISE/DECam/TESS pipeline and do not establish readiness for the new ZTF
  DR24 pipeline. New gates are needed before claiming that pipeline is
  production-capable.
- **Status update v0.90.18**: Phase 0 verification is now recorded under
  `docs/evidence/phase0/`. JPL/MPC/IRSA are live-verified; Fink remains an
  external TLS blocker; pretrained models are deferred.

### Handoff notes (2026-07-02) — v0.90.11

**Correction (operator-flagged 2026-07-02)**: earlier same-day handoff notes
described Gate P4 as something requiring active operator action ("Jerome
must obtain written MPC confirmation," "wait on Jerome's Gate P4
correspondence"). That framing was wrong — **there is no candidate yet, so
there is nothing to tell MPC and no reason to contact them.** Gate P4 is
**dormant**, not a pending operator task. It only becomes relevant once a
real WISE-sourced candidate actually survives adversarial review and
operator review. Do not describe Gate P4 as "awaiting operator
correspondence" in future handoffs.

**Current production definition**:
- Production readiness now means demonstrated capability to find, score,
  reject, review, and package candidates from unreviewed archival discovery
  data with defensible, industry-standard confidence controls. It does not
  require that the project has already found a genuinely new NEO.
- `docs/neo_discovery_agent_brief.md` is now authoritative workflow guidance
  and has been applied to close Gate P2: source verification, no future-catalog
  leakage, historical replay discipline, pretrained-model audits, and
  auditable ranker design are recorded in `docs/SURVEY_NATIVE_CONFIDENCE_POLICY.md`.
- **Gates P1, P2, P3, and P5 in `docs/PRODUCTION_READINESS.md` are all
  CLOSED.** Gate P4 (MPC submission protocol) is open but dormant — it does
  not require operator action today; it activates only when a real candidate
  needs submitting. No further code work can close it either, since the
  fail-closed guards already exist and were verified in the Gate P3 drill.
  Actual candidate survival is a later event-driven discovery gate.

**Gate P5 CLOSED (2026-07-02)**:
- `docs/OPERATOR_GO_NO_GO_RUNBOOK.md`: one-page flow with review-packet
  location, verified `adversarial_review.py`/`export_ades_report.py`
  commands, an operator-review checklist, the dormant Gate P4 check, and
  the permanent forbidden-communications list. States `SURVIVE`/`BORDERLINE`
  means "candidate may be reviewed for MPC submission," never "confirmed NEO."
- **NEXT PRODUCTION ACTION for a coding agent**: all code-addressable
  production-capability gates are closed. Remaining code-addressable work is
  the two items left open under Gate P2 (WISE sentinel-magnitude rejection
  filter; DECam/TESS live endpoint verification). There is no pending
  operator task to wait on — do not invent one.

**Gate P3 CLOSED (2026-07-02)**:
- `Skills/injection_recovery.py --review-packet-out` writes full `ScoredNEO`
  packets from injection runs, feeding the drill directly from a Gate P1 run.
- Drilled 5 synthetic WISE packets through `Skills/adversarial_review.py
  --offline` (5/5 `REJECT`, expected) and `Skills/export_ades_report.py`
  twice — default args and `--obs-code C51` without confirmation — both
  failed closed with no `.psv` file written and no network call.
- Evidence: `docs/evidence/prod-loop/2026-07-02-gate-p3-no-submission-drill.md`.
- **NEXT PRODUCTION ACTION — NOT YET DONE**: Gate P4 requires Jerome to
  contact MPC in writing about archival WISE/NEOWISE submission authority
  under station code C51 (see `docs/MPC_SUBMISSION_POLICY.md §TODO for Future
  Agents`). No code path can substitute for this.

**Gate P2 CLOSED (2026-07-02)**:
- `docs/SURVEY_NATIVE_CONFIDENCE_POLICY.md` documents the source-verification
  matrix (WISE live-verified; DECam/TESS code-complete but never
  live-verified), confirms `score.py:_determine_alert_pathway` already fails
  closed on missing real/bogus (routes to `internal_candidate`), records the
  no-future-catalog-leakage statement, reaffirms ZTF/Fink/SNAPS as
  reference-only, and records the pretrained-model-audit requirement as not
  yet applicable.
- Finding: TESS's `fetch_tess_ffis` returns TIC catalog star positions, not
  genuine FFI difference-image detections — `preprocess.py` has no FFI source
  extraction. `Skills/run_pipeline.py` now warns operators when `--surveys
  DECam` or `--surveys TESS` is selected.
- **NEXT PRODUCTION ACTION — NOT YET DONE**: work Gate P3 — run an end-to-end
  no-submission package drill from a Gate P1 positive-control packet through
  `Skills/adversarial_review.py`, operator review packet generation, and
  `Skills/export_ades_report.py`, verifying no external submission occurs.

**Gate P1 CLOSED (2026-07-02)**:
- `Skills/injection_recovery.py --survey WISE` injects a source-native
  NEOWISE-visit-cadence synthetic tracklet through the real production
  `detect.py` discovery-archive singleton path, `link.py`, `classify.py`, and
  `score.py`.
- Verified 100% detection/link/score rate (n=50, seed=42); baseline committed
  at `data/injection_recovery_wise_baseline.json`; CI job `wise-injection`
  fails closed if recovery drops to zero.
- Evidence:
  `docs/evidence/prod-loop/2026-07-02-gate-p1-wise-injection-recovery.md`.
- **NEXT PRODUCTION ACTION — NOT YET DONE**: work Gate P2 by documenting
  quantitative WISE/DECam/TESS confidence thresholds so archive candidates do
  not rely on absent ZTF-style real/bogus evidence. Gate P2 must also fold in
  the discovery-agent brief's source-verification matrix, no-future-catalog
  leakage rule, and pretrained-model audit requirement.

**v0.90.5 patch status**:
- `Skills/select_survey_fields.py --wise-archive-probes` now enriches ranked
  field selections with dry-run WISE/NEOWISE scale-plan probe commands. These
  commands use `caffeinate -i`, `uv run --python 3.14`, bounded native
  numerical thread settings, `--surveys WISE`, `--force-refresh`, and
  `--link-scale-plan-out`.
- This is the next D1 path after Taurus exhaustion: use the selector to choose a
  new non-Taurus parent field/window and run a scale-plan probe before any full
  diagnostic. Do not hand-pick new WISE coordinates without either selector
  output or a documented field-window rationale.
- Generated commands are dry-run only and do not authorize external submission.
  Run adversarial review only after a pipeline run reports a non-zero full
  `ScoredNEO` review-packet count.
- The selector-generated non-Taurus parent field was live-probed from merged
  `main`: RA `209.64`, Dec `-15.0`, radius `0.2`, JD `2458880.5` to
  `2459250.5`, survey `WISE`. It fetched `16582` WISE rows, passed
  `16558/16582`, detected `16558` singleton candidates, and stopped
  fail-closed at `27845455` estimated seed pairs over the `1000000` budget.
  Durable evidence:
  `docs/evidence/live/2026-06-30-wise-v0905-parent-field-probe.md`.
- The rank 1 v0.90.5 support-positive subfield was then run from merged
  `main`: RA `209.5`, Dec `-14.9`, radius `0.0303`. It fetched `690` WISE
  rows, passed `686/690`, detected `686` singleton candidates, linked `58596`
  seed pairs, and produced `0` tracklets and `0` review packets. The pipeline
  correctly instructed the operator to skip adversarial review. This is valid
  diagnostic evidence, not a crash; it is historical context for why the v0.90.6
  WISE positive-control harness was needed to close Gate P1.
- This historical v0.90.5 diagnostic no longer blocks Gate P1; the v0.90.6 WISE
  positive-control harness closed P1. Do not ask the operator for another live
  WISE run until Gate P2 supplies a measured, non-guesswork confidence policy.

**v0.90.4 patch status**:
- `detect.py`, `link.py`, and `Skills/audit_real_run.py` now share the
  adversarial-review hard lower motion floor of `0.05 arcsec/hr`. This prevents
  WISE near-stationary associations from producing review packets that are
  guaranteed to fail D1 on motion-rate grounds.
- `src/background.py` now lazy-loads classify/orbit/score stages so
  metadata-only background CLI commands avoid cold-start subprocess timeouts.
- The Taurus v0.90.3 diagnostic subfields remain exhausted; do not rerun them.
  The next D1 blocker is either a new WISE/NEOWISE field-window strategy likely
  to produce faster non-static candidates, or a defensible WISE-native
  real/bogus/quality policy for archive detections.

**v0.90.3 patch status**:
- `Skills/run_pipeline.py --review-packet-out` now prints the number of full
  `ScoredNEO` packets written. If the count is zero, it prints a fail-closed
  operator instruction to skip adversarial review because an empty packet file
  is not reviewable input.
- `Skills/run_pipeline.py --link-scale-plan-out` now ranks recommended
  diagnostic subfields by local cross-night seed-pair support and records
  `support_metrics` for each recommendation, including whether the subfield can
  support at least three observations across at least two nights inside the
  recommended diagnostic radius.

**v0.90.2 patch status**:
- WISE/NEOWISE ADES export is fail-closed: `stn=C51` requires written MPC
  confirmation, and ADES note `Z` is emitted for this non-survey archival
  remeasurement pipeline.
- `Skills/run_pipeline.py --link-scale-plan-out` writes top night-pair and
  sky-cell diagnostics when the link seed-pair budget fails closed, including
  a budget-derived diagnostic radius and recommended subfield parameters.
- Operator scale-plan probe result: `11786731` estimated seed pairs over the
  `1000000` default budget. Dominant night pairs are `2459084/2459085`
  (`9102120`) and `2459243/2459244` (`2503474`).
- The v0.90.2 scale-plan probe on `main` regenerated the full-window stop and
  emitted `recommended_diagnostic_subfields`; durable evidence is
  `docs/evidence/live/2026-06-29-wise-v0902-scale-plan-subfields.md`.
  First subfield: RA `58.1`, Dec `20.1`, radius `0.0466`, JD
  `2458880.5` to `2459250.5`, survey `WISE`.
- The first verified subfield was run by the operator. It fetched `532` WISE
  rows, passed `531/532`, detected `531` singleton candidates, linked `25053`
  seed pairs across `4` nights, and formed `0` tracklets. Candidate and
  review-packet outputs were empty arrays (`[]`). Durable evidence:
  `docs/evidence/live/2026-06-29-wise-v0902-subfield-diagnostic.md`.
- Important correction: do not run `Skills/adversarial_review.py` on
  `--review-packet-out` files until confirming the file contains at least one
  full `ScoredNEO` entry. The first subfield's adversarial-review command
  failed correctly with `ERROR: no valid ScoredNEO entries found in input`
  because no tracklets meant no reviewable packets.
- Expected seed-budget stops now exit cleanly with audit/output artifacts, not
  unhandled tracebacks.
- **NEXT PRODUCTION ACTION — NOT YET DONE**: do not rerun the RA `58.1`, Dec
  `20.1`, radius `0.0466` subfield. The v0.90.3 scale plan has been
  regenerated and recorded at
  `docs/evidence/live/2026-06-30-wise-v0903-scale-plan-support.md`. The next
  verified diagnostic was run: RA `58.1`, Dec `19.9`, radius `0.0466`. It
  produced `701` WISE rows, `3` tracklets, `3` full review packets, and `3/3`
  offline adversarial `REJECT` verdicts. Durable evidence:
  `docs/evidence/live/2026-06-30-wise-v0903-subfield-58p1-19p9.md`.
  The rank 2 support-positive diagnostic was also run: RA `57.9`, Dec `20.1`,
  radius `0.0466`. It produced `691` WISE rows, `2` tracklets, `2` full review
  packets, and `2/2` offline adversarial `REJECT` verdicts. Durable evidence:
  `docs/evidence/live/2026-06-30-wise-v0903-subfield-57p9-20p1.md`.
  The final remaining distinct support-positive diagnostic was then run: RA
  `57.9`, Dec `19.9`, radius `0.0466`. It produced `668` WISE rows, `2`
  tracklets, `2` full review packets, and `2/2` offline adversarial `REJECT`
  verdicts. Durable evidence:
  `docs/evidence/live/2026-06-30-wise-v0903-subfield-57p9-19p9.md`.
  **NEXT PRODUCTION ACTION — NOT YET DONE**: do not rerun the Taurus v0.90.3
  diagnostic subfields. The support-positive Taurus loop produced either zero
  tracklets or only adversarial `REJECT` candidates. Move D1 forward by
  selecting a new WISE/NEOWISE field-window strategy likely to produce faster,
  non-static candidates, or by improving WISE-specific filtering/linking before
  the next operator live run.

**Goal: defensible discovery paper** (operator-confirmed 2026-06-26 by Jerome W. Lindsey III).
Two-stage review before any external submission:
  1. `Skills/adversarial_review.py` — automated adversarial challenges try to REJECT
  2. Operator (Jerome) reviews survivors
  3. MPC submission → provisional designation → independent confirmation → journal paper

**Discovery fetch layer complete (PR #119, 2026-06-27)**:
- `fetch_wise_archive`: IRSA `neowiser_p1bs_psd` cone search; MJD→JD; disk-cached
- `fetch_decam_archive`: NOIRLab NSC DR2 via pyvo TAP; disk-cached
- `fetch_tess_ffis`: MAST `Observations.query_criteria()` + TIC catalog; BTJD→JD; disk-cached
- `fetch_discovery`: routing enforcer — raises `ValueError` for ZTF/ATLAS inputs
- `Mission` literal extended: `"TESS"`, `"DECam"`, `"WISE"` added
- `run_pipeline.py` default changed to `--surveys WISE`
- 1573 tests; 100% coverage; CI green on Python 3.14 ✓

**Adversarial review implemented (v0.89.3, PR #116/117)**:
`Skills/adversarial_review.py` — 13 challenges + 2 live checks.
Verdicts: SURVIVE / BORDERLINE / REJECT. Exit codes 0/1/2.
Tests: `tests/test_adversarial_review_skill.py` (50+ cases).

**PR #131 merged (2026-06-28)**:
- Discovery sweeps now fail closed for live MPC submission unless
  `NEO_MPC_SUBMISSION_APPROVED=1` is set with a real non-placeholder MPC
  observatory code.
- The Taurus WISE run evidence is durable at
  `docs/evidence/live/2026-06-27-wise-live-sweep.md`: `111913` IRSA rows,
  `85335` parsed observations, `535` moving-object candidates, `0` linked
  tracklets.
- WISE masked photometry values are handled as missing-data sentinels instead
  of being converted to `nan`.
- Do not ask the operator to repeat the same Taurus sweep.

**PR #133 merged (2026-06-28)**:
- Root cause of the Taurus `535` candidates -> `0` tracklets result: WISE fetch
  queried the broad static NEOWISE point-source population, then `detect()`
  required same-night pairs before `link()` saw archive rows.
- WISE ADQL now narrows rows with official IRSA association columns (`sso_flg`,
  `allwise_cntr`, `n_allwise`, `source_id`) and preserves prefiltered
  WISE/DECam/TESS archive rows as singleton candidates for multi-night linking.
- Validation: operator targeted run on Python 3.14.3 passed (`80 passed in
  0.86s`; targeted ruff clean; mypy clean across 12 source files). CI initially
  failed only on missing helper coverage; coverage test added, full local
  pytest passed (`1586 passed, 2 deselected`), and GitHub CI passed before
  merge.
- Evidence: `docs/evidence/live/2026-06-28-wise-linking-root-cause.md`.
- Follow-up diagnostic from `main` at `2a786e18` reached WISE pyvo polling but
  failed before result retrieval with `AttributeError: 'AsyncTAPJob' object has
  no attribute 'update'`. Root cause: pyvo 1.9.0 exposes `_update()`/`wait()`,
  not public `update()`. Evidence:
  `docs/evidence/live/2026-06-28-wise-prefilter-diagnostic-pyvo-update.md`.
- This pyvo blocker was closed by PR #135.

**PR #135 merged (2026-06-28)**:
- WISE TAP polling is now compatible with pyvo 1.9.0: the poll loop uses public
  `update()` when available, falls back to one-shot `_update()`, and preserves
  explicit heartbeat output.
- Post-merge smaller diagnostic from `main` at `dd35a8c0` completed:
  `5206` WISE rows, `5200/5206` preprocessed, `5200` singleton candidates,
  `0` linked tracklets, `0` candidates processed, dry-run safety intact.
- Evidence:
  `docs/evidence/live/2026-06-28-wise-prefilter-diagnostic-post-pyvo.md`.
- NOT YET DONE: diagnose why current WISE archive singleton candidates do not
  link into multi-night tracklets. Do not rerun the same 1.0°/7-day Taurus
  diagnostic until that diagnosis is recorded and a distinct fix or selection
  change is ready.

**PR #136 merged (2026-06-28)**:
- Linker provenance now records nights, observations, total seed pairs,
  rate-window seeds, satellite rejects, min-observation/min-night rejects, and
  chi-square rejects. Zero-tracklet runs persist these counters in
  `checkpoint.json` and print them when seed pairs exist.
- Operator validation before merge: targeted pytest `80 passed`, ruff clean,
  mypy clean. GitHub CI passed before merge.
- Post-merge bounded WISE rerun from `main` at `b8ca1312`: `5206` rows,
  `5200/5206` preprocessed, `5200` candidates, `0` tracklets.
  Link diagnostics: `n_nights=1`, `n_seed_pairs_total=0`.
- Evidence:
  `docs/evidence/live/2026-06-28-wise-linker-diagnostics-one-night.md`.
- NOT YET DONE: select or probe a WISE field/window that spans at least two
  integer-JD nights after preprocessing. Do not rerun the same 1.0°/7-day
  Taurus diagnostic; it is proven to be a one-night sample.

**WISE window probes after PR #136 (2026-06-28)**:
- 1.0° Taurus, 30 days: `5206` observations on one night (`2458883`).
- 1.0° Taurus, 195 days: `5206` observations on one night (`2458883`).
- 1.0° Taurus, 370 days: `328022` observations on eight nights, too large for
  the next full pipeline diagnostic.
- 0.2° Taurus, 370 days: `12061` observations on six nights
  (`2458883`, `2459084`, `2459085`, `2459242`, `2459243`, `2459244`).
- Evidence: `docs/evidence/live/2026-06-28-wise-window-night-probes.md`.

**WISE cap-2000 dry run (2026-06-29)**:
- Evidence: `docs/evidence/live/2026-06-29-wise-cap2000-dry-run.md`.
- The selected 0.2° Taurus full-year window is data-viable: `12061` WISE rows,
  `12042/12061` valid sources, and multi-night tracklets can form.
- The uncapped `12042`-candidate all-pairs linker path projected tens of
  minutes and was intentionally interrupted; do not rerun it as the next
  diagnostic.
- The explicit bounded run with `--max-candidates 2000` completed in `35.32s`,
  linked `243289` seed pairs, produced `19` tracklets, processed `19`
  candidates, and found `0` submission-ready candidates.
- `Skills/adversarial_review.py` now fails closed on compact pipeline summary
  rows. The cap-2000 output produced `19/19` structured `REJECT` verdicts
  because the output rows are not full `ScoredNEO` review packets.
- `run_pipeline.py --review-packet-out` was then added and live-validated on
  the same bounded WISE diagnostic. The rerun wrote `21` full `ScoredNEO`
  packets; offline adversarial review produced `21/21 REJECT` verdicts with
  fatal `orbit_quality`, `real_bogus`, `artifact_posterior`, and
  `neo_dominance` challenges. No candidate advanced to operator review.
- `run_pipeline.py --max-link-seed-pairs` now fails closed before the linker
  when estimated all-pairs seed work exceeds the configured budget
  (default `1000000`; set `0` only for a documented override).
- NEXT CODE ACTION: address WISE-scale linking with a scale-aware strategy or
  explicit tiling plan before attempting uncapped 12k-candidate runs.

Keep discovery sweeps in alert dry-run mode. Live archive fetching does not
require `--no-dry-run`; actual MPC submission remains fail-closed until the
MPC observatory-code path is resolved and `NEO_MPC_SUBMISSION_APPROVED=1` is
set with a real non-placeholder observatory code.

**Two human-gated blockers remain**:
1. MPC observatory code strategy — Jerome must resolve before any submission.
   See `docs/MPC_SUBMISSION_POLICY.md §TODO for Future Agents — Archival WISE Submission Authority`.
2. Actual candidate discovery — pipeline must find a survivor before paper is possible.

**Progress tracker**: `docs/evidence/prod-loop/LOOP_PROGRESS.md` — read
at session start to avoid repeating completed work.

### Handoff notes (2026-06-22) — v0.89.1

**ZTF fetch ndet cap fix (PR #115, merged 2026-06-22)**: Root cause of 0
tracklets (live Runs 3–5) was `_fetch_ztf_alerce_api` Mode 1 using
`ndet_max=None`, which returned persistent stationary sources whose detections
are all at the same sky position. Mode 1 now uses `ndet_max=3,
order_mode="ASC"` to surface single-detection transients (the moving-object
signature). `max_objects` increased 50→200. Two regression tests added.
Evidence: `docs/evidence/live/2026-06-22-ndet-cap-root-cause.md`.

**Adversarial test fixes (PR #115, merged 2026-06-22)**:
- `compute_streak_metric` now returns `None` (not `0.0`) for observations with
  no cutout — correct sentinel for "cannot determine streak status".
  `filter_by_streak_score` updated to skip `None` values.
- `OrbitQualityCode` extended to include `0` (degenerate/no-orbit sentinel);
  `compute_moid` already returned `None` for `quality_code < 1`.
- `test_very_fast_neo_links` adds a 4th observation on night 3 so the linker
  propagation loop has a third night to visit (seed pair uses nights 1+2;
  propagation skips night_a and night_b).
- `test_short_arc_blocks_submission` adds `sys.path` manipulation to import
  `conftest.build_scored_neo` outside the pytest root path.
- `test_run_pipeline_resumes_from_checkpoint` patches `ready_for_submission`
  to prevent MagicMock vs int comparison failure.

**Historical next live run (SUPERSEDED — do NOT run for discovery)**:
```bash
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/run_pipeline.py \
    --ra 284.13 --dec -22.5 --radius 3.5 \
    --start-jd 2461183.0 --end-jd 2461213.0 \
    --surveys ZTF --no-dry-run --force-refresh --no-resume
```
Expected: `ndet≤3` asteroid-classified OIDs → single-night transients at
unique sky positions → linker forms seed pairs with real solar system motion
rates → tracklets appear.

### Handoff notes (2026-06-17) — historical T1-C context

**What is now true for T1-C**:
- The original zero-alert diagnosis has been superseded. Public ALeRCE-backed
  ZTF source detection is working and has produced non-zero real data.
- The Orion pilot run `011dd53aa7f4` is retained only as historical/debug
  evidence. Do not reuse Orion for the production recovery KPI.
- The next production run should target many recoverable known moving objects,
  preferably from `Skills/select_survey_fields.py --mode recovery`, then audit
  against a manifest containing MPC designations plus sky/time samples.
- `Skills/audit_real_run.py` is the fail-closed promotion gate. It must verify
  >=90% known-object recovery and require operator review before
  internal production promotion is allowed. It never authorizes MPC submission,
  NASA notification, or any impact-probability statement.

**How to load credentials on operator Mac (NEVER use bare env vars)**:
```bash
source Skills/verify_live_credentials.sh   # loads ATLAS_TOKEN, ZTF_IRSA_USERNAME, ZTF_IRSA_PASSWORD
```
The script uses `security find-generic-password -s "neo-detection:ATLAS_TOKEN" -w`
(full string as service name, no `-a` flag). Do NOT use `-s neo-detection -a ATLAS_TOKEN`.

**Operator recovery-field selection command**:
```bash
git pull origin main
PYTHONPATH=src uv run --python 3.14 python Skills/select_survey_fields.py \
  --jd now \
  --mode recovery \
  --top-n 10 \
  --history-dir Logs/pipeline_runs \
  --json
```

### Skills

| Script | Purpose |
|---|---|
| `Skills/smoke_test.py` | Happy-path check for all modules; exits 0 on success |
| `Skills/evaluate_calibration.py` | Brier/ECE evaluation for Platt and isotonic calibrators |
| `Skills/generate_training_labels.py` | Download Tier 1 labels or build the approved four-class MPC Tier 3 pilot manifest |
| `Skills/download_ztf_training_alerts.py` | Download labeled ZTF Avro alert tarballs from public archive (ztf.uw.edu); decompresses gzip-FITS cutouts; writes `data/ztf_labeled_alerts.json`; run from Mac with `caffeinate -i` |
| `Skills/batch_score.py` | Score a list of tracklets from a JSON file; print ranked table |
| `Skills/run_pipeline.py` | Full end-to-end pipeline run |
| `Skills/injection_recovery.py` | Injection-recovery test: injects synthetic NEOs, measures detection/link/score rates |
| `Skills/check_mpc_known.py` | Cross-match candidate observations against MPC known object catalog |
| `Skills/build_recovery_manifest.py` | Build checkpointed MPC+Horizons expected-known manifests for T1-C recovery audits |
| `Skills/visualize_tracklets.py` | Plot sky positions and light curves for a tracklet JSON file |
| `Skills/export_mpc_report.py` | Export MPC 80-column reports from a scored NEO JSON file |
| `Skills/benchmark_pipeline.py` | Time classify + score on N synthetic tracklets; print throughput table |
| `Skills/train_tier1_xgboost.py` | Train Tier 1 XGBoost on ZTF alerts + MPC labels; saves `models/tier1_xgb.json`; run from Mac with `caffeinate -i` |
| `Skills/train_tier2_cnn.py` | Fine-tune CNN on labeled ZTF cutout CSV; saves `models/tier2_cnn.pt` |
| `Skills/train_tier3_transformer.py` | Train Transformer on MPC tracklet CSV; saves `models/tier3_transformer.pt` |
| `Skills/tune_linker.py` | Parametric sweep of `position_tolerance_arcsec` × `chi2_threshold` vs link/score rate |
| `Skills/background.py` | Unified background automation CLI with run, readiness, live dry-run, summary, detail, history, and signoff subcommands |
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
| `Skills/compute_orbital_energy.py` | Batch orbital energy computation; bound/parabolic/hyperbolic label; `--json` flag |
| `Skills/assess_survey_coverage.py` | Survey field coverage report (area, limiting mag, source count, fields per night); `--json` flag |
| `Skills/grade_tracklets.py` | Batch-grade tracklets from JSON (A/B/C/D) using arc, nights, and astrometric RMS; `--json` flag |
| `Skills/query_mpc_observations.py` | Inspect one MPC history or collect a bounded, resumable, versioned Tier 3 raw sequence dataset |
| `Skills/compute_threat_scores.py` | Batch-compute threat scores for ScoredNEOs from JSON; `--threshold` and `--json` flags |
| `Skills/fetch_atlas_data.py` | Fetch ATLAS forced photometry for a sky position; `--token`, `--force-refresh`, `--json` flags |
| `Skills/plot_calibration.py` | Plot reliability diagram from scored NEO or prob/label JSON; saves PNG; prints Brier/ECE/log-loss |
| `Skills/export_survey_summary.py` | Export per-candidate detection summary from pipeline run JSON to CSV or HTML |
| `Skills/compute_apparent_magnitudes.py` | Batch apparent magnitude at JD from tracklet JSON; `--jd`, `--albedo`, `--json` flags |
| `Skills/triage_candidates.py` | Urgency-sorted triage table from scored NEO JSON; `--urgency`, `--pathway`, `--json` flags |
| `Skills/compute_discovery_scores.py` | Batch discovery score table from scored NEO JSON; `--threshold`, `--sort`, `--json` flags |
| `Skills/format_submission_checklists.py` | Submission checklists for candidates above `--min-priority`; `--json` flag |
| `Skills/validate_pipeline_run.py` | Validate pipeline run JSON for required keys, MOID plausibility, and no impact-probability phrases; `--json` flag |
| `Skills/export_atlas_lightcurve.py` | Export ATLAS forced-photometry lightcurve for a sky position; `--format png\|csv\|json`, `--out`, `--token`, `--force-refresh` flags |
| `Skills/analyze_field_detections.py` | Field-level detection statistics and mission/filter breakdowns; `--json` flag |
| `Skills/compute_eccentric_anomaly.py` | Batch eccentric anomaly table from tracklet JSON; `--json` flag |
| `Skills/compute_true_anomaly.py` | Batch true anomaly table from tracklet JSON; `--json` flag |
| `Skills/export_candidate_dossiers.py` | Export conservative per-candidate dossier files; `--out-dir`, `--json` flags |
| `Skills/compute_combined_priority.py` | Batch combined candidate priority values; `--json` flag |
| `Skills/fetch_recent_neos.py` | Fetch recent MPC NEO observations; `--days`, `--force-refresh`, `--json` flags |
| `Skills/compute_weighted_priority.py` | Batch weighted priority scores; `--json` flag |
| `Skills/estimate_field_completeness.py` | Estimate field completeness from limiting magnitude and source counts; `--json` flag |
| `Skills/compute_orbital_inclination_class.py` | Batch orbital inclination class labels; `--json` flag |
| `Skills/compute_tier1_score_distribution.py` | Summarize Tier 1 score distributions; `--json` flag |
| `Skills/compute_mean_anomaly.py` | Batch mean anomaly at target JD; `--json` flag |
| `Skills/compute_weighted_hazard_scores.py` | Batch weighted hazard scores; `--json` flag |
| `Skills/compute_hazard_grades.py` | Batch hazard grade labels; `--json` flag |
| `Skills/compute_orbital_velocity.py` | Batch orbital velocity estimates; `--json` flag |
| `Skills/compute_priority_ranks.py` | Rank candidates by discovery priority; `--json` flag |
| `Skills/export_ades_report.py` | Export MPC ADES PSV reports for scored candidates |
| `Skills/compute_aphelion_distances.py` | Batch aphelion distance estimates; `--json` flag |
| `Skills/generate_night_summary.py` | Generate per-night observation summary tables; `--json` flag |
| `Skills/compute_risk_scores.py` | Batch weighted risk scores; `--json` flag |
| `Skills/compute_variability_indices.py` | Batch variability indices for observations; `--json` flag |
| `Skills/compute_field_overlap.py` | Compare survey field overlap between fetch results; `--json` flag |
| `Skills/compute_hazard_summary.py` | Aggregate hazard summary across scored candidates; `--json` flag |
| `Skills/fetch_known_phas.py` | Fetch known PHA records with cache support; `--force-refresh`, `--json` flags |
| `Skills/find_longest_tracklet.py` | Find the longest tracklet in a tracklet JSON file; `--json` flag |
| `Skills/get_top_candidates.py` | Top-N candidates by discovery priority from scored NEO JSON; `--n`, `--json` flags |
| `Skills/load_credentials.py` | Load ATLAS/ZTF credentials from macOS Keychain into env vars; used by `fetch_atlas_data.py` |
| `Skills/validate_model_weights.py` | Load all four committed model files and assert valid calibrated output on synthetic fixtures; used by model-weights CI job |
| `Skills/validate_alert_protocol.py` | Run `ready_for_submission()` on 14 diverse synthetic NEOs and assert correct gate behavior; `--json` flag |

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
| `docs/MPC_SUBMISSION_POLICY.md` | **MANDATORY READ before touching alert.py or submission logic.** Operator-approved policy (2026-06-21): MPC/NEOCP/Scout is the expert review system; submission gates in `ready_for_submission()` are the correct bar; no in-house expert required. |
| `docs/CLASSIFICATION_GUIDE.md` | Technical reference for three-tier ML classification, morphology, ensemble stacking, calibration, and conservative classification policy |
| `docs/QUALITY_METRICS.md` | Reference for all pipeline quality metrics: detection, astrometric, photometric, orbital, calibration, and hazard scoring |
| `docs/THREAT_ASSESSMENT.md` | Technical reference for threat score formula, components, interpretation guidelines, and CLI usage |
| `docs/DETECTION_GUIDE.md` | Technical reference for detect.py: RB threshold, streak detection, clustering, known-object matching, detection efficiency, DetectionSummary |
| `docs/LINKING_GUIDE.md` | Technical reference for link.py: tracklet formation, arc statistics, satellite trail rejection, deduplication, quality grades |
| `docs/FETCH_GUIDE.md` | Technical reference for fetch.py: ZTF/ATLAS/MPC/Horizons retrieval, caching, depth estimation, survey merging, filtering |
| `docs/PREPROCESS_GUIDE.md` | Technical reference for preprocess.py: difference image quality, photometry, astrometric calibration, SNR, scatter, zero-point |
| `docs/CALIBRATION_GUIDE.md` | Technical reference for calibration helpers and metrics |
| `docs/SCORING_MODEL_V2.md` | Updated scoring model reference for newer priority and close-approach helpers |
| `docs/ORBIT_DYNAMICS.md` | Technical reference for orbital dynamics helper APIs |
| `docs/CALIBRATION_METRICS.md` | Calibration metric definitions and review guidance |
| `docs/DETECTION_STATISTICS.md` | Detection-statistics helper reference |
| `docs/HAZARD_SCORING.md` | Hazard scoring helper reference |
| `docs/ORBITAL_MECHANICS.md` | Orbital mechanics helper reference |
| `docs/SCORING_REFERENCE.md` | Expanded scoring helper reference |
| `docs/CLASSIFICATION_FEATURES.md` | Classification feature helper reference |
| `docs/DATA_PIPELINE_OVERVIEW.md` | End-to-end data pipeline overview |
| `docs/ALERT_PATHWAY_GUIDE.md` | Alert pathway helper and guardrail guide |
| `docs/SCHEMA_REFERENCE.md` | Schema model reference |
| `docs/CONSOLE_OUTPUT_SPEC.md` | **Console output standard for all pipeline runners.** Stage prefixes, ETA format, run header/footer, candidate escalation notice. `Skills/run_pipeline.py` is compliant as of 2026-06-21. |

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

### Coverage by Module (v0.88.0)

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

### Operational Milestone Status

| Milestone | Status | Description |
|---|---|---|
| 4 (partial) | LIVE ✓ | First ZTF live run complete (2026-06-21). Scheduler policy in `background/config.json`. |
| 5 | DONE ✓ | Tier 2 CNN trained (`models/tier2_cnn.pt`; val_acc=91.3%) |
| 6 | DONE ✓ | Tier 3 Transformer trained (`models/tier3_transformer.pt`; val_macro_f1=0.9400) |
| 7 | DONE ✓ | Ensemble calibration KPIs all pass (AUC=0.9809, Brier=0.0211, ECE=0.0000) |

### Immediate Next Steps

**No autonomous code work remains.** All T1/T2 production gaps are closed as of
2026-06-22. The pipeline is ready for discovery-paper operation against unreviewed archives.

**One human-gated blocker**:
- **MPC observatory code / escalation path**: Jerome must decide whether and how to
  obtain an observatory code to submit MPC reports. See
  `docs/MPC_SUBMISSION_POLICY.md §TODO for Future Agents — Archival WISE Submission Authority`.
  The pipeline prints an escalation notice for submission-ready candidates but makes
  no actual submission until this is resolved.

**When Jerome resolves the observatory code strategy**:
1. Update `docs/MPC_SUBMISSION_POLICY.md` §TODO for Future Agents with the answer.
2. Update `alert.py` to perform the actual submission in `run_pipeline.py`.
3. Update `Skills/export_ades_report.py` `--obs-code` default to the assigned code.

**Historical next live run (SUPERSEDED — do NOT run for discovery)**:
```bash
git pull origin main
source Skills/verify_live_credentials.sh
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/run_pipeline.py \
    --ra 284.13 --dec -22.5 --radius 3.5 \
    --start-jd 2461183.0 --end-jd 2461213.0 \
    --surveys ZTF --no-dry-run --force-refresh --no-resume
```

**Background automation (lower priority)**:
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
- Added `Skills/fetch_known_phas.py`, `Skills/find_longest_tracklet.py`, and `docs/SCHEMA_REFERENCE.md`.
- 2083 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.50.0.

### Key Changes in v0.49.0

- Added 10 public APIs for mission counts, calibration error, class probability ranges, angular separation, field overlap, tracklet completeness, orbital arc quality, cutout peak positions, and hazard summaries.
- Added `Skills/compute_field_overlap.py`, `Skills/compute_hazard_summary.py`, and `docs/ALERT_PATHWAY_GUIDE.md`.
- Version bumped to 0.49.0.

### Key Changes in v0.48.0

- Added 10 public APIs for NEOCP submission formatting, calibration uniformity, posterior stability, variability, MPC orbit catalogs, sky density, Earth Tisserand parameter, compactness, tracklet clusters, and weighted risk.
- Added `Skills/compute_risk_scores.py`, `Skills/compute_variability_indices.py`, and `docs/DATA_PIPELINE_OVERVIEW.md`.
- Version bumped to 0.48.0.

### Key Changes in v0.47.0

- Added 10 public APIs for discovery reports, calibration drift, Tier 1 confidence, brightness trends, NEOCP confirmations, motion summaries, aphelion distance, PSF asymmetry, night summaries, and survey completeness.
- Added `Skills/compute_aphelion_distances.py`, `Skills/generate_night_summary.py`, and `docs/CLASSIFICATION_FEATURES.md`.
- Version bumped to 0.47.0.

### Key Changes in v0.46.0

- Added 10 public APIs for ADES PSV export, reliability, posterior update, field source counts, known NEO lists, tracklet arc nights, perihelion distance, radial profiles, observation coverage, and priority ranks.
- Added `Skills/compute_priority_ranks.py`, `Skills/export_ades_report.py`, and `docs/SCORING_REFERENCE.md`.
- Version bumped to 0.46.0.

### Key Changes in v0.45.0

- Added 10 public APIs for observation logs, expected positive rate, NEO class distribution, cadence, MPC orbit elements, motion-rate filtering, orbital velocity, streak angle, residual summaries, and hazard grades.
- Added `Skills/compute_hazard_grades.py`, `Skills/compute_orbital_velocity.py`, and `docs/ORBITAL_MECHANICS.md`.
- Version bumped to 0.45.0.

### Key Changes in v0.44.0

- Added 10 public APIs for alert age, resolution score, class entropy summary, detection gaps, NEOCP objects, inter-night gaps, mean anomaly at JD, cutout symmetry, astrometric residuals, and weighted hazard scoring.
- Added `Skills/compute_mean_anomaly.py`, `Skills/compute_weighted_hazard_scores.py`, and `docs/HAZARD_SCORING.md`.
- Version bumped to 0.44.0.

### Key Changes in v0.43.0

- Added 10 public APIs for ready-to-submit counts, discrimination, Tier 1 score distributions, angular velocity, known NEO ephemerides, velocity dispersion, inclination class, image gradients, observation clusters, and arc-quality bonuses.
- Added `Skills/compute_orbital_inclination_class.py`, `Skills/compute_tier1_score_distribution.py`, and `docs/DETECTION_STATISTICS.md`.
- Version bumped to 0.43.0.

### Key Changes in v0.42.0

- Added 10 public APIs for bulk summaries, Brier skill score, class entropy stats, streak density, field completeness, night span, longitude of perihelion, cutout contrast, ephemeris points, and weighted priority.
- Added `Skills/compute_weighted_priority.py`, `Skills/estimate_field_completeness.py`, and `docs/CALIBRATION_METRICS.md`.
- Version bumped to 0.42.0.

### Key Changes in v0.41.0

- Added 10 public APIs for alert-flag counts, calibration sharpness, batch morphology, magnitude filtering, recent MPC NEO retrieval, tracklet quality, mean motion, pixel histograms, survey statistics, and combined priority.
- Added `Skills/compute_combined_priority.py`, `Skills/fetch_recent_neos.py`, and `docs/ORBIT_DYNAMICS.md`.
- Version bumped to 0.41.0.

### Key Changes in v0.40.0

- Added 10 public APIs for true anomaly, observation depth, position-angle consistency, calibration gain, close-approach scoring, candidate dossiers, Pan-STARRS moving objects, background level, candidate reports, and average precision.
- Added `Skills/compute_true_anomaly.py`, `Skills/export_candidate_dossiers.py`, and `docs/SCORING_MODEL_V2.md`.
- Version bumped to 0.40.0.

### Key Changes in v0.39.0

- Added 10 public APIs for eccentric anomaly, source extent, great-circle residuals, confusion matrices, size estimates, follow-up windows, CSS alerts, cutout entropy, orbital summaries, and F1 score.
- Added `Skills/compute_eccentric_anomaly.py`, `Skills/analyze_field_detections.py`, and `docs/CALIBRATION_GUIDE.md`.
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
- `Skills/compute_discovery_scores.py`: new — batch discovery score table; `--threshold`, `--sort`, `--json` flags.
- `Skills/format_submission_checklists.py`: new — submission checklists for candidates above `--min-priority`; `--json` flag.
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
- `Skills/compute_apparent_magnitudes.py`: new — batch apparent magnitude at JD from tracklet JSON; `--jd`, `--albedo`, `--json` flags.
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
- `Skills/compute_threat_scores.py`: new — batch threat score table from ScoredNEO JSON; `--threshold` and `--json` flags.
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
- `Skills/compute_orbital_energy.py`: new — batch orbital energy CLI; `--json` flag.
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
