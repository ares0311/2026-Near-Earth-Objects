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
- **Astrometrics policies are mandatory directives**:
  `docs/astrometrics_coding_agents_master_guide.md`,
  `docs/astrometrics_data_selection_policy.md`, and
  `docs/astrometrics_external_and_cloud_storage_policy.md` must be read before
  planning data acquisition, storage, training, scoring, evaluation,
  retrospective replay, live search, or submission-package work. Apply their
  repo-visible controls in `data_selection/` and `storage/`. Do not hand the
  operator guessed URLs, schemas, worker counts, shard layouts, or storage
  paths.
- **Astrometrics production roadmap is mandatory**:
  Work these gates in order unless the operator explicitly chooses a different
  production path: A1 dataset manifest system; A2 candidate ledger; A3 freeze
  the current CNN as `benchmark_cnn_v1`; A4 grouped NEO splits and leakage
  checks; A5 OpenAI-evals-style canonical regression suite; A6 parameterized
  injection-recovery curves; A7 calibration/promotion report. Do not promote a
  model, expand live search, or treat the CNN as production-promoted until the
  relevant A-gates close. The existing CNN may be used as an image/artifact
  feature source and benchmark, not as the main scientific thesis.
- **Repository artifact policy supports `git add .`**: The standard operator
  cadence may use `git add .`, so `.gitignore` must protect local/generated
  outputs by default. Treat `Logs/**` as local operational output and never
  commit it except explicit compact `Logs/reports/` evidence/manifests and
  the two `.gitkeep` placeholders. When run
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
- **Optimized sharded/multiprocess execution is the standing default wherever
  it safely applies**. All agents must prefer the single-command launchers
  below when work is independently divisible and they reduce wall time:
  - For a long data acquisition whose target Skill already implements native
    `--shard-index`, `--shard-count`, and `--workers` semantics, the agent must
    call `Skills/run_sharded_download.py` itself instead of asking the operator
    to maintain six terminal tabs. The default is **6 shards x 6 workers**.
    First run its `--dry-run`, provide `--estimated-download-gb`, verify the
    target's service limit/checkpoint/output isolation, and keep the projected
    project footprint below 100 GB. The launcher must not invent shard
    semantics for a target that lacks those native flags.
  - For a full or otherwise broad offline test pass, Codex should call
    `Skills/run_sharded_tests.py`, defaulting to **6 file shards x 6
    pytest-xdist workers** with `--dist=loadfile`. The runner owns disjoint
    test files and separate coverage data per shard, then combines coverage
    once and enforces the repository's 100% gate. Use a normal targeted pytest
    command when only a few tests are relevant, because launcher overhead
    would not improve wall time.
  - Do not run either launcher during an active Tier 3 operator run or beside
    another resource-heavy job. If a measured 6x6 run is slower, exhausts
    memory, or exposes a provider rate limit, reduce the explicit shard/worker
    counts to the last clean level and record why. Prefer an equivalent
    repo-native launcher in future workflows rather than recreating ad hoc
    terminal-tab orchestration.
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
  `Skills/run_sharded_tests.py` is the narrow local-validation exception to
  the committed git-relay requirement: one parent process directly owns every
  child, emits one fail-closed result, writes ignored logs and `summary.json`
  under `Logs/pipeline_runs/`, and deletes its small sandbox-temporary coverage
  databases after combining them. It must not auto-commit every local test run.
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
- **MCP servers, when configured/available**: prefer these over guessing or
  ad hoc web scraping — GitHub MCP for issues, PRs, remote branches, repo
  metadata, PR review notes, branch health, and PR links; Context7 MCP for
  current library/framework/API documentation instead of relying on
  training-data recall; arXiv MCP for preprint lookup and research context;
  NASA ADS MCP for astronomy/astrophysics literature, bibcodes, citations,
  references, metrics, and BibTeX export. This project also runs repo-scoped
  MCP tools (`neo_project_files`, `neo_git_read`, `neo_guard`, configured in
  `.mcp.json`) for bounded file reads, read-only git inspection, and fixed
  offline validation commands — prefer these over raw shell equivalents for
  read-only repo inspection.

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

# Broad local test pass: six disjoint file shards x six xdist workers, with
# isolated per-shard coverage data combined into the same 100% final gate.
UV_CACHE_DIR=.uv-cache caffeinate -i uv run --no-sync --python 3.14 python \
    Skills/run_sharded_tests.py

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

## Current State (v0.90.88)

**Latest sync (2026-07-13, single-command sharding)**: Added Codex-owned
single-command orchestration for native shard-aware downloads and broad offline
tests. `Skills/run_sharded_download.py` defaults to 6 shards x 6 workers, checks
the 100 GB conservative cache budget, requires exact native shard flags,
isolates logs, fails the whole batch on a child failure, and maintains a
file-locked status/finalize manifest. `Skills/run_sharded_tests.py` assigns
every test file to exactly one of 6 outer shards, runs 6 pytest-xdist workers
per shard with `--dist=loadfile`, isolates coverage files, combines them only
after all shards pass, and retains the 100% coverage gate. Codex should use
these launchers whenever measured wall time benefits and safety conditions are
met; small targeted checks remain serial.

