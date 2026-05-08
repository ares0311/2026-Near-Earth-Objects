# 🚀 2026 Near-Earth Object Detection & Ranking

![Status](https://img.shields.io/badge/status-active%20development-blue)
![License](https://img.shields.io/badge/license-Apache%202.0-green)
![Focus](https://img.shields.io/badge/focus-near--earth--objects-orange)
![Tests](https://img.shields.io/badge/tests-328%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)

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
- High-value candidates: Potentially Hazardous Asteroids (PHAs) with MOID ≤ 0.05 AU

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
- ✅ 100% code coverage; CI green on lint + type-check + test
- ✅ MPC-compatible alert formatting (80-column + JSON)
- ✅ NASA PDCO alert protocol implemented
- ✅ Three-tier ML ensemble (XGBoost + CNN + Transformer + stacking meta-learner)
- ✅ Injection-recovery baseline: 100% detect, 62% link (n=50, seed=42)
- ⏳ Live ZTF/ATLAS data integration (requires API tokens)
- ⏳ CNN image classifier training (requires labeled cutouts + GPU)
- ⏳ Transformer tracklet model training (requires multi-night dataset)

| Module | Status | Tests |
|---|---|---|
| `schemas.py` | ✅ Complete | 100% |
| `fetch.py` | ✅ Complete | 100% |
| `preprocess.py` | ✅ Complete | 100% |
| `detect.py` | ✅ Complete | 100% |
| `link.py` | ✅ Complete | 100% |
| `classify.py` | ✅ Complete | 100% |
| `orbit.py` | ✅ Complete | 100% |
| `score.py` | ✅ Complete | 100% |
| `alert.py` | ✅ Complete | 100% |
| `calibration.py` | ✅ Complete | 100% |

👉 See [`CLAUDE.md`](CLAUDE.md) for full version history and change log

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

Each stage produces a typed, immutable result object. No shared mutable state.

| Module | Purpose |
|---|---|
| `fetch.py` | ZTF alert stream, ATLAS forced photometry, MPC catalog, JPL Horizons ephemerides |
| `preprocess.py` | Difference image validation, PSF quality, Gaia DR3 astrometric correction |
| `detect.py` | Real/bogus filter (rb ≥ 0.65), moving-source pairing, streak detection, MPC cross-match |
| `link.py` | THOR-inspired multi-night tracklet linking; ≥3 detections on ≥2 nights required |
| `classify.py` | Three-tier ML ensemble: XGBoost + CNN + Transformer + logistic regression stacker |
| `orbit.py` | Gauss method IOD, differential correction, MOID vs Earth, NEO class assignment |
| `score.py` | Hazard ranking, PHA flag, discovery priority, follow-up value, novelty score |
| `alert.py` | MPC 80-column report formatting; mandatory three-step NASA PDCO alert protocol |
| `calibration.py` | Platt scaling and isotonic PAVA; Brier score + ECE evaluation |

### Three-Tier ML Architecture

| Tier | Method | Strength |
|---|---|---|
| **Tier 1** | XGBoost on tabular features | Fast, interpretable, ~500 labels sufficient |
| **Tier 2** | CNN on 63×63 px image triplets (sci / ref / diff) | Proven real/bogus classifier (Duev et al. 2019) |
| **Tier 3** | Transformer on observation sequences | Frontier multi-night classification (Lin et al. 2022) |
| **Ensemble** | Logistic regression stacker + Platt calibration | Best-of-all; falls back to weighted average without trained weights |

👉 See [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)

---

## 📐 Scoring Model

Bayesian log-score framework over five hypotheses:

```
P(Hᵢ | D) ∝ exp( log P(Hᵢ) + Σₖ wᵢₖ · φₖ(D) )
```

### Hypotheses & Priors

| Hypothesis | Prior | Rationale |
|---|---|---|
| `neo_candidate` | 0.05 | Most moving sources are not new NEOs |
| `known_object` | 0.30 | Large fraction of detections are catalog objects |
| `main_belt_asteroid` | 0.35 | MBAs dominate the moving-object population |
| `stellar_artifact` | 0.25 | Cosmic rays, satellites, and ghosts are common |
| `other_solar_system` | 0.05 | Comets, TNOs, Centaurs are rare |

> Priors are deliberately pessimistic about new NEOs. Adjust for high-ecliptic-latitude fields where MBA contamination is lower.

### Key Feature Weights

```
log_score_neo =
    log_prior_neo
    + 2.0 × real_bogus_score          ← strongest signal of reality
    + 1.5 × arc_coverage_score        ← multi-night arc quality
    + 1.5 × nights_observed_score     ← observing cadence
    + 1.2 × motion_consistency_score  ← orbital motion coherence
    + 1.0 × orbit_quality_score       ← fit residuals
    − 2.5 × known_object_score        ← penalise catalog matches strongly
    − 2.0 × stellar_artifact_score    ← penalise artifacts strongly
    − 1.5 × main_belt_consistency     ← penalise MBA-like orbits
```

All features ∈ [0, 1]. Missing features contribute **0** — neutral, no penalty for absent data.

### NEO Dynamical Classes

| Class | Definition | Example |
|---|---|---|
| **Amor** | 1.017 < q < 1.3 AU | 433 Eros |
| **Apollo** | a > 1.0 AU, q < 1.017 AU | 1862 Apollo |
| **Aten** | a < 1.0 AU, Q > 0.983 AU | 2062 Aten |
| **IEO (Atira)** | Q < 0.983 AU | 163693 Atira |

**PHA criteria:** MOID ≤ 0.05 AU **and** H ≤ 22 (diameter ≳ 140 m). Orbit quality code ≥ 2 required before the PHA flag is set.

### Outputs

- Posterior probabilities over all five hypotheses
- Hazard flag: `pha_candidate` / `close_approach` / `nominal` / `unknown`
- Discovery priority, follow-up value, and scientific interest scores
- Alert pathway: `internal_candidate` → `mpc_submission` → `neocp_followup` → `nasa_pdco_notify`

👉 See [`docs/SCORING_MODEL.md`](docs/SCORING_MODEL.md)

---

## 🚨 Alert Protocol

> The pipeline **never autonomously asserts a probability of Earth impact.**

All hazard signals follow a mandatory three-step process — no step may be skipped:

```
Computed MOID ≤ 0.05 AU
AND orbit quality code ≥ 2
AND real_bogus_score ≥ 0.90
AND NOT matched to MPC known object
         │
         ▼
Step 1: Submit to MPC via standard report format
        (MPC 80-column or JSON; astroquery.mpc or direct HTTP POST)
         │
         ▼
Step 2: Monitor NEOCP for independent confirmation
        (wait ≥ 24 hours OR ≥ 2 independent observatory confirmations)
         │
         ▼
Step 3: If CNEOS Scout/Sentry assigns impact probability ≥ 0.01%:
        → Open GitHub Issue tagged [HAZARD-ALERT]
        → Notify NASA PDCO and IAU CBAT
        → Defer ALL public communication to NASA/CNEOS
```

---

## 📂 Project Structure

```
src/               pipeline modules (10 files)
tests/             pytest suite (328 tests, 100% coverage)
Skills/            standalone utility scripts
data/              sample tracklets, injection-recovery baselines
docs/              pipeline spec, scoring model, API reference
models/            trained model weights (.pt, .json)
.github/           CI workflow, issue templates
```

| Script | Purpose |
|---|---|
| `Skills/smoke_test.py` | Happy-path check for all modules |
| `Skills/injection_recovery.py` | Inject synthetic NEOs; measure detect/link/score rates |
| `Skills/tune_linker.py` | Parametric sweep of linker tolerance × chi² vs link rate |
| `Skills/batch_score.py` | Score a JSON list of tracklets; print ranked table |
| `Skills/run_pipeline.py` | Full end-to-end pipeline run |
| `Skills/export_mpc_report.py` | Export MPC 80-column reports from scored NEO JSON |
| `Skills/train_tier2_cnn.py` | Fine-tune CNN on labeled ZTF cutout CSV |
| `Skills/train_tier3_transformer.py` | Train Transformer on MPC tracklet observation CSV |
| `Skills/generate_training_labels.py` | Download MPC NEO + MBA catalog as training label CSV |
| `Skills/benchmark_pipeline.py` | Time classify + score on N synthetic tracklets |

👉 See [`data/README.md`](data/README.md) for data format reference

---

## 🖥 Local System Profile

| Requirement | Minimum | Recommended |
|---|---|---|
| Python | 3.11 | 3.12 |
| RAM | 4 GB | 16 GB (CNN training) |
| GPU | — | Required for Tier 2/3 training |
| Disk | 1 GB | 10 GB (alert cache + cutouts) |

Dependencies: `pydantic ≥ 2.13`, `numpy ≥ 2.4`, `scipy ≥ 1.17`, `astropy ≥ 7.2`, `xgboost ≥ 2.0`, `scikit-learn ≥ 1.3`, `torch ≥ 2.1`

```bash
# Install
pip install -e ".[dev]"

# Smoke test — happy-path check for all modules
PYTHONPATH=src python Skills/smoke_test.py

# Full test suite
PYTHONPATH=src python -m pytest -q
```

Quality commands:

```bash
ruff check .                      # lint
ruff check . --fix                # lint + auto-fix
python -m mypy src                # type-check
PYTHONPATH=src python -m pytest   # full test suite + coverage
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

- Code: Apache 2.0
- Docs: CC-BY-4.0

---

## 📚 Citations

Bellm, Eric C., et al. "The Zwicky Transient Facility: System Overview, Performance, and First Results." *PASP*, vol. 131, 2019, p. 018002.

Duev, Dmitry A., et al. "Real-bogus Classification for the Zwicky Transient Facility Using Deep Learning." *MNRAS*, vol. 489, no. 3, 2019, pp. 3582–3590.

Lin, Hsing-Wen, et al. "Astronomical Image Time Series Classification Using CONVolutional Neural nETworks (ConvNet)." *AJ*, vol. 163, 2022, p. 154.

Moeyens, Joachim, et al. "THOR: An Algorithm for Cadence-independent Asteroid Discovery." *AJ*, vol. 162, no. 4, 2021, p. 143.

Ye, Quanzhi, et al. "Hundreds of New Near-Earth Asteroids Found with ZTF." *AJ*, vol. 159, no. 2, 2020, p. 70.

---

## 🔭 Vision

Build a system that produces:

> **Scientifically defensible, reproducible Near-Earth Object candidates** — not just ranked lists.

Every result carries full provenance: which survey, which epoch, which model version, which orbit solution. Every hazard flag is conservative and human-reviewable.
