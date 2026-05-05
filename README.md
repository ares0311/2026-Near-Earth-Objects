# 🌌 2026 Near-Earth Object Detection & Ranking

![CI](https://github.com/ares0311/2026-Near-Earth-Objects/actions/workflows/ci.yml/badge.svg)
![Status](https://img.shields.io/badge/status-active%20development-blue)
![License](https://img.shields.io/badge/license-Apache%202.0-green)
![Focus](https://img.shields.io/badge/focus-near--earth--objects-orange)

Automated pipeline for detecting, linking, classifying, and ranking Near-Earth Object (NEO) candidates from publicly available survey photometry, with MPC-compatible reporting and a NASA alert pathway for high-confidence hazard signals.

---

## 🔭 Core Flow

```
Fetch → Preprocess → Detect → Link → Classify → Score → Alert
```

Each stage produces a typed, immutable result object (Pydantic, `frozen=True`). No shared mutable state between stages.

---

## 💡 Key Idea

Most moving sources are **not** new NEOs — they are known main-belt asteroids, instrumental artifacts, or catalog objects observed again. This pipeline **disproves signals first**:

1. **Real/bogus filter** — reject artifacts before any orbit work
2. **MPC cross-match** — identify already-known objects immediately
3. **Orbit quality gates** — require multi-night arcs before hazard assessment
4. **Independent confirmation** — mandate NEOCP confirmation before any NASA notification

A candidate is elevated only after surviving every gate. The system is conservative by design.

---

## ✅ Current Status

**Foundation complete — all 10 modules built and tested (149 tests, CI green).**

| Component | Status |
|---|---|
| `schemas.py` | Complete |
| `fetch.py` | Complete |
| `preprocess.py` | Complete |
| `detect.py` | Complete |
| `link.py` | Complete |
| `classify.py` | Complete |
| `orbit.py` | Complete |
| `score.py` | Complete |
| `alert.py` | Complete |
| `calibration.py` | Complete |

---

## 🗺️ Roadmap

| Milestone | Description |
|---|---|
| 1 | Core pipeline (schemas → score) |
| 2 | Alert protocol & MPC formatting |
| 3 | ML calibration (Platt / isotonic) |
| 4 | Live ZTF/ATLAS data integration |
| 5 | CNN image classifier (Tier 2) |
| 6 | Transformer tracklet model (Tier 3) |
| 7 | Ensemble calibration & injection-recovery |

---

## 🏗️ Architecture

| Module | Purpose |
|---|---|
| `fetch.py` | ZTF/ATLAS/MPC/Horizons data retrieval |
| `preprocess.py` | Difference image handling, source extraction |
| `detect.py` | Moving object detection, real/bogus filter |
| `link.py` | Multi-night tracklet linking (THOR-inspired) |
| `classify.py` | XGBoost + CNN + Transformer ensemble |
| `orbit.py` | Gauss IOD, differential correction, MOID |
| `score.py` | Hazard ranking, PHA flag, discovery priority |
| `alert.py` | MPC report formatting, NASA alert protocol |
| `calibration.py` | Platt scaling and isotonic PAVA |

The ML classifier follows a three-tier architecture:

- **Tier 1** — XGBoost/LightGBM on tabular features (fast, interpretable, works with ~500 labels)
- **Tier 2** — CNN on ZTF image triplets (science / reference / difference cutouts, 63×63 px)
- **Tier 3** — Transformer on tracklet observation sequences (multi-night linking and NEO type classification)
- **Ensemble** — stacking meta-learner (logistic regression) over all three tiers, calibrated via `calibration.py`

---

## 📊 Scoring Model

Classification uses a log-score Bayesian framework over five hypotheses:

| Hypothesis | Prior | Description |
|---|---|---|
| `neo_candidate` | 0.05 | Genuine new NEO |
| `known_object` | 0.30 | Matches MPC catalog |
| `main_belt_asteroid` | 0.35 | MBA on unusual orbit |
| `stellar_artifact` | 0.25 | Cosmic ray / satellite / artifact |
| `other_solar_system` | 0.05 | Comet, TNO, etc. |

Priors are deliberately pessimistic about new NEOs — most moving sources are known objects or artifacts.

**Key feature weights for `neo_candidate`:**

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

All features are bounded `[0, 1]`. Missing features contribute 0 (neutral — no penalty for absent data).

**NEO dynamical classes:**

| Class | Definition |
|---|---|
| Amor | 1.017 < q < 1.3 AU |
| Apollo | a > 1.0 AU, q < 1.017 AU |
| Aten | a < 1.0 AU, Q > 0.983 AU |
| IEO (Atira) | Q < 0.983 AU |

**PHA criteria:** MOID ≤ 0.05 AU AND absolute magnitude H ≤ 22 (diameter ≳ 140 m). Orbit quality code ≥ 2 required before the PHA flag is set.

---

## 🚨 Alert Protocol

The pipeline **never autonomously asserts a probability of Earth impact.** All hazard signals follow a mandatory three-step process — no step may be skipped:

```
Computed MOID ≤ 0.05 AU
AND orbit quality code ≥ 2
AND real_bogus_score ≥ 0.90
AND NOT matched to MPC known object
         │
         ▼
Step 1: Submit to MPC (standard 80-column or JSON format)
         │
         ▼
Step 2: Monitor NEOCP — wait ≥ 24 hr or ≥ 2 independent confirmations
         │
         ▼
Step 3: If CNEOS Scout/Sentry assigns impact probability ≥ 0.01%:
        → Open GitHub Issue tagged [HAZARD-ALERT]
        → Notify NASA PDCO and IAU CBAT
        → Defer all public communication to NASA/CNEOS
```

---

## 📁 Project Structure

```
src/         pipeline modules (fetch, preprocess, detect, link,
             classify, orbit, score, alert, calibration, schemas)
tests/       pytest suite (149 tests)
Skills/      standalone utility scripts
.github/     CI workflow + HAZARD-ALERT issue template
```

---

## 🚀 Quick Start

```bash
pip install -e ".[dev]"
PYTHONPATH=src python Skills/smoke_test.py
PYTHONPATH=src python -m pytest -q
```

**Quality commands:**

```bash
ruff check .                        # lint
ruff check . --fix                  # lint + auto-fix
python -m mypy src                  # type-check
PYTHONPATH=src python -m pytest     # full test suite
```

---

## ⚠️ Disclaimer

This pipeline identifies **candidates only**. It never asserts or implies a probability of Earth impact from internally computed data alone. All authoritative hazard assessment is deferred to the Minor Planet Center (MPC) and NASA/CNEOS. The alert protocol requires independent observatory confirmation before any NASA PDCO notification is issued. No public impact probability is ever quoted by this system.

---

## 📜 License

Apache 2.0 — see [LICENSE](LICENSE).

---

## 🌠 Vision

Build a system that produces scientifically defensible, reproducible NEO candidates — not just ranked lists. Every result carries full provenance: which survey, which epoch, which model version, which orbit solution. Every hazard flag is conservative and human-reviewable. Science first, automation second.