**Latest sync (2026-07-12, tier2_cnn_v4 operator-approved)**: V4 now has
two validated training manifests (real ZTF plus the deterministic synthetic
hard-negative supplement), real CNN injection evidence bound to checkpoint
SHA-256, a 5/5-case and 25/25-check canonical suite, and a signed promotion
report with all nine evidence artifacts passing. Jerome W. Lindsey III
approved internal production promotion under signoff ID
`jlindsey-2026-07-12-tier2-cnn-v4`. The corrected harness exposed a material
tradeoff: all 14 scored
synthetic moving-source injections have `stellar_artifact` as v4's final
ensemble argmax, identical to `benchmark_cnn_v1` on this harness and more
conservative than v3 on 8/14 cases. V4 also closes v3's adversarial artifact
failure (0/200 versus 200/200 false discoveries) and passes all real-data
calibration KPIs. `tier2_cnn_v4` is now the internally promoted Tier 2
candidate; `benchmark_cnn_v1` remains the immutable historical benchmark.
This does not authorize live-search expansion or any external submission.

**Latest sync (2026-07-11, v0.90.85 — doc-sync only)**: Four commits landed
after this file's last sync without an AGENTS.md update; catching up here.
`1ca5fecc`/`736a81c5` add real dataset manifests for `models/tier1_xgb.json`
and `models/tier3_transformer.pt`'s training data, closing the last A1 gaps
(the Tier 3 manifest also documents a real trap: the top-level
`data/sequences/mpc_pilot.json` is the failed first pilot attempt — real
data is `data/sequences/tier3_pilot_v2/`). `41b47fc8` adds
`docs/evidence/promotion/tier2_cnn_v3_operator_review_packet.md`, a real
readable review packet (training result, all 8 A7 checks, calibration KPI
table, the one policy judgment call needing operator buy-in, known
limitations, attestation checklist) behind the `operator_signoff_missing`
blocker — read this before recording a signoff decision. `c2a02dac` makes
`--candidate-ledger-db` default-on in `Skills/run_pipeline.py` (A2), closing
a real gap where candidates could be produced with zero ledger provenance by
omitting a flag; also fixed a `--source-dataset-id="not-recorded"` footgun
that would have written fake provenance into the ledger. Full detail in
`CLAUDE.md`'s Current State. `operator_signoff_missing` remains the sole
A1-A7 blocker, now backed by a real review packet.

**Earlier sync (2026-07-10, v0.90.75)**: Fixed a real operator-reported bug:
`Skills/download_ztf_training_alerts.py` produced total console silence
during a download (operator killed it). Root cause: no `flush=True` on any
print, plus the tarball was read via one blocking `resp.content` call with
zero progress output. Fixed by porting the proven stream+progress+ETA
pattern already used in `Skills/ztf_alert_archive_ingest.py` (HEAD for
Content-Length, `_CountingReader` over `resp.raw`, byte-level progress every
200 scanned members, `flush=True` everywhere). See `CLAUDE.md`'s Current
State for the full root-cause writeup and predicted-output check.

**Latest sync (2026-07-10, v0.90.74)**: Fixed the acquisition-side root
cause behind A7's `grouped_split_report_missing` blocker (operator-confirmed
plan). `Skills/download_ztf_training_alerts.py` now captures real per-alert
`object_id`/`candid`/`jd`/`ra`/`dec`/`fid`/`field`/archive-night (verified
against a real packet, not guessed); `Skills/build_cutout_dataset.py`
propagates them; `Skills/train_tier2_cnn.py` replaces `random_split()` with
a genuine grouped train/validation/test split by `object_id`, plus
`--emit-split-csv` for a matching audit file. 26 new offline tests. This is
a **code fix only** — closing the blocker needs one operator-run
download+retrain; see `CLAUDE.md`'s Current State for the exact command
sequence (naming: produces a new candidate, not a silent overwrite of the
frozen `benchmark_cnn_v1`).

**Latest sync (2026-07-10, v0.90.73)**: A1 now has four real, committed
dataset manifests under `data_selection/dataset_manifests/`
(`ztf_labeled_alerts_tier2_cnn_v1`, `gate_z4_ranking_baseline_v1`,
`gate_z6_retrospective_validation_v1`,
`a6_injection_recovery_image_level_n200_v1`), each populated from computed
facts (checksums) or already-documented project history — never guessed.
Citing the training manifest in the A7 promotion report closes the
`dataset_manifest_missing` blocker for real: `benchmark_cnn_v1`'s promotion
report now shows 6/8 evidence checks passing with only **three** real named
blockers left (grouped-split report, calibration report, operator signoff),
down from four.

