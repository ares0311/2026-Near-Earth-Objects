# 🚀 2026 Near-Earth Object Detection & Ranking

![Status](https://img.shields.io/badge/status-active%20development-blue)
![License](https://img.shields.io/badge/license-Apache%202.0-green)
![Focus](https://img.shields.io/badge/focus-near--earth--objects-orange)

---

## 🌌 Overview

A **research-grade, reproducible pipeline** for detecting and evaluating Near-Earth Object (NEO) candidates from **ZTF**, **ATLAS**, and **MPC** survey data.

### Core Flow

```
Raw Survey Data → Preprocess → Detect → Link → Classify → Score → Alert
```

This project prioritizes:
- Scientific rigor and conservative classification
- Low false-positive rates via real/bogus filtering + MPC cross-match
- Reproducibility — every result carries full provenance
- Defensible hazard candidates with a mandatory NASA alert protocol

---

## 🧠 Key Idea

Most moving sources are **not** new NEOs.

This system is built to **disprove signals first**, then elevate only the strongest candidates.

1. **Real/bogus filter** — reject artifacts before any orbit work
2. **MPC cross-match** — identify already-known objects immediately
3. **Orbit quality gates** — require multi-night arcs before hazard assessment
4. **Independent confirmation** — mandate NEOCP confirmation before any NASA notification

A candidate is elevated only after surviving every gate. The system is **conservative by design**.

---

## 📊 Current Status

**Phase:** Foundation Complete — v0.9.0

- ✅ All 10 pipeline modules built and tested
- ✅ 328 tests passing across Python 3.11 & 3.12
- ✅ 100% code coverage; CI green
- ✅ MPC-compatible alert formatting
- ✅ NASA PDCO alert protocol implemented
- ✅ Three-tier ML ensemble (XGBoost + CNN + Transformer + stacking meta-learner)
- ✅ Injection-recovery baseline: 100% detect, 62% link (n=50)
- ⏳ Live ZTF/ATLAS data integration
- ⏳ CNN image classifier training (requires labeled cutouts)
- ⏳ Transformer tracklet model training (requires multi-night dataset)

👉 See [`CLAUDE.md`](CLAUDE.md) for full module-by-module detail

---

## 🛣 Roadmap

| Milestone | Description |
|---|---|
| 1 | Core pipeline (schemas → score) ✅ |
| 2 | Alert protocol & MPC formatting ✅ |
| 3 | ML calibration + ensemble meta-learner ✅ |
| 4 | Live ZTF/ATLAS data integration |
| 5 | CNN image classifier (Tier 2) |
| 6 | Transformer tracklet model (Tier 3) |
| 7 | Ensemble calibration & injection-recovery tuning |

👉 See [`docs/PIPELINE_SPEC.md`](docs/PIPELINE_SPEC.md)

---

## ⚙️ Architecture

```
Fetch → Preprocess → Detect → Link → Classify → Score → Alert
```

| Module | Purpose |
|---|---|
| `fetch.py` | ZTF / ATLAS / MPC / JPL Horizons data retrieval |
| `preprocess.py` | Difference image handling, source extraction, Gaia astrometry |
| `detect.py` | Moving object detection, real/bogus filter (rb ≥ 0.65) |
| `link.py` | Multi-night tracklet linking — THOR-inspired |
| `classify.py` | Three-tier ML ensemble: XGBoost + CNN + Transformer |
| `orbit.py` | Gauss IOD, differential correction, MOID computation |
| `score.py` | Hazard ranking, PHA flag, discovery priority |
| `alert.py` | MPC 80-column report formatting, NASA PDCO alert protocol |
| `calibration.py` | Platt scaling and isotonic PAVA probability calibration |

👉 See [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)

---

## 📐 Scoring Model

Bayesian log-score framework:

```
P(Hᵢ | D) ∝ exp( log P(Hᵢ) + Σₖ wᵢₖ · φₖ(D) )
```

Hypotheses:
- NEO candidate (new, unconfirmed)
- Known MPC object
- Main-belt asteroid
- Stellar artifact / instrumental
- Other solar system body (comet, TNO)

Outputs:
- Posterior probabilities over all five hypotheses
- Hazard flag: `pha_candidate` / `close_approach` / `nominal` / `unknown`
- Discovery priority and follow-up value scores
- Alert pathway: `internal_candidate` → `mpc_submission` → `nasa_pdco_notify`

> Priors are deliberately pessimistic about new NEOs — most moving sources are known objects or artifacts.

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

👉 See [`data/README.md`](data/README.md) for data format reference

---

## 🖥 Quick Start

```bash
# Install
pip install -e ".[dev]"

# Smoke test
PYTHONPATH=src python Skills/smoke_test.py

# Full test suite
PYTHONPATH=src python -m pytest -q
```

Quality commands:

```bash
ruff check .                     # lint
python -m mypy src               # type-check
PYTHONPATH=src python -m pytest  # tests + coverage
```

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

## 🔭 Vision

Build a system that produces:

> **Scientifically defensible, reproducible Near-Earth Object candidates** — not just ranked lists.

Every result carries full provenance. Every hazard flag is conservative and human-reviewable.
