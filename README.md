# 🌌 2026 Near-Earth Object Detection & Ranking

![CI](https://github.com/ares0311/2026-Near-Earth-Objects/actions/workflows/ci.yml/badge.svg)
![Status](https://img.shields.io/badge/status-active%20development-blue)
![License](https://img.shields.io/badge/license-Apache%202.0-green)
![Focus](https://img.shields.io/badge/focus-near--earth--objects-orange)
![Tests](https://img.shields.io/badge/tests-149%20passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)

---

## 🔭 Overview

A **research-grade, reproducible pipeline** for detecting and evaluating Near-Earth Object (NEO) candidates from **ZTF**, **ATLAS**, and **MPC** survey data.

### ⚡ Core Flow

```
Raw Survey Data → Preprocess → Detect → Link → Classify → Score → Alert
```

This project prioritizes:
- 🎯 Scientific rigor and conservative classification
- 🔬 Low false-positive rates via real/bogus filtering + MPC cross-match
- 📋 Reproducibility — every result carries full provenance
- 🚨 Defensible hazard candidates with a mandatory NASA alert protocol

---

## 🧠 Key Idea

Most moving sources are **not** new NEOs.

This system is built to **disprove signals first**, then elevate only the strongest candidates:

1. 🛑 **Real/bogus filter** — reject artifacts before any orbit work
2. 🗂️ **MPC cross-match** — identify already-known objects immediately
3. 📐 **Orbit quality gates** — require multi-night arcs before hazard assessment
4. 🔁 **Independent confirmation** — mandate NEOCP confirmation before any NASA notification

A candidate is elevated only after surviving every gate. The system is **conservative by design**.

---

## 📊 Current Status

**Phase:** Foundation Complete 🎉

- ✅ All 10 pipeline modules built and tested
- ✅ 149 tests passing across Python 3.11 & 3.12
- ✅ CI green (lint + type-check + test + coverage)
- ✅ MPC-compatible alert formatting
- ✅ NASA PDCO alert protocol implemented
- ⏳ Live ZTF/ATLAS data integration
- ⏳ CNN image classifier (Tier 2)
- ⏳ Transformer tracklet model (Tier 3)

| Module | Status |
|---|---|
| 🧱 `schemas.py` | ✅ Complete |
| 📡 `fetch.py` | ✅ Complete |
| 🖼️ `preprocess.py` | ✅ Complete |
| 🔍 `detect.py` | ✅ Complete |
| 🔗 `link.py` | ✅ Complete |
| 🤖 `classify.py` | ✅ Complete |
| 🪐 `orbit.py` | ✅ Complete |
| 📈 `score.py` | ✅ Complete |
| 🚨 `alert.py` | ✅ Complete |
| 🎛️ `calibration.py` | ✅ Complete |

---

## 🗺️ Roadmap

| Milestone | Description | Status |
|---|---|---|
| 1 | Core pipeline (schemas → score) | ✅ Done |
| 2 | Alert protocol & MPC formatting | ✅ Done |
| 3 | ML calibration (Platt / isotonic) | ✅ Done |
| 4 | Live ZTF/ATLAS data integration | ⏳ Planned |
| 5 | CNN image classifier (Tier 2) | ⏳ Planned |
| 6 | Transformer tracklet model (Tier 3) | ⏳ Planned |
| 7 | Ensemble calibration & injection-recovery | ⏳ Planned |

---

## ⚙️ Architecture

```
Fetch → Preprocess → Detect → Link → Classify → Score → Alert
```

| Module | Purpose |
|---|---|
| 📡 `fetch.py` | ZTF / ATLAS / MPC / JPL Horizons data retrieval |
| 🖼️ `preprocess.py` | Difference image handling, source extraction, Gaia astrometry |
| 🔍 `detect.py` | Moving object detection, real/bogus filter (rb ≥ 0.65) |
| 🔗 `link.py` | Multi-night tracklet linking — THOR-inspired (Moeyens et al. 2021) |
| 🤖 `classify.py` | Three-tier ML ensemble: XGBoost + CNN + Transformer |
| 🪐 `orbit.py` | Gauss IOD, differential correction, MOID computation |
| 📈 `score.py` | Hazard ranking, PHA flag, discovery priority |
| 🚨 `alert.py` | MPC 80-column report formatting, NASA PDCO alert protocol |
| 🎛️ `calibration.py` | Platt scaling and isotonic PAVA probability calibration |

### 🤖 Three-Tier ML Architecture

| Tier | Method | Strength |
|---|---|---|
| **Tier 1** | XGBoost on tabular features | Fast, interpretable, ~500 labels sufficient |
| **Tier 2** | CNN on 63×63 px image triplets | Proven real/bogus classifier (Duev et al. 2019) |
| **Tier 3** | Transformer on tracklet sequences | Frontier multi-night classification (Lin et al. 2022) |
| **Ensemble** | Stacking meta-learner + calibration | Best-of-all via logistic regression over tiers |

---

## 📐 Scoring Model

Classification uses a **log-score Bayesian framework** over five hypotheses:

```
P(Hᵢ | D) ∝ exp( log P(Hᵢ) + Σₖ wᵢₖ · φₖ(D) )
```

### 🧮 Hypotheses & Priors

| Hypothesis | Prior | Description |
|---|---|---|
| 🌠 `neo_candidate` | 0.05 | Genuine new NEO |
| 📚 `known_object` | 0.30 | Matches MPC catalog |
| 🪨 `main_belt_asteroid` | 0.35 | MBA on unusual orbit |
| ⚡ `stellar_artifact` | 0.25 | Cosmic ray / satellite / artifact |
| ☄️ `other_solar_system` | 0.05 | Comet, TNO, etc. |

> Priors are deliberately pessimistic about new NEOs — most moving sources are known objects or artifacts.

### ⚖️ Key Feature Weights

```
log_score_neo =
    log_prior_neo
    + 2.0 × real_bogus_score          ← strongest signal of reality
    + 1.5 × arc_coverage_score        ← multi-night arc quality
    + 1.5 × nights_observed_score     ← observing cadence
    + 1.2 × motion_consistency_score  ← orbital motion coherence
    + 1.0 × orbit_quality_score       ← fit residuals
    − 2.5 × known_object_score        ← penalise catalog matches hard
    − 2.0 × stellar_artifact_score    ← penalise artifacts hard
    − 1.5 × main_belt_consistency     ← penalise MBA-like orbits
```

All features ∈ [0, 1]. Missing features contribute **0** (neutral — no penalty for absent data).

### 🪐 NEO Dynamical Classes

| Class | Definition | Example |
|---|---|---|
| **Amor** | 1.017 < q < 1.3 AU | 433 Eros |
| **Apollo** | a > 1.0 AU, q < 1.017 AU | 1862 Apollo |
| **Aten** | a < 1.0 AU, Q > 0.983 AU | 2062 Aten |
| **IEO (Atira)** | Q < 0.983 AU | 163693 Atira |

**🚨 PHA Criteria:** MOID ≤ 0.05 AU **AND** H ≤ 22 (⌀ ≳ 140 m). Orbit quality code ≥ 2 required before the PHA flag is set.

---

## 🚨 Alert Protocol

> The pipeline **never autonomously asserts a probability of Earth impact.**

All hazard signals follow a **mandatory three-step process** — no step may be skipped:

```
🔭 Computed MOID ≤ 0.05 AU
   AND orbit quality code ≥ 2
   AND real_bogus_score ≥ 0.90
   AND NOT matched to MPC known object
              │
              ▼
📨 Step 1: Submit to MPC (standard 80-column or JSON format)
              │
              ▼
👁️  Step 2: Monitor NEOCP
           Wait ≥ 24 hr OR ≥ 2 independent observatory confirmations
              │
              ▼
🛰️  Step 3: If CNEOS Scout/Sentry assigns impact probability ≥ 0.01%:
           → Open GitHub Issue tagged [HAZARD-ALERT]
           → Notify NASA PDCO and IAU CBAT
           → ⛔ Defer ALL public communication to NASA/CNEOS
```

---

## 📂 Project Structure

```
📦 2026-Near-Earth-Objects/
├── 🧬 src/               pipeline modules
│   ├── schemas.py        all data models (Pydantic, frozen=True)
│   ├── fetch.py          data acquisition
│   ├── preprocess.py     image validation + source extraction
│   ├── detect.py         moving object detection
│   ├── link.py           multi-night tracklet linking
│   ├── classify.py       three-tier ML ensemble
│   ├── orbit.py          orbit fitting + MOID
│   ├── score.py          hazard scoring
│   ├── alert.py          MPC/NASA alert protocol
│   └── calibration.py    probability calibration
├── 🧪 tests/             pytest suite (149 tests)
├── 🛠️  Skills/            standalone utility scripts
└── ⚙️  .github/           CI workflow + HAZARD-ALERT issue template
```

---

## 🖥️ Local Development Profile

| Tool | Version |
|---|---|
| Python | 3.11 / 3.12 |
| pydantic | ≥ 2.13 |
| numpy | ≥ 2.4 |
| scipy | ≥ 1.17 |
| astropy | ≥ 7.2 |
| xgboost | ≥ 2.0 |
| scikit-learn | ≥ 1.3 |

**Minimum recommended:** 8 GB RAM for Tier 1 training; 16 GB + GPU for Tier 2 CNN fine-tuning; 32 GB + GPU for Tier 3 Transformer.

---

## 🚀 Quick Start

```bash
# Install
pip install -e ".[dev]"

# Smoke test — happy-path check for all modules
PYTHONPATH=src python Skills/smoke_test.py

# Full test suite
PYTHONPATH=src python -m pytest -q
```

**🧹 Quality commands:**

```bash
ruff check .                     # 🔍 lint
ruff check . --fix               # 🔧 lint + auto-fix
python -m mypy src               # 🏷️  type-check
PYTHONPATH=src python -m pytest  # ✅ full test suite
```

---

## ⚠️ Important Disclaimer

This project identifies **candidate signals only**.

❌ No claims of confirmed NEOs or Earth impactors
❌ No replacement for MPC / CNEOS authoritative hazard pipelines
❌ No publicly stated impact probabilities — ever

> All authoritative hazard assessment is deferred to the **Minor Planet Center (MPC)** and **NASA/CNEOS**. The alert protocol requires independent observatory confirmation before any NASA PDCO notification is issued.

---

## 📜 License

- 💻 Code: Apache 2.0
- 📄 Docs: CC-BY-4.0

---

## 📚 Citations

Bellm, Eric C., et al. "The Zwicky Transient Facility: System Overview, Performance, and First Results." *Publications of the Astronomical Society of the Pacific*, vol. 131, no. 995, 2019, p. 018002.

Duev, Dmitry A., et al. "Real-Bogus Classification for the Zwicky Transient Facility Using Deep Learning." *Monthly Notices of the Royal Astronomical Society*, vol. 489, no. 3, 2019, pp. 3582–3590.

Jedicke, Robert, et al. "Observational Selection Effects in Asteroid Surveys." *Asteroids III*, edited by William F. Bottke Jr. et al., University of Arizona Press, 2002, pp. 71–87.

Lin, Hsing-Wen, et al. "Astronomical Image Time Series Classification Using CONVolutional Neural nETworks (ConvNet)." *The Astronomical Journal*, vol. 163, no. 4, 2022, p. 154.

Mainzer, Amy, et al. "Initial Performance of the NEOWISE Reactivation Mission." *The Astrophysical Journal*, vol. 792, no. 1, 2014, p. 30.

Moeyens, Joachim, et al. "THOR: An Algorithm for Cadence-Independent Asteroid Discovery." *The Astronomical Journal*, vol. 162, no. 4, 2021, p. 143.

Ye, Quanzhi, et al. "Hundreds of New Near-Earth Asteroids Found with the Zwicky Transient Facility." *The Astronomical Journal*, vol. 159, no. 2, 2020, p. 70.

---

## 🌠 Vision

Build a system that produces:

> **Scientifically defensible, reproducible Near-Earth Object candidates** — not just ranked lists.

Every result carries full provenance: which survey, which epoch, which model version, which orbit solution. Every hazard flag is conservative and human-reviewable.

🔭 Science first. Automation second. Safety always.