**Latest sync (2026-07-10, v0.90.72)**: A7's promotion-report builder has now
been run for real against `benchmark_cnn_v1`. New `Skills/extract_promotion_evidence.py`
derives an injection-recovery report and a false-discovery report from
already-committed real evidence (A6's image-level baseline and Gate Z4's
ranking-baseline review-burden counts: 0/200 false positives) without
inventing any data. `Skills/build_promotion_report.py` then produced a real,
committed report — `promotion_allowed=false` with 4 real named blockers
(dataset manifest, grouped-split report, calibration report, operator
signoff). Root-cause finding: `data/ztf_labeled_alerts.json` (the CNN's
committed 10,000-alert training source) never captured per-alert RA/Dec/JD
metadata, so a real grouped split cannot be reconstructed for it — this is
why A4/A1 remain open for the CNN's training set specifically, not a coding
gap. See `docs/PRODUCTION_READINESS.md` for detail.

**Latest sync (2026-07-09, v0.90.71)**: A6 now closes the image-level gap:
`Skills/injection_recovery.py --image-level` synthesizes a real
difference-image cutout per injection (Gaussian PSF + background noise +
trail elongation) and derives `real_bogus` from its analytic peak SNR, so
seeing/background/trail-length sweeps produce real, non-degenerate recovery
curves through the actual `detect()`/`link()`/`classify()`/`score()` chain.
A real n=200, seed=42 baseline is committed at
`data/injection_recovery_image_level_n200.json` (7.5% detection/link/score
rate). All five required A6 dimensions (magnitude, velocity, observation
count, night count, and now seeing/background/trail length) are covered. See
`docs/PRODUCTION_READINESS.md` for detail.

**Latest sync (2026-07-09, v0.90.70)**: A5 now has a frozen, policy-grade
canonical eval suite (`data_selection/canonical_evals/production_suite_v1.json`)
covering all four required case types, every case citing a real,
already-committed evidence artifact (the n=200 injection-recovery baseline,
the Gate Z4 ranking-baseline purity/ablation report, the Gate Z6
retrospective-validation report, and a real, unconfirmed Gate Z3 known-NEO
recovery attempt transcribed to
`docs/evidence/canonical_evals/known_neo_recovery_72966_no_match.json`). This
closes A5 for model-builder-independent regression protection; per-model
canonical suites remain part of A7. See `docs/PRODUCTION_READINESS.md` for
detail.

**Latest sync (2026-07-09, v0.90.69)**: All four model-builder Skills
(`train_tier1_xgboost.py`, `train_tier2_cnn.py`, `train_tier3_transformer.py`,
and `train_ensemble_stacker.py`) now share the same A4 fail-closed
`--grouped-split-report`/`--production-candidate` gate via a shared
`grouped_splits.load_grouped_split_gate` helper. `train_tier2_cnn.py` also
gained `--dry-run` (previously absent) so the gate can be checked without a
full CNN training run. This closes "broader model-builder adoption" from the
v0.90.68 note below; promotion-report wiring with real, model-specific
evidence packets remains open. See `docs/PRODUCTION_READINESS.md` for detail.

**Latest sync (2026-07-09, v0.90.68)**: The Astrometrics coding-agent,
data-selection, and external/cloud-storage policy docs are now mandatory
directives. Repo-local controls have started under `data_selection/` and
`storage/`. The active ZTF DR24 posture is unchanged from the latest gate
evidence: Z1, Z2, Z4, Z5, Z6, and Z7 are closed; Z3 is the only open gate and
its candidate-pair search remains intentionally paused unless the operator
explicitly restarts that path. The highest-priority non-blocked roadmap is now
A1-A7: dataset manifests, candidate ledger, frozen CNN benchmark, grouped
splits/leakage checks, canonical regression evals, injection-recovery curves,
and calibration/promotion reports. A1 now has a committed manifest schema and
validator; `Skills/run_pipeline.py` can now cite a source dataset ID in audit
summaries. A2 now has an initial SQLite candidate ledger schema/CLI plus
optional run-pipeline ingestion via `--candidate-ledger-db`. Both remain
partially open until policy-grade manifests cover every real dataset role and
operator production runs routinely use the manifest/ledger flags. A3's freeze
step is complete:
`benchmarks/benchmark_cnn_v1/` wraps `models/tier2_cnn.pt` with locked
preprocessing, config, score/train entrypoints, tests, and a model card. A4
now has initial grouped split/leakage controls in `src/grouped_splits.py` and
`Skills/validate_grouped_splits.py`; `Skills/train_ensemble_stacker.py` now
requires a passing grouped split report when `--production-candidate` is set.
Broader model-builder adoption and promotion report wiring remain open. A5 now
has a fail-closed canonical regression eval
engine in `src/canonical_eval.py` and `Skills/run_canonical_evals.py`; frozen
production suites covering known-NEO recovery, false links, injection-recovery,
and review-packet examples remain open. The CNN is still not
production-promoted under the new policy. A6 now has synthetic-harness recovery
curves by magnitude, motion rate, observation count, and night count; image-level
seeing/background/trail-length curves remain open. A7 now has a fail-closed
promotion packet builder in `src/promotion_report.py` and CLI wrapper in
`Skills/build_promotion_report.py`; real model-specific evidence packets still
need to be generated before any production promotion claim.

