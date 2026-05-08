# 🚀 2026 Near-Earth Object Detection & Ranking

![Status](https://img.shields.io/badge/status-active%20development-blue)
![License](https://img.shields.io/badge/license-Apache%202.0-green)
![Focus](https://img.shields.io/badge/focus-near--earth--objects-orange)
![Tests](https://img.shields.io/badge/tests-328%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)

---

## 🌌 Overview

A **research-grade, reproducible pipeline** for detecting, linking, classifying, and ranking Near-Earth Object (NEO) candidates from publicly available survey photometry — with MPC-compatible reporting and a NASA alert pathway for high-confidence hazard signals.

Primary data sources: **ZTF** (Zwicky Transient Facility), **ATLAS**, and the **Minor Planet Center (MPC)** catalog.

### Core Flow

```
Raw Survey Data → Preprocess → Detect → Link → Classify → Score → Alert
```

This project prioritizes:
- Scientific rigor and conservative classification
- Low false-positive rates via real/bogus filtering and MPC cross-matching
- Reproducibility — every result carries full provenance
- High-value candidates: Potentially Hazardous Asteroids (PHAs) with MOID ≤ 0.05 AU

---

## 🧠 Key Idea

Most moving sources are **not** new NEOs.

This system is built to **disprove signals first**, then elevate only the strongest candidates.

---

## 📊 Current Status

**Phase:** Foundation Complete — v0.9.0

- ✅ All 10 pipeline modules built and tested
- ✅ 328 tests passing (100% coverage) on Python 3.11 & 3.12
- ✅ CI green — lint, type-check, test, coverage
- ✅ MPC 80-column and JSON report formatting
- ✅ NASA PDCO alert protocol implemented
- ✅ Three-tier ML ensemble (XGBoost + CNN + Transformer + meta-learner)
- ✅ Injection-recovery baseline: 100% detect, 62% link (n=50, seed=42)
- ⏳ Live ZTF/ATLAS data integration (requires API tokens)
- ⏳ CNN image classifier training (requires labeled cutouts + GPU)
- ⏳ Transformer tracklet model training (requires multi-night dataset)

👉 See [`CLAUDE.md`](CLAUDE.md) for full version history and per-module detail

---

## 🛣 Roadmap

| Milestone | Description |
|---|---|
| 1 | Core pipeline (schemas → score) |
| 2 | Alert protocol & MPC report formatting |
| 3 | ML calibration + logistic regression ensemble |
| 4 | Live ZTF / ATLAS data integration |
| 5 | CNN image classifier — Tier 2 |
| 6 | Transformer tracklet model — Tier 3 |
| 7 | Ensemble calibration & injection-recovery tuning |

👉 See [`docs/PIPELINE_SPEC.md`](docs/PIPELINE_SPEC.md)

---

## ⚙️ Pipeline Architecture

```
Fetch → Preprocess → Detect → Link → Classify → Score → Alert
```

Each stage produces a typed, immutable result object. No shared mutable state.

| Module | Purpose |
|---|---|
| `fetch.py` | ZTF alert stream, ATLAS forced photometry, MPC catalog, JPL Horizons ephemerides |
| `preprocess.py` | Difference image validation, PSF quality checks, Gaia DR3 astrometric correction |
| `detect.py` | Real/bogus filter (rb ≥ 0.65), moving-source pairing, streak detection, MPC cross-match |
| `link.py` | THOR-inspired multi-night tracklet linking; ≥ 3 detections on ≥ 2 nights required |
| `classify.py` | Three-tier ML ensemble: XGBoost → CNN → Transformer → logistic regression stacker |
| `orbit.py` | Gauss method IOD, differential correction, MOID vs. Earth, NEO dynamical class |
| `score.py` | Hazard ranking, PHA flag, discovery priority, follow-up value, novelty score |
| `alert.py` | MPC 80-column / JSON report; mandatory three-step NASA PDCO alert protocol |
| `calibration.py` | Platt scaling and isotonic PAVA regression; Brier score and ECE evaluation |

### Three-Tier ML Architecture

| Tier | Method | Strength |
|---|---|---|
| Tier 1 | XGBoost on tabular features | Fast, interpretable; ~500 labeled examples sufficient |
| Tier 2 | CNN on 63 × 63 px image triplets (sci / ref / diff) | Proven real/bogus classifier (Duev et al., 2019) |
| Tier 3 | Transformer on observation sequences | Frontier multi-night classification (Lin et al., 2022) |
| Ensemble | Logistic regression stacker + Platt calibration | Best-of-all; falls back to weighted average without trained weights |

👉 See [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)

---

## 📐 Scoring Methodology

Classification uses a **Bayesian log-score model** over five mutually exclusive hypotheses.

### Posterior

```
P(Hᵢ | D) ∝ P(D | Hᵢ) · P(Hᵢ)
```

Implemented in log-space for numerical stability:

```
ℓᵢ = log P(Hᵢ) + Σₖ wᵢₖ · φₖ(D)

pᵢ = exp(ℓᵢ − ℓₘₐₓ) / Σⱼ exp(ℓⱼ − ℓₘₐₓ)
```

All features φₖ ∈ [0, 1]. Missing features contribute 0 (neutral — no penalty for absent data).

### Hypotheses & Priors

| Hypothesis | Prior | Rationale |
|---|---|---|
| `neo_candidate` | 0.05 | Most moving sources are not new NEOs |
| `known_object` | 0.30 | Large fraction of detections match the MPC catalog |
| `main_belt_asteroid` | 0.35 | MBAs dominate the moving-object population |
| `stellar_artifact` | 0.25 | Cosmic rays, satellites, and optical ghosts are common |
| `other_solar_system` | 0.05 | Comets, TNOs, and Centaurs are rare |

### Key Feature Weights

```
log_score_neo =
    log P(neo)
    + 2.0 · real_bogus_score          ← strongest signal of reality
    + 1.5 · arc_coverage_score        ← multi-night arc quality
    + 1.5 · nights_observed_score     ← observing cadence
    + 1.2 · motion_consistency_score  ← linearity of sky-plane motion
    + 1.0 · orbit_quality_score       ← IOD fit residuals
    − 2.5 · known_object_score        ← penalise catalog matches
    − 2.0 · stellar_artifact_score    ← penalise artifacts
    − 1.5 · main_belt_consistency     ← penalise MBA-like orbits
```

### NEO Dynamical Classes

| Class | Criterion | Example |
|---|---|---|
| Amor | 1.017 < q < 1.3 AU | 433 Eros |
| Apollo | a > 1.0 AU, q < 1.017 AU | 1862 Apollo |
| Aten | a < 1.0 AU, Q > 0.983 AU | 2062 Aten |
| IEO (Atira) | Q < 0.983 AU | 163693 Atira |

**PHA criteria:** MOID ≤ 0.05 AU **and** H ≤ 22 (diameter ≳ 140 m). Orbit quality code ≥ 2 required before the PHA flag is set.

### Outputs

- Posterior probabilities over all five hypotheses
- Hazard flag: `pha_candidate` / `close_approach` / `nominal` / `unknown`
- Discovery priority, follow-up value, and scientific interest scores
- Alert pathway: `internal_candidate` → `mpc_submission` → `neocp_followup` → `nasa_pdco_notify`

👉 See [`docs/SCORING_MODEL.md`](docs/SCORING_MODEL.md)

---

## 🛰 Data Sources

| Source | Access | Use |
|---|---|---|
| ZTF alert stream | IRSA / `ztfquery` (free account) | Primary detections; includes sci/ref/diff cutouts and real/bogus score |
| ATLAS forced photometry | REST API — fallingstar-data.com | Candidate confirmation; orange and cyan bands |
| MPC catalog | `astroquery.mpc` | Known-object cross-match; NEOCP monitoring |
| JPL Horizons | `astroquery.jplhorizons` | Ephemerides for known NEOs; close-approach tables |
| Gaia DR3 | `astroquery.gaia` | Sub-milliarcsecond astrometric reference |
| CNEOS Scout / Sentry | Read-only web API | Impact probability reference (never overridden) |

👉 See [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md)

---

## 🚨 Alert Protocol & Submission

> The pipeline **never autonomously asserts a probability of Earth impact.**

All hazard signals follow a mandatory three-step submission process — no step may be skipped:

```
Computed MOID ≤ 0.05 AU
AND orbit quality code ≥ 2
AND real_bogus_score ≥ 0.90
AND NOT matched to MPC known object
         │
         ▼
Step 1: Submit to MPC
        MPC 80-column or JSON format
        via astroquery.mpc or direct POST to minorplanetcenter.net
         │
         ▼
Step 2: Monitor NEOCP
        Wait ≥ 24 hours OR ≥ 2 independent observatory confirmations
         │
         ▼
Step 3: If CNEOS Scout / Sentry assigns impact probability ≥ 0.01%:
        → Open GitHub Issue tagged [HAZARD-ALERT]
        → Notify NASA PDCO and IAU CBAT
        → Defer ALL public communication to NASA / CNEOS
```

---

## 💻 Installation

**Requirements:** Python 3.11 or 3.12

```bash
# Clone
git clone https://github.com/ares0311/2026-Near-Earth-Objects.git
cd 2026-Near-Earth-Objects

# Install (with dev dependencies)
pip install -e ".[dev]"
```

**Optional — CPU-only PyTorch (CI / no GPU):**

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

---

## 🚀 Quick Start

```bash
# Smoke test — happy-path check for all modules
PYTHONPATH=src python Skills/smoke_test.py

# Run full test suite
PYTHONPATH=src python -m pytest -q

# Score a list of tracklets from JSON
PYTHONPATH=src python Skills/batch_score.py --input data/sample_tracklets.json

# Injection-recovery benchmark
PYTHONPATH=src python Skills/injection_recovery.py --n-inject 50 --json results.json

# Linker parameter sweep
PYTHONPATH=src python Skills/tune_linker.py --n 20
```

---

## 📂 Repository Layout

```
2026-Near-Earth-Objects/
├── src/                    pipeline source modules
│   ├── schemas.py          all data models (Pydantic, frozen=True)
│   ├── fetch.py            data acquisition
│   ├── preprocess.py       image validation + source extraction
│   ├── detect.py           moving object detection
│   ├── link.py             multi-night tracklet linking
│   ├── classify.py         three-tier ML ensemble
│   ├── orbit.py            orbit fitting + MOID
│   ├── score.py            hazard scoring
│   ├── alert.py            MPC / NASA alert protocol
│   └── calibration.py      probability calibration
├── tests/                  328 pytest tests (100% coverage)
├── Skills/                 standalone utility scripts
├── data/                   sample tracklets, injection-recovery baselines
├── docs/                   pipeline spec, scoring model, API reference
├── models/                 trained model weights (.pt, .json)
└── .github/                CI workflow, issue templates
```

---

## 🔬 Quality Control

```bash
# Lint
ruff check .
ruff check . --fix

# Type-check
python -m mypy src

# Tests + coverage (gate: 100%)
PYTHONPATH=src python -m pytest --cov=src --cov-fail-under=100

# All three
ruff check . && python -m mypy src && PYTHONPATH=src python -m pytest
```

Live integration tests (require network access to ZTF / ATLAS / MPC) are marked `@pytest.mark.integration_live` and excluded from CI by default.

---

## 🛡 Guardrails

The following constraints are enforced at every layer of the system:

- **No autonomous impact claims.** The pipeline produces ranked candidates and hazard flags. It never autonomously asserts a probability of Earth impact. All impact probabilities are deferred to MPC / CNEOS.
- **Alert protocol is non-negotiable.** The three-step submission process (MPC → NEOCP → NASA PDCO) must be followed in full. No step may be skipped.
- **Conservative classification.** Unknown objects default to `internal_candidate`, not `confirmed NEO`. PHA flags require orbit quality code ≥ 2.
- **No suppression of genuine alerts.** When in doubt, report to authorities and let them assess. Uncertainty is not a reason to suppress.
- **Full provenance.** Every scored result records survey, epoch, model version, orbit solution, and scoring weights.

---

## ⚠️ Important Disclaimer

This project identifies **candidate signals only**.

❌ No claims of confirmed NEOs or Earth impactors
❌ No replacement for MPC / CNEOS authoritative hazard pipelines
❌ No publicly stated impact probabilities — ever

---

## 📜 License

- Code: Apache 2.0
- Docs: CC-BY-4.0

---

## 📚 Citations

Bellm, Eric C., et al. "The Zwicky Transient Facility: System Overview, Performance, and First Results." *Publications of the Astronomical Society of the Pacific*, vol. 131, no. 995, Jan. 2019, p. 018002.

Duev, Dmitry A., et al. "Real-Bogus Classification for the Zwicky Transient Facility Using Deep Learning." *Monthly Notices of the Royal Astronomical Society*, vol. 489, no. 3, Nov. 2019, pp. 3582–3590.

Jedicke, Robert, et al. "Observational Selection Effects in Asteroid Surveys." *Asteroids III*, edited by William F. Bottke Jr. et al., University of Arizona Press, 2002, pp. 71–87.

Lin, Hsing-Wen, et al. "Astronomical Image Time Series Classification Using CONVolutional Neural nETworks (ConvNet)." *The Astronomical Journal*, vol. 163, no. 4, Apr. 2022, p. 154.

Mainzer, Amy, et al. "Initial Performance of the NEOWISE Reactivation Mission." *The Astrophysical Journal*, vol. 792, no. 1, Sep. 2014, p. 30.

Moeyens, Joachim, et al. "THOR: An Algorithm for Cadence-Independent Asteroid Discovery." *The Astronomical Journal*, vol. 162, no. 4, Oct. 2021, p. 143.

Ye, Quanzhi, et al. "Hundreds of New Near-Earth Asteroids Found with the Zwicky Transient Facility." *The Astronomical Journal*, vol. 159, no. 2, Feb. 2020, p. 70.

---

## 🔭 Vision

Build a system that produces:

> **Scientifically defensible, reproducible Near-Earth Object candidates**

—not just ranked lists.
