# 🚀 2026 Near-Earth Object Detection & Ranking

![Status](https://img.shields.io/badge/status-active%20development-blue)
![License](https://img.shields.io/badge/license-Apache%202.0-green)
![Focus](https://img.shields.io/badge/focus-near--earth--objects-orange)

---

## 🌌 Overview

A **research-grade, reproducible pipeline** for detecting and evaluating Near-Earth Object (NEO) candidates from **ZTF** and **ATLAS** data.

### Core Flow

```
Raw Survey Data → Preprocess → Detect → Link → Classify → Score → Alert
```

This project prioritizes:
- Scientific rigor
- Low false-positive rates
- Reproducibility
- High-value candidates (Potentially Hazardous Asteroids)

---

## 🧠 Key Idea

Most moving sources are **not** new NEOs.

This system is built to **disprove signals first**, then elevate only the strongest candidates.

---

## 📊 Current Status

**Phase:** Foundation Complete — v0.9.0

- ✅ All 10 pipeline modules built and tested
- ✅ 328 tests passing (100% coverage)
- ✅ CI green on Python 3.11 & 3.12
- ✅ MPC-compatible alert formatting
- ✅ Three-tier ML ensemble implemented
- ✅ Injection-recovery baseline established
- ⏳ Live ZTF/ATLAS data integration
- ⏳ CNN and Transformer model training

👉 See [`CLAUDE.md`](CLAUDE.md)

---

## 🛣 Roadmap

| Milestone | Description |
|---|---|
| 1 | Core pipeline (fetch → score) |
| 2 | Alert protocol & MPC formatting |
| 3 | ML calibration + ensemble |
| 4 | Live ZTF/ATLAS integration |
| 5 | CNN image classifier (Tier 2) |
| 6 | Transformer tracklet model (Tier 3) |
| 7 | Injection–recovery tuning |

👉 See [`docs/PIPELINE_SPEC.md`](docs/PIPELINE_SPEC.md)

---

## ⚙️ Architecture

```
Fetch → Preprocess → Detect → Link → Classify → Score → Alert
```

| Module | Purpose |
|---|---|
| fetch.py | ZTF / ATLAS / MPC / JPL data retrieval |
| preprocess.py | Difference image handling, source extraction |
| detect.py | Moving object detection, real/bogus filter |
| link.py | Multi-night tracklet linking |
| classify.py | Three-tier ML ensemble |
| orbit.py | Orbit fitting, MOID computation |
| score.py | Hazard ranking, PHA flag |
| alert.py | MPC report formatting, NASA alert protocol |
| calibration.py | Probability calibration |

👉 See [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)

---

## 📐 Scoring Model

Bayesian framework:

```
P(H | D) ∝ P(D | H) P(H)
```

Hypotheses:
- NEO candidate (new, unconfirmed)
- Known MPC object
- Main-belt asteroid
- Stellar artifact / instrumental
- Other solar system body

Outputs:
- Posterior probabilities
- Hazard flag (PHA candidate / close approach / nominal)
- Discovery priority and follow-up value
- Alert pathway classification

👉 See [`docs/SCORING_MODEL.md`](docs/SCORING_MODEL.md)

---

## 📂 Project Structure

```
src/
tests/
Skills/
data/
docs/
models/
```

## 🖥 Local System Profile

Local development and batch-run sizing guidance is recorded in [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md).

---

## ⚠️ Important Disclaimer

This project identifies **candidate signals only**.

❌ No claims of confirmed NEOs or Earth impactors
❌ No replacement for MPC / CNEOS authoritative hazard pipelines

---

## 📜 License

- Code: Apache 2.0
- Docs: CC-BY-4.0

---

## 🔭 Vision

Build a system that produces:

> **Scientifically defensible, reproducible Near-Earth Object candidates**

—not just ranked lists.