**This section was last synced 2026-07-02 through v0.90.27; the detail below
is historical and accurate as of that date but does not reflect
v0.90.28-v0.90.57.** For the full blow-by-blow, `CLAUDE.md`'s handoff section
is kept current every session; this paragraph gives the condensed delta so
AGENTS.md stays usable without reading all of CLAUDE.md.

**Delta since v0.90.27 (2026-07-02) through v0.90.57 (2026-07-04)**: Gate
Z3 (source-native candidate linking) had its real-detection-source blocker
resolved (UW ZTF public alert archive, confirmed reachable/schema-verified)
and its ingest/positive-control/matching tooling built and run for real
against four candidate-pair apparitions of designation 72966. Pipeline
mechanics (`preprocess()`->`detect()`->`link()`) are confirmed working
correctly on real archived ZTF data (546 real cross-night tracklets formed
across two full pairs), but no pair has yet produced a confirmed
single-object match — see `docs/ZTF_DR24_PRODUCTION_GATES.md` Gate Z3 row
for the full real-data trail. **The candidate-pair search is intentionally
paused**: after four attempts with no confirmation, the operator identified
this as a real doom-loop pattern and directed a pivot to evidence-only,
non-gambling work; do not propose a fifth apparition or a different NEO
designation without explicit operator direction. Gates Z2 (time-aware
known-object exclusion), Z6 (no-submission package drill), Z7 (operator
runbook update), Z4 (auditable ranking baseline), and Z5 (retrospective
validation) are all **CLOSED** (2026-07-04/05) with real data — see
`docs/ZTF_DR24_PRODUCTION_GATES.md`,
`docs/evidence/live/2026-07-04-gate-z4-z5-closed.md`, and
`docs/evidence/live/2026-07-05-gate-z2-first-obs-verified.md`. The only
remaining open ZTF DR24 gate is Z3 (paused, see above).


**Historical state and dated handoff notes (v0.90.27 and earlier, back
through the 2026-06-17 T1-C context)** are archived in
`docs/HANDOFF_HISTORY.md` under "AGENTS.md historical notes". Not required
session-start reading — consult only for historical context on a specific
gate or bug. This mirrors, but is not identical to, `CLAUDE.md`'s own
(more detailed) handoff archive for the same period.

### Skills

| Script | Purpose |
|---|---|
| `Skills/smoke_test.py` | Happy-path check for all modules; exits 0 on success |
| `Skills/evaluate_calibration.py` | Brier/ECE evaluation for Platt and isotonic calibrators |
| `Skills/generate_training_labels.py` | Download Tier 1 labels or build the approved four-class MPC Tier 3 pilot manifest |
| `Skills/download_ztf_training_alerts.py` | Download labeled ZTF Avro alert tarballs from public archive (ztf.uw.edu); decompresses gzip-FITS cutouts; writes `data/ztf_labeled_alerts.json`; run from Mac with `caffeinate -i` |
| `Skills/batch_score.py` | Score a list of tracklets from a JSON file; print ranked table |
| `Skills/run_pipeline.py` | Full end-to-end pipeline run |
| `Skills/select_survey_fields.py` | Algorithmically ranks sky fields for `Skills/run_pipeline.py` by known-object density, geometry, and novelty (`--mode recovery` for known-object-rich fields; `--wise-archive-probes` attaches ready-to-run WISE scale-plan commands); `--write-target-queue` appends real, computed selection results to `data_selection/target_priority_queue.csv` — the canonical way to pick a target field |
| `Skills/injection_recovery.py` | Injection-recovery test: injects synthetic NEOs, measures detection/link/score rates; `--image-level` sweeps seeing/background/trail-length via synthesized difference cutouts for A6 recovery curves |
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
| `data/injection_recovery_image_level_n200.json` | A6 image-level injection-recovery results (n=200, seed=42, `--image-level`): 7.5% detection/link/score with real per-bin seeing/background/trail-length recovery curves |
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

### Version-by-Version Changelog

See `CHANGELOG.md` (authoritative; updated on every version bump per the
"Sync docs and changelog" standing rule above) for the full v0.1.0-through-
current changelog. It is not duplicated in this file.
