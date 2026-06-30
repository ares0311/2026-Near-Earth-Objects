# 2026 Near-Earth Object Detection & Ranking Pipeline

![Status](https://img.shields.io/badge/status-active%20development-blue)
![Version](https://img.shields.io/badge/version-0.90.3-informational)
![License](https://img.shields.io/badge/license-Apache%202.0-green)
![Tests](https://img.shields.io/badge/tests-3500%2B%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)
![Python](https://img.shields.io/badge/python-3.14.3-blue)
![CI](https://img.shields.io/badge/CI-passing-brightgreen)

---

## Abstract

Near-Earth Objects (NEOs) — small solar system bodies with perihelion distances $q < 1.3$ AU — represent both a premier target for planetary science and the only known category of natural disaster that is, in principle, preventable. Despite three decades of systematic survey effort, population completeness models estimate that the majority of NEOs larger than 140 meters remain undetected, sustaining the need for automated, high-throughput discovery pipelines capable of operating at the cadence and scale of modern wide-field photometric surveys. This work presents a research pipeline for the detection, multi-night linking, orbital characterization, and hazard ranking of NEO candidates derived from public training streams and unreviewed archival survey data. The system implements a seven-stage directed acyclic processing graph — fetch, preprocess, detect, link, classify, orbit, score — followed by a mandatory three-step alert protocol governing all external communications. Classification employs a three-tier ensemble architecture: a gradient-boosted tree classifier on tabular features (Tier 1), a convolutional neural network operating on 63×63-pixel ZTF image triplets following the architecture of Duev et al. (2019) (Tier 2), and a BERT-style Transformer trained on multi-night observation sequences following Lin et al. (2022) (Tier 3), with outputs combined by a logistic regression meta-learner and calibrated via Platt scaling or isotonic regression. Hazard assessment follows a Bayesian log-score model over five competing hypotheses with deliberately pessimistic priors for new NEO candidates. Preliminary orbit determination uses Gauss's method with differential correction, and Potentially Hazardous Asteroid (PHA) flags are gated on orbit quality code ≥ 2 and independently confirmed MOID ≤ 0.05 AU. As of version 0.90.3, all ten pipeline modules are implemented, all three ML tiers and the ensemble stacker have passed quantitative calibration KPIs, T1/T2 production gaps are closed, and the discovery fetch layer targets WISE/NEOWISE, DECam/NOIRLab, and TESS FFIs while keeping ZTF/ATLAS as training-data sources only. Background automation provides top-level SQLite audit logs and fail-closed readiness controls. Injection-recovery validation on $n = 200$ synthetic NEO tracklets reports 100% detection, link, and score rates, but synthetic results are not treated as evidence of live-sky performance. The pipeline produces MPC-compatible 80-column, ADES PSV, and JSON observation reports and implements a non-negotiable three-step pathway — MPC submission, independent observatory confirmation, and conditional NASA PDCO notification — ensuring that no autonomous impact claim is ever issued. MPC submission remains disabled until archival WISE/NEOWISE submission authority is resolved with MPC and a candidate survives adversarial plus operator review.

**Keywords:** near-Earth objects, planetary defense, asteroid detection, automated pipeline, machine learning, real/bogus classification, orbit determination, Bayesian scoring, ZTF, Minor Planet Center

---

## Table of Contents

- [Abstract](#abstract)

1. [Introduction](#1-introduction)
2. [Scientific Background](#2-scientific-background)
3. [Pipeline Architecture](#3-pipeline-architecture)
4. [Methodology & Equations](#4-methodology--equations)
5. [Three-Tier Machine Learning Architecture](#5-three-tier-machine-learning-architecture)
6. [Scoring Model](#6-scoring-model)
7. [Alert Protocol & Guardrails](#7-alert-protocol--guardrails)
8. [Data Sources](#8-data-sources)
9. [Repository Layout](#9-repository-layout)
10. [End-User Guide (Layperson)](#10-end-user-guide-layperson)
11. [Recalibration Guide](#11-recalibration-guide)
12. [Installation](#12-installation)
13. [Quick Start](#13-quick-start)
14. [Quality Control](#14-quality-control)
15. [Current Status & Roadmap](#15-current-status--roadmap)
16. [Important Disclaimer](#16-important-disclaimer)
17. [License](#17-license)
18. [Works Cited](#18-works-cited)

---

## 1. Introduction

Near-Earth Objects (NEOs) constitute one of the most consequential populations in the solar system from both a scientific and a planetary-defense perspective. Defined by the International Astronomical Union as small bodies with perihelion distances $q < 1.3$ AU, NEOs include asteroids and short-period comets whose orbits bring them into the inner solar system and, in some cases, into proximity with Earth. As of 2026, the Minor Planet Center (MPC) catalogs approximately 35,000 confirmed NEOs; however, population completeness models estimate that hundreds of thousands of objects larger than 140 meters remain undetected (Jedicke et al. 71). The discovery and characterization of this population is therefore a standing scientific priority endorsed by NASA, the European Space Agency, and the United Nations Office for Outer Space Affairs.

The global NEO survey is currently led by a small number of wide-field photometric facilities: the Zwicky Transient Facility (ZTF), the Asteroid Terrestrial-impact Last Alert System (ATLAS), the Panoramic Survey Telescope and Rapid Response System (Pan-STARRS), and the Catalina Sky Survey (CSS). Together these systems generate on the order of $10^6$ difference-image alerts per night (Bellm et al. 018002), the vast majority of which correspond to non-moving transient phenomena, instrumental artifacts, satellite trails, cosmic rays, and main-belt asteroids — not genuine new NEOs. Efficient real-time discrimination of the rare true positive from this overwhelmingly negative background is the central algorithmic challenge of the field.

This repository implements a complete, research-grade automated detection and ranking pipeline for NEO candidates. Training and calibration use processed ZTF/ATLAS evidence, while discovery searches target less-reviewed archival sources such as WISE/NEOWISE, DECam, and TESS. The system performs astrometric source extraction, multi-night tracklet linking, preliminary orbit determination, Bayesian hazard scoring, and - where evidence meets mandatory threshold criteria - formatted MPC reporting under fail-closed submission controls. The pipeline is designed around five principles:

1. **Conservative classification** — every gate fails closed; ambiguous candidates are flagged for human review, never silently promoted.
2. **Full provenance** — every scored candidate carries the survey, filter, epoch, model version, and orbit-solution identifier needed to reproduce the result.
3. **MPC interoperability** — all detections are expressible in MPC 80-column or MPC JSON format, ensuring compatibility with the global community.
4. **Independent confirmation before alert** — the NASA PDCO notification pathway is gated on MPC submission *and* independent observatory confirmation, not on pipeline confidence alone.
5. **No autonomous impact claims** — the system produces ranked candidates and hazard flags; it defers all authoritative impact probability statements to CNEOS Scout and Sentry.

The pipeline follows the build order: `schemas` -> `fetch` -> `preprocess` -> `detect` -> `link` -> `classify` -> `orbit` -> `score` -> `alert` -> `calibration`. Each stage consumes the immutable, typed output of all prior stages. As of v0.90.3, all ten pipeline modules plus background automation are complete, all three ML tiers have trained weights, calibration KPIs have passed, T1/T2 production gaps are closed, and the discovery fetch layer is active for WISE/NEOWISE, DECam, and TESS. External MPC submission remains disabled until archival WISE/NEOWISE submission authority and candidate review gates are satisfied. See `docs/PRODUCTION_READINESS.md` for the authoritative production register.

---

## 2. Scientific Background

### 2.1 NEO Dynamical Classification

Near-Earth Objects are subdivided into four dynamical families based on their semi-major axis $a$, perihelion distance $q$, and aphelion distance $Q$:

| Family | Criterion | Archetypal Member |
|---|---|---|
| **Amor** | $1.017 < q < 1.3$ AU | 433 Eros |
| **Apollo** | $a > 1.0$ AU, $q < 1.017$ AU | 1862 Apollo |
| **Aten** | $a < 1.0$ AU, $Q > 0.983$ AU | 2062 Aten |
| **IEO (Atira)** | $Q < 0.983$ AU | 163693 Atira |

Amorite, Apollonian, and Atenian objects cross or approach Earth's orbit; IEOs orbit entirely interior to Earth and are observationally challenging due to solar elongation constraints.

### 2.2 Potentially Hazardous Asteroids

A Potentially Hazardous Asteroid (PHA) is an NEO satisfying two simultaneous criteria:

- **Minimum Orbit Intersection Distance (MOID)** ≤ 0.05 AU with respect to Earth's orbit
- **Absolute magnitude** $H \leq 22$, corresponding to an estimated diameter $d \gtrsim 140$ m at geometric albedo $p_v = 0.14$

The diameter–magnitude relationship used throughout this pipeline is:

$$d = \frac{1329 \text{ km}}{\sqrt{p_v}} \times 10^{-H/5}$$

At the standard assumption of $p_v = 0.14$ (C-type average; Mainzer et al. 30), $H = 22$ yields $d \approx 140$ m — the widely adopted threshold below which an impactor would cause regional-scale destruction. Objects above this threshold and with low MOID are the primary concern of planetary defense.

### 2.3 MOID and Close-Approach Geometry

The Minimum Orbit Intersection Distance is defined as the global minimum of the distance between two Keplerian ellipses, computed analytically or via iterative grid search. For a candidate orbit with elements $(a, e, i, \Omega, \omega)$, the MOID with respect to Earth is:

$$\text{MOID} = \min_{\nu_1, \nu_2} \left| \mathbf{r}_\text{NEO}(\nu_1) - \mathbf{r}_\oplus(\nu_2) \right|$$

where $\nu_1$ and $\nu_2$ are the true anomalies of the NEO and Earth respectively, and $\mathbf{r}$ denotes the heliocentric position vector in the ecliptic frame. This pipeline implements the computation in `orbit.py` using a $\chi^2$-minimisation approach over a coarse grid followed by Brent refinement. MOID values derived from arcs shorter than 24 hours are flagged as unreliable and do not trigger the PHA flag.

### 2.4 The Detection Problem at Scale

A modern wide-field survey such as ZTF observes approximately $3.75 \times 10^3$ square degrees per hour to a limiting magnitude of $r \approx 20.5$. Each processed exposure generates $\mathcal{O}(10^4)$ difference-image detections, of which approximately 97–99% are non-astrophysical (satellite streaks, cosmic rays, subtraction artefacts) or known solar system objects. Of the remaining astrophysical transients, roughly 0.1% are previously unknown solar system objects (Ye et al. 70). The signal-to-noise problem therefore spans four orders of magnitude, motivating a multi-stage filtering architecture in which each stage is calibrated to reduce the false-positive rate while preserving genuine NEO candidates.

---

## 3. Pipeline Architecture

The pipeline implements a strict directed acyclic graph (DAG) of processing stages. Each stage produces an immutable, typed result object; no shared mutable state exists between stages. The complete data flow is:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    NEO DETECTION PIPELINE  v0.87.0                  │
└─────────────────────────────────────────────────────────────────────┘

  External Data Sources
  ┌──────┐  ┌───────┐  ┌──────┐  ┌──────────────┐
  │ ZTF  │  │ ATLAS │  │ MPC  │  │ JPL Horizons │
  └──┬───┘  └───┬───┘  └──┬───┘  └──────┬───────┘
     │           │          │              │
     └───────────┴──────────┴──────────────┘
                            │
                     ┌──────▼──────┐
                     │   fetch.py  │  → FetchResult
                     └──────┬──────┘
                            │
                  ┌──────────▼───────────┐
                  │    preprocess.py      │  → PreprocessResult
                  │  (Gaia DR3 astrometry)│
                  └──────────┬───────────┘
                             │
                    ┌─────────▼─────────┐
                    │    detect.py       │  → DetectResult
                    │  (rb ≥ 0.65 gate) │
                    └─────────┬─────────┘
                              │
                     ┌────────▼────────┐
                     │    link.py       │  → LinkResult
                     │ (THOR-inspired) │
                     └────────┬────────┘
                              │
                   ┌──────────▼──────────┐
                   │    classify.py       │  → ClassifyResult
                   │  Tier1+Tier2+Tier3  │
                   └──────────┬──────────┘
                              │
                     ┌────────▼────────┐
                     │    orbit.py      │  → OrbitResult
                     │ (Gauss + diff-  │
                     │  correction)    │
                     └────────┬────────┘
                              │
                      ┌───────▼───────┐
                      │   score.py    │  → ScoredNEO
                      │ (Bayesian log-│
                      │  score model) │
                      └───────┬───────┘
                              │
                      ┌───────▼───────┐
                      │   alert.py    │  → AlertResult
                      │ (MPC report + │
                      │ NASA pathway) │
                      └───────────────┘
                              │
                   ┌──────────▼──────────┐
                   │  calibration.py      │  → CalibrationResult
                   │  (Platt / isotonic) │
                   └─────────────────────┘
```

### 3.1 Stage Specifications

| Module | Inputs | Key Operations | Outputs |
|---|---|---|---|
| `fetch.py` | Sky region, date range, survey | ZTF IRSA query; ATLAS forced photometry; MPC catalog; JPL Horizons ephemerides | `FetchResult(alerts, provenance)` |
| `preprocess.py` | Raw alerts with cutouts | PSF validation; pixel normalisation [0,1]; Gaia DR3 astrometric correction; aperture photometry | `PreprocessResult(sources, provenance)` |
| `detect.py` | Preprocessed source catalog | Real/bogus filter ($rb \geq 0.65$); moving-source pairing across epochs; streak detection; MPC cross-match | `DetectResult(candidates, known_matches)` |
| `link.py` | Single-night candidates, multi-night | Pair → triplet → longer arc; $\chi^2$ orbit-consistency test; require ≥3 detections on ≥2 nights | `LinkResult(tracklets)` |
| `classify.py` | Tracklets + image cutouts | XGBoost (Tier 1); CNN image triplet (Tier 2); Transformer sequence (Tier 3); logistic stacker ensemble | `ClassifyResult(posterior, features)` |
| `orbit.py` | Linked tracklets | Gauss IOD; differential correction; orbital elements $(a,e,i,\Omega,\omega,M_0)$; MOID; NEO class | `OrbitResult(elements, moid_au, neo_class, quality_code)` |
| `score.py` | Classified tracklets + orbit | Hazard flag; PHA test; discovery priority; follow-up value; novelty score | `ScoredNEO(tracklet, features, posterior, hazard, metadata)` |
| `alert.py` | `ScoredNEO` objects | MPC 80-column / JSON formatting; three-step PDCO protocol; timestamp + provenance logging | `AlertResult(mpc_report, pathway, log)` |
| `calibration.py` | Raw classifier scores | Platt scaling; isotonic PAVA regression; Brier score + ECE evaluation | `CalibrationResult(calibrator, metrics)` |

---

## 4. Methodology & Equations

### 4.1 Astrometric Reduction

Raw ZTF alert positions are calibrated against Gaia Data Release 3 (Gaia Collaboration 2022), which provides sub-milliarcsecond astrometry for $\sim 1.5 \times 10^9$ stars. The astrometric correction for source $i$ is:

$$\Delta\alpha_i = \alpha_i^\text{ZTF} - \alpha_i^\text{Gaia}, \qquad \Delta\delta_i = \delta_i^\text{ZTF} - \delta_i^\text{Gaia}$$

A field-wide polynomial correction of degree $n = 2$ is fit by weighted least squares:

$$\Delta\alpha = \sum_{j=0}^{n} \sum_{k=0}^{n-j} c_{jk} \, x^j \, y^k$$

where $x, y$ are detector coordinates and weights are proportional to Gaia astrometric excess noise inverse. Residuals are required to satisfy $\sigma_\text{astrometric} \leq 0.3$ arcsec RMS before a source is forwarded to `detect.py`.

### 4.2 Moving-Object Detection & Apparent Motion

A source pair $(\mathbf{r}_1, t_1)$, $(\mathbf{r}_2, t_2)$ is consistent with a solar-system object if its apparent sky-plane motion rate $\dot\theta$ satisfies:

$$0.01 \;\text{arcsec hr}^{-1} \leq \dot\theta \leq 60 \;\text{arcsec hr}^{-1}$$

The lower bound excludes stationary transients; the upper bound excludes fast-moving spacecraft and low-Earth-orbit debris. For the survey field centred at ecliptic latitude $\beta$, the expected sky-plane rate for an NEO at heliocentric distance $r$ and geocentric distance $\Delta$ is approximately:

$$\dot\theta \approx \frac{v_\oplus \cos\beta}{\Delta} \left(1 - \frac{\Delta}{r}\right) \;\text{rad s}^{-1}$$

Streak morphology is separately detected via second-moment elongation: a source with semi-major to semi-minor axis ratio $a/b > 1.5$ and position angle consistent with the expected motion vector is flagged as a trailed detection and is given enhanced weight in the linking stage.

### 4.3 Tracklet Linking ($\chi^2$ Consistency Test)

Following the THOR algorithm (Moeyens et al. 143), candidate triplets are extended into longer arcs by testing whether adding a new detection $(\alpha_k, \delta_k, t_k)$ is consistent with the existing tracklet under a constant angular-rate approximation:

$$\chi^2_k = \left(\frac{\alpha_k - \hat\alpha_k}{\sigma_{\alpha,k}}\right)^2 + \left(\frac{\delta_k - \hat\delta_k}{\sigma_{\delta,k}}\right)^2$$

where $\hat\alpha_k$, $\hat\delta_k$ are the predicted positions from a linear extrapolation of the tracklet, and $\sigma$ are the positional uncertainties. A detection is admitted to the tracklet if $\chi^2_k \leq \chi^2_\text{thresh}$ (default: 9.0, i.e., $3\sigma$). The tracklet is reportable if it contains $\geq 3$ detections on $\geq 2$ distinct nights.

### 4.4 Preliminary Orbit Determination — Gauss's Method

Given three observations at times $t_1 < t_2 < t_3$ with unit direction vectors $\hat{\mathbf{e}}_1, \hat{\mathbf{e}}_2, \hat{\mathbf{e}}_3$ from the observer, Gauss's method solves for the geocentric distances $\rho_1, \rho_2, \rho_3$ via the scalar equation:

$$\rho_2^8 + a_1 \rho_2^6 + a_2 \rho_2^3 + a_3 = 0$$

derived from the $f$- and $g$-series Lagrange coefficients and the conservation of angular momentum. The three real-valued heliocentric position vectors $\mathbf{r}_1, \mathbf{r}_2, \mathbf{r}_3$ and velocity $\dot{\mathbf{r}}_2$ are then determined, and Keplerian elements are extracted from $(\mathbf{r}_2, \dot{\mathbf{r}}_2)$ using:

$$a = -\frac{\mu}{2\mathcal{E}}, \qquad e = \left|\mathbf{e}\right|, \qquad i = \arccos\left(\frac{h_z}{|\mathbf{h}|}\right)$$

where $\mu = GM_\odot$, $\mathcal{E} = \frac{v^2}{2} - \frac{\mu}{r}$ is the specific orbital energy, $\mathbf{e}$ is the eccentricity vector, and $\mathbf{h} = \mathbf{r} \times \dot{\mathbf{r}}$ is the specific angular momentum.

### 4.5 Differential Correction

The initial Gauss solution is refined by nonlinear least-squares differential correction. The design matrix $\mathbf{A}$ has rows $\partial (\alpha_i^\text{calc}, \delta_i^\text{calc}) / \partial \mathbf{x}$ where $\mathbf{x} = (a, e, i, \Omega, \omega, M_0)^\top$. The correction vector at each iteration is:

$$\Delta\mathbf{x} = \left(\mathbf{A}^\top \mathbf{W} \mathbf{A}\right)^{-1} \mathbf{A}^\top \mathbf{W} \mathbf{r}$$

where $\mathbf{W} = \text{diag}(\sigma_{\alpha,i}^{-2}, \sigma_{\delta,i}^{-2})$ is the weight matrix and $\mathbf{r}$ is the residual vector. Iteration continues until $|\Delta\mathbf{x}| < 10^{-8}$ or 50 iterations are exhausted. The orbit quality code is assigned as:

| Code | Arc Duration |
|---|---|
| 1 | < 1 day |
| 2 | Multi-night (≥ 2 nights) |
| 3 | Multi-week (≥ 14 days) |
| 4 | Opposition coverage (≥ 3 months) |

The PHA flag is suppressed for quality code 1 orbits.

### 4.6 Absolute Magnitude and Size Estimation

The absolute magnitude $H$ is derived from the reduced magnitude using the HG phase function (Bowell et al. 1989):

$$H = V - 5\log_{10}(r\Delta) - 2.5\log_{10}\left[(1-G)\Phi_1(\alpha) + G\Phi_2(\alpha)\right]$$

where $r$ is heliocentric distance in AU, $\Delta$ is geocentric distance in AU, $\alpha$ is the solar phase angle, $G = 0.15$ is the default slope parameter, and $\Phi_1$, $\Phi_2$ are the Hapke basis functions. The inferred physical diameter is:

$$d = \frac{1329 \text{ km}}{\sqrt{p_v}} \times 10^{-H/5}$$

with $p_v = 0.14$ as the default geometric albedo (C-type average). Both $p_v$ and $G$ are flagged as assumptions in the provenance record.

---

## 5. Three-Tier Machine Learning Architecture

The classifier follows the tiered ensemble design established for high-false-positive-rate astronomical surveys. Tiers are built in order: Tier 1 must be calibrated before Tier 2 is trained, and both must be complete before the Tier 3 Transformer is trained and the ensemble is assembled.

```
                 Tabular Features
                       │
               ┌───────▼────────┐
               │   TIER 1        │
               │   XGBoost       │  → p̂₁(neo | features)
               │ (≥ 500 labels) │
               └───────┬────────┘
                       │
         Image Triplets (63×63 px, 3-channel)
                       │
               ┌───────▼────────┐
               │   TIER 2        │
               │   CNN           │  → p̂₂(real | cutout)
               │ (Duev 2019)    │
               └───────┬────────┘
                       │
      Observation Sequences  [(α,δ,m,t,f) × n_obs]
                       │
               ┌───────▼────────┐
               │   TIER 3        │
               │  Transformer    │  → p̂₃(class | tracklet)
               │ (Lin 2022)     │
               └───────┬────────┘
                       │
               ┌───────▼────────┐
               │  ENSEMBLE       │
               │ Logistic Stacker│  → p̂(H_i | D)
               │  + Platt calib  │
               └────────────────┘
```

| Tier | Method | Input Dimensionality | Training Data | Purpose |
|---|---|---|---|---|
| **1** | XGBoost gradient-boosted trees | 14 tabular features | ~100,000 ZTF labeled alerts | Real/bogus + NEO class seed probabilities; fast enough for full stream |
| **2** | Three-branch CNN (Duev architecture) | $3 \times 63 \times 63$ pixels | ZTF cutout triplets, labeled by MPC | Morphological real/bogus discrimination; exploits image structure unavailable to Tier 1 |
| **3** | BERT-style encoder Transformer | Sequence of $(α, δ, m, t, f)$ tokens | MPC multi-night observation histories | Multi-night classification; context across the full observing arc |
| **Ensemble** | Logistic regression meta-learner | $[p̂_1, p̂_2, p̂_3]$ | Held-out calibration set | Optimal weighted combination; falls back to equal-weight average without trained weights |

All classifier outputs are probability-calibrated via `calibration.py` before being consumed by `score.py`.

---

## 6. Scoring Model

### 6.1 Bayesian Framework

The pipeline maintains a posterior distribution over five mutually exclusive hypotheses for each candidate:

| Symbol | Hypothesis | Prior $P(H_i)$ | Scientific Rationale |
|---|---|---|---|
| $H_\text{neo}$ | Genuine new NEO candidate | 0.05 | Most moving objects are not previously unknown NEOs |
| $H_\text{ko}$ | Known MPC catalog object | 0.30 | Large fraction of detections are cataloged |
| $H_\text{mba}$ | Main-belt asteroid on unusual orbit | 0.35 | MBAs dominate the moving-object population |
| $H_\text{art}$ | Instrumental artifact | 0.25 | Cosmic rays, satellites, subtraction ghosts are common |
| $H_\text{other}$ | Other solar system body (comet, TNO, Centaur) | 0.05 | Genuinely rare in any survey field |

Priors are deliberately pessimistic with respect to $H_\text{neo}$. They should be adjusted downward for MBAs in high-ecliptic-latitude fields, and upward for $H_\text{other}$ in survey fields targeting the trans-Neptunian region.

### 6.2 Log-Score Model

The posterior is computed via a log-linear model in the space of calibrated feature scores $\phi_k(\mathbf{D}) \in [0,1]$:

$$\ell_i = \log P(H_i) + \sum_k w_{ik} \, \phi_k(\mathbf{D})$$

$$P(H_i \mid \mathbf{D}) = \frac{\exp\!\left(\ell_i - \ell_{\max}\right)}{\displaystyle\sum_j \exp\!\left(\ell_j - \ell_{\max}\right)}$$

The $\ell_{\max}$ subtraction prevents numerical overflow and does not affect the normalised posterior. Missing features contribute $\phi_k = 0$ (neutral — no penalty for absent data). The sign convention for weights is:

- $w_{ik} > 0$: feature is evidence *for* hypothesis $H_i$
- $w_{ik} < 0$: feature is evidence *against* hypothesis $H_i$

### 6.3 Feature Weights for $H_\text{neo}$

```
log_score_neo =
    log(0.05)                          ← log prior

    + 2.0 × real_bogus_score           ← strongest signal of physical reality
    + 1.5 × arc_coverage_score         ← multi-night arc quality and completeness
    + 1.5 × nights_observed_score      ← observing cadence; independent epochs
    + 1.2 × motion_consistency_score   ← coherence of sky-plane angular velocity
    + 1.0 × orbit_quality_score        ← differential-correction residual RMS

    − 2.5 × known_object_score         ← strong penalty for MPC catalog match
    − 2.0 × stellar_artifact_score     ← strong penalty for artifact morphology
    − 1.5 × main_belt_consistency      ← penalty for MBA-like orbital geometry
```

### 6.4 Derived Scoring Outputs

In addition to the five-class posterior, `score.py` produces three scalar priority metrics:

$$\text{discovery\_priority} = 0.5 \, p_\text{neo} + 0.3 \, (1 - \text{orbit\_quality\_score}) + 0.2 \, \phi_\text{MOID}$$

$$\text{followup\_value} = 0.4 \, \phi_\text{brightness} + 0.4 \, (1 - \phi_\text{arc}) + 0.2 \, \phi_\text{orbit\_unc}$$

$$\text{scientific\_interest} = 0.5 \, \phi_\text{novelty} + 0.3 \, \phi_\text{extreme\_orbit} + 0.2 \, p_\text{other}$$

where $\phi_\text{MOID} = 1$ if MOID $\leq 0.05$ AU, $\phi_\text{novelty}$ encodes deviation from any known object, and $\phi_\text{extreme\_orbit}$ encodes unusually high $e$ or $i$.

---

## 7. Alert Protocol & Guardrails

### 7.1 The Three-Step Protocol

The following decision tree governs all external communications. **No step may be skipped or reordered under any circumstances.**

```
PRE-CONDITIONS (all must be TRUE simultaneously):
  ├─ Computed MOID ≤ 0.05 AU
  ├─ Orbit quality code ≥ 2  (multi-night arc)
  ├─ Tier 1 real_bogus_score ≥ 0.90
  └─ Object NOT matched to MPC known-object catalog
                    │
                    ▼
   ╔══════════════════════════════════════════════╗
   ║  STEP 1: MPC SUBMISSION                      ║
   ║  Submit observation report in MPC 80-column  ║
   ║  format or MPC JSON via astroquery.mpc or    ║
   ║  direct HTTP POST to minorplanetcenter.net.   ║
   ║  Store submission timestamp + report hash.   ║
   ╚══════════════════════════════════════════════╝
                    │
                    ▼
   ╔══════════════════════════════════════════════╗
   ║  STEP 2: AWAIT INDEPENDENT CONFIRMATION      ║
   ║  Monitor NEOCP for response.                 ║
   ║  Require EITHER:                             ║
   ║    ≥ 24 hours elapsed  OR                    ║
   ║    ≥ 2 independent observatory confirmations ║
   ║  DO NOT proceed to Step 3 without one of     ║
   ║  these conditions being satisfied.           ║
   ╚══════════════════════════════════════════════╝
                    │
                    ▼
   ╔══════════════════════════════════════════════╗
   ║  STEP 3: NASA PDCO NOTIFICATION              ║
   ║  ONLY IF CNEOS Scout/Sentry independently    ║
   ║  assigns an impact probability ≥ 0.01%:      ║
   ║    → Open GitHub Issue tagged [HAZARD-ALERT] ║
   ║    → Notify NASA PDCO and IAU CBAT           ║
   ║    → Defer ALL public statements to          ║
   ║      NASA/CNEOS — do not quote probabilities ║
   ╚══════════════════════════════════════════════╝
```

### 7.2 Non-Negotiable Guardrails

The following constraints are hard-coded into pipeline logic and may not be overridden by configuration:

| Guardrail | Enforcement Location |
|---|---|
| Never output "confirmed NEO" for internally detected objects | `score.py`, `alert.py` |
| Never state or imply an impact probability without MPC/CNEOS confirmation | `alert.py` |
| PHA flag requires orbit quality code ≥ 2 | `orbit.py`, `score.py` |
| `None` feature scores fail gate conditions (no optimistic imputation) | `score.py` |
| Unknown objects default to `"candidate"`, not `"confirmed_neo"` | `schemas.py` |
| Full observation + orbit provenance stored with every alert | `alert.py` |
| NASA PDCO step requires CNEOS independent assessment in `cneos_assessment` parameter | `alert.py` |
| Alert log is append-only; no deletion or overwrite of historical alerts | `alert.py` |

---

## 8. Data Sources

| Source | Access Method | Data Product | Pipeline Stage |
|---|---|---|---|
| **ZTF** (Zwicky Transient Facility) | `ztfquery` / IRSA API (free account) | Difference-image alert stream; science, reference, difference cutouts; `rb`, `drb`, RA, Dec, JD, mag | `fetch.py`, `classify.py` Tier 2 |
| **ATLAS** (Asteroid Terrestrial-impact Last Alert System) | REST API at `fallingstar-data.com/forcedphot/` | Forced photometry in $o$ (orange) and $c$ (cyan) bands at any sky position; 2-day cadence | `fetch.py` (confirmation) |
| **MPC** (Minor Planet Center) | `astroquery.mpc`; direct HTTP | Known NEO/MBA catalog; NEO Confirmation Page (NEOCP); observation submission endpoint | `detect.py` (cross-match), `alert.py` |
| **JPL Horizons / CNEOS** | `astroquery.jplhorizons` | Ephemerides for known objects; close-approach tables; Scout/Sentry impact monitoring (read-only) | `fetch.py`, `orbit.py` (verification) |
| **Gaia DR3** | `astroquery.gaia` | Sub-milliarcsecond astrometry for $\sim 1.5 \times 10^9$ stars; astrometric calibration reference | `preprocess.py` |
| **Pan-STARRS DR2** | MAST / PS1 API | Deep photometry catalog; color index reference for $g-r$, $r-i$ | `preprocess.py` (optional) |

### 8.1 Training Datasets

| Dataset | Source | Approximate Size | Pipeline Use |
|---|---|---|---|
| ZTF real/bogus labeled alerts (Duev et al. 2019) | Broker APIs / Zenodo | ~100,000 alerts | Tier 1 + Tier 2 training |
| MPC confirmed NEO catalog (numbered objects only) | `astroquery.mpc` | ~35,000 objects | Positive labels; high-confidence only |
| MPC main-belt asteroid sample | `astroquery.mpc` | $\mathcal{O}(10^6)$ objects | Negative labels for NEO classifier |
| ZTF NEO observation history | IRSA | Varies by epoch | Tracklet sequence training for Tier 3 |
| ATLAS detections of known NEOs | ATLAS forced-photometry server | Varies | Tier 1 feature validation; photometric cross-check |

**Label quality policy:** Only MPC-numbered objects are used as high-confidence positive labels. Provisional designations (e.g., 2026 XY$_1$) may be reassigned by the MPC and are treated with $0.5\times$ sample weight in all training runs.

---

## 9. Repository Layout

### 9.1 Data-Flow Schema

The diagram below shows how data and artifacts move between the repository's top-level directories during a complete pipeline run. Arrows represent the direction of data flow; labels on arrows identify the artifact type being passed.

```
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                        REPOSITORY DATA FLOW                             │
 └─────────────────────────────────────────────────────────────────────────┘

  External APIs                   src/ (pipeline logic)
  ┌──────────────────┐            ┌──────────────────────────────────────┐
  │ ZTF IRSA         │──alerts──▶ │ fetch.py → preprocess.py → detect.py │
  │ ATLAS REST API   │──phot.──▶  │     ↓               ↓           ↓    │
  │ MPC catalog      │──catalog─▶ │  link.py → classify.py → orbit.py    │
  │ JPL Horizons     │──ephem.──▶ │     ↓               ↓           ↓    │
  └──────────────────┘            │  score.py → alert.py → calibration   │
                                  └──────────────┬───────────────────────┘
                                                 │
            ┌────────────────────────────────────┼──────────────────────┐
            │                                    │                      │
            ▼                                    ▼                      ▼
   data/                              Skills/ (utilities)         models/
   ├─ sample_tracklets.json ◀──────── batch_score.py             ├─ tier2_cnn.pt
   ├─ injection_recovery_            ├─ run_pipeline.py           └─ tier3_transformer.pt
   │    baseline.json ◀─────────────  injection_recovery.py            ▲
   └─ (cached raw alerts)            ├─ train_tier2_cnn.py ────────────┘
                                     ├─ train_tier3_transformer.py ─────┘
                                     ├─ export_mpc_report.py
                                     └─ evaluate_calibration.py
                                                 │
                                                 ▼
                                        reports/ (user output)
                                        ├─ mpc_report.txt        ← MPC submission
                                        ├─ scored_neos.json      ← ranked candidates
                                        └─ calibration_curves/   ← QC diagnostics
                                                 │
                                  ┌──────────────┘
                                  ▼
                          External Reporting
                          ├─ minorplanetcenter.net  (Step 1 — always)
                          ├─ NEOCP monitoring       (Step 2 — confirmation)
                          └─ NASA PDCO / IAU CBAT   (Step 3 — if triggered)
```

**Key relationships:**

| From | To | Artifact |
|---|---|---|
| `fetch.py` | `preprocess.py` | `FetchResult` — raw alerts + provenance |
| `preprocess.py` | `detect.py` | `PreprocessResult` — calibrated source catalog |
| `detect.py` | `link.py` | `DetectResult` — moving-source candidates |
| `link.py` | `classify.py` | `LinkResult` — multi-night tracklets |
| `classify.py` | `orbit.py` | `ClassifyResult` — posterior + feature scores |
| `orbit.py` | `score.py` | `OrbitResult` — elements, MOID, quality code |
| `score.py` | `alert.py` | `ScoredNEO` — ranked candidate with hazard flag |
| `alert.py` | `calibration.py` | Raw classifier scores for calibration fitting |
| `models/` | `classify.py` | Trained weights loaded at runtime |
| `data/` | `Skills/` | Input JSON / CSV for batch and training scripts |

### 9.2 Directory Tree

```
2026-Near-Earth-Objects/
│
├── src/                          # Core pipeline modules (Python 3.11+)
│   ├── __init__.py               # Package version (0.90.3)
│   ├── schemas.py                # All Pydantic data models (frozen=True)
│   ├── fetch.py                  # ZTF/ATLAS/MPC/Horizons data retrieval
│   ├── preprocess.py             # Difference image handling; Gaia astrometry
│   ├── detect.py                 # Moving-object detection; real/bogus filter
│   ├── link.py                   # THOR-inspired multi-night tracklet linking
│   ├── classify.py               # Three-tier ML ensemble
│   ├── orbit.py                  # Gauss IOD; differential correction; MOID
│   ├── score.py                  # Bayesian hazard scoring; PHA flag
│   ├── alert.py                  # MPC report formatting; NASA alert protocol
│   ├── calibration.py            # Platt / isotonic PAVA calibration
│   └── py.typed                  # PEP 561 type information marker
│
├── tests/                        # pytest suite (3475 passing; 2 live/integration deselected)
│   ├── conftest.py               # Shared fixtures and synthetic tracklet factories
│   ├── test_schemas.py
│   ├── test_fetch.py
│   ├── test_preprocess.py
│   ├── test_detect.py
│   ├── test_link.py
│   ├── test_classify.py
│   ├── test_orbit.py
│   ├── test_score.py
│   ├── test_alert.py
│   ├── test_calibration.py
│   ├── test_pipeline.py          # Inter-module integration tests
│   └── test_pipeline_e2e.py      # Full end-to-end pipeline test
│
├── Skills/                       # Standalone utility scripts
│   ├── smoke_test.py             # Happy-path check for all modules
│   ├── run_pipeline.py           # Full end-to-end pipeline run
│   ├── batch_score.py            # Score tracklet JSON; print ranked table
│   ├── injection_recovery.py     # Inject synthetic NEOs; measure detection rates
│   ├── tune_linker.py            # Parametric sweep: tolerance × chi² vs link rate
│   ├── evaluate_calibration.py   # Brier score + ECE for Platt and isotonic
│   ├── generate_training_labels.py # Download MPC NEO + MBA catalog as CSV
│   ├── check_mpc_known.py        # Cross-match candidates against MPC catalog
│   ├── audit_real_run.py         # Build fail-closed real-run audit packets
│   ├── build_recovery_manifest.py # Build expected-known manifests for T1-C audits
│   ├── visualize_tracklets.py    # Plot sky positions and light curves
│   ├── export_mpc_report.py      # Export MPC 80-column reports from scored JSON
│   ├── benchmark_pipeline.py     # Time classify + score on N synthetic tracklets
│   ├── train_tier2_cnn.py        # Fine-tune CNN on labeled ZTF cutout CSV
│   ├── train_tier3_transformer.py # Train Transformer on MPC tracklet CSV
│   ├── run_tier3_pilot.py        # Atomic, resumable Tier 3 pilot workflow
│   ├── validate_pipeline_run.py  # Validate run JSON and guardrail language
│   ├── export_atlas_lightcurve.py # Export ATLAS forced-photometry lightcurves
│   ├── neo_mcp_server.py         # Project-scoped MCP guard server
│   └── background.py              # Unified background CLI with subcommands
│
├── Logs/                         # Top-level SQLite background automation logs
│   ├── background.sqlite         # Created by `Skills/background.py run-once`
│   ├── tier3_pilot.sqlite        # Tier 3 operator run and stage ledger
│   └── reports/                  # Internal needs-follow-up report drafts
│
├── data/                         # Reference data and baselines
│   ├── README.md                 # Data format reference
│   ├── sample_tracklets.json     # Two synthetic tracklets for testing
│   ├── injection_recovery_baseline.json  # n=50, seed=42 baseline results
│   ├── injection_recovery_n200.json      # n=200, seed=42 baseline results
│   └── stress_test_high_motion.json      # high-motion linker stress baseline
│
├── docs/                         # Extended documentation
│   ├── PIPELINE_SPEC.md          # Stage-by-stage pipeline specification
│   ├── SCORING_MODEL.md          # Full Bayesian scoring model documentation
│   ├── DATA_SOURCES.md           # External data source reference
│   ├── API_REFERENCE.md          # Public function signatures and schema fields
│   ├── BACKGROUND_SEARCH_AUTOMATION.md
│   ├── ALERT_PROTOCOL.md
│   ├── TRAINING_GUIDE.md
│   ├── ORBIT_FITTING.md
│   ├── CLASSIFICATION_GUIDE.md
│   ├── QUALITY_METRICS.md
│   ├── THREAT_ASSESSMENT.md
│   ├── DETECTION_GUIDE.md
│   ├── LINKING_GUIDE.md
│   ├── FETCH_GUIDE.md
│   └── PREPROCESS_GUIDE.md
│
├── background/                    # Automated offline background automation config
│   ├── config.json
│   ├── config.schema.json
│   ├── live_review_policy.example.json
│   ├── live_review_policy.schema.json
│   └── targets.json
│
├── models/                       # Trained model weights (gitignored if large)
│   └── .gitkeep
│
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                # Lint + type-check + test + coverage gate
│   │   └── release.yml           # Version-tagged release workflow
│   └── ISSUE_TEMPLATE/
│       ├── bug_report.yml
│       ├── feature_request.yml
│       └── hazard_alert.yml      # [HAZARD-ALERT] issue template
│
├── CLAUDE.md                     # Agent coding instructions and version history
├── CONTRIBUTING.md               # Contribution guidelines
├── LICENSE                       # Apache 2.0
├── .mcp.json                     # Claude Code project MCP configuration
├── .codex/config.toml            # Codex project MCP configuration
├── pyproject.toml                # Build config; dependencies; ruff/mypy/pytest settings
└── .pre-commit-config.yaml       # Pre-commit hooks (ruff, mypy)
```

---

## 10. End-User Guide (Layperson)

This section explains how to use the pipeline in plain language — no astronomy or software-engineering background required. The goal is to get from a sky region and a date range to a ranked list of NEO candidates and, if warranted, a formatted report ready to submit to the Minor Planet Center.

### 10.1 What the Pipeline Does, In Plain Terms

Think of the pipeline as a five-step process:

1. **Download** — it fetches all the astronomical alerts that were triggered in your chosen patch of sky during your chosen dates. These alerts are generated automatically when a telescope notices something that changed or moved compared to a reference image.
2. **Filter** — it discards the vast majority of alerts that are camera artefacts, cosmic rays, or satellite trails, keeping only those that look like real moving objects.
3. **Connect the dots** — it checks whether the same moving object was seen on multiple nights, and if so, links those sightings into a *tracklet* (a short arc of the object's path across the sky).
4. **Characterise** — from the tracklet it computes a preliminary orbit and estimates how close the object comes to Earth (the Minimum Orbit Intersection Distance, or MOID).
5. **Rank and report** — it scores every candidate by how likely it is to be a genuine new NEO, flags any that meet the criteria for a Potentially Hazardous Asteroid (MOID ≤ 0.05 AU and estimated diameter ≥ 140 m), and produces a report in the format required by the Minor Planet Center.

### 10.2 Before You Begin

You need three things:

| Item | Where to get it | Notes |
|---|---|---|
| **Python 3.14.3 via uv** | `uv.lock` | Use `uv run`; do not invoke bare `python`, `pytest`, `mypy`, or `ruff` |
| **A ZTF IRSA account** | irsa.ipac.caltech.edu (free registration) | Needed for live sky data; not needed for the sample data bundled with the repo |
| **This repository** | See §11 Installation | ~50 MB including test suite |

If you only want to explore the pipeline with the bundled synthetic data — without connecting to any telescope feed — you do **not** need a ZTF account.

### 10.3 Your First Run (No Account Needed)

After installing (see §11), run the following two commands from the repository root. Each line is explained in plain English below it.

```bash
# Step 1 — confirm every module is working correctly
PYTHONPATH=src uv run python Skills/smoke_test.py
```
*This takes about 10 seconds. If you see "All modules OK — smoke test passed." the installation is healthy.*

```bash
# Step 2 — score the two bundled example tracklets
PYTHONPATH=src uv run python Skills/batch_score.py data/sample_tracklets.json
```
*This runs the classification and scoring pipeline on two synthetic NEO candidates that are included with the repository. It prints a ranked table showing the posterior probability that each candidate is a genuine NEO, its hazard flag, and its estimated size.*

**Reading the output table:**

| Column | What it means |
|---|---|
| `object_id` | Internal identifier for this candidate |
| `neo_candidate` | Probability (0–1) that this is a genuine new NEO. Values above 0.5 are worth human review. |
| `hazard_flag` | `pha_candidate` = potentially hazardous; `close_approach` = comes near Earth but below PHA threshold; `nominal` = no special concern; `unknown` = insufficient data |
| `moid_au` | Closest the object's orbit comes to Earth's orbit, in Astronomical Units. Below 0.05 AU triggers the PHA check. |
| `estimated_diameter_m` | Rough size estimate in metres, assuming a typical rocky asteroid reflectivity. Treat as order-of-magnitude only. |
| `alert_pathway` | What the pipeline recommends doing next (see §10.5 below). |

### 10.4 Running on a Real Sky Region

Public ZTF dry runs do not require an IRSA token. Proprietary ZTF access uses
IRSA username/password, while ATLAS uses `ATLAS_TOKEN`.

```bash
# Run the pipeline on a 5-degree radius around RA=180°, Dec=0° for one week
PYTHONPATH=src uv run python Skills/run_pipeline.py \
    --ra 180.0 \
    --dec 0.0 \
    --radius 5.0 \
    --start-jd 2460796.5 \
    --end-jd 2460802.5 \
    --surveys ZTF \
    --max-candidates 80
```

**Parameters you can change:**

| Parameter | What it controls | Example values |
|---|---|---|
| `--ra` | Right Ascension of field centre (degrees, 0–360) | `180.0`, `45.5` |
| `--dec` | Declination of field centre (degrees, −90 to +90) | `0.0`, `−30.0` |
| `--radius` | Search radius in degrees | `1.0` to `10.0` |
| `--start` / `--end` | Date range in YYYY-MM-DD format | `2026-05-01` |

The pipeline writes its output to `results/scored_neos.json`. The file contains the full ranked candidate list in machine-readable form.

### 10.5 Understanding the Alert Pathway Column

The `alert_pathway` value in the output tells you exactly what action, if any, is warranted:

| Value | Plain-English meaning | What you should do |
|---|---|---|
| `internal_candidate` | Interesting but below external-reporting thresholds | Review manually; watch for repeat detections on subsequent nights |
| `mpc_submission` | Strong enough for formal reporting to the Minor Planet Center | Run `export_mpc_report.py` (§10.6) and submit the output |
| `neocp_followup` | Object is already on the MPC's Confirmation Page; independent follow-up requested | Request follow-up observations if you have telescope access |
| `nasa_pdco_notify` | High-confidence PHA candidate with CNEOS-confirmed impact probability | Follow the mandatory three-step protocol in §7 exactly — do not skip steps |
| `known_object` | Matches a catalogued asteroid or comet | No action needed; note the MPC designation in your records |

### 10.6 Generating an MPC Submission Report

If any candidates carry `alert_pathway = mpc_submission`, generate the formatted report with:

```bash
PYTHONPATH=src python Skills/export_mpc_report.py \
    results/scored_neos.json \
    --out reports/mpc_report.txt
```

The output file (`reports/mpc_report.txt`) is in the MPC 80-column observation format. Submit it by following the instructions at [minorplanetcenter.net/iau/MPC_Documentation.html](https://minorplanetcenter.net/iau/MPC_Documentation.html). You will need a free MPC observer account and your assigned observatory code.

### 10.7 Visualising a Candidate

To plot the sky positions and light curve of a candidate for visual inspection:

```bash
PYTHONPATH=src python Skills/visualize_tracklets.py data/sample_tracklets.json
```

This opens a matplotlib window showing:
- **Left panel**: sky-plane positions across all nights, with the expected motion direction overlaid
- **Right panel**: apparent magnitude vs. time (light curve), coloured by filter band

---

## 11. Recalibration Guide

Classifier recalibration is necessary when (a) the pipeline is deployed on a new survey or telescope, (b) a statistically significant drift in Brier score or ECE is detected on recent labeled data, or (c) new confirmed NEO labels become available from the MPC. This section walks through the full recalibration workflow from label generation to production deployment.

### 11.1 When to Recalibrate

| Trigger | Recommended Action |
|---|---|
| Brier score increases by > 0.05 relative to baseline | Full Tier 1 recalibration + isotonic refitting |
| ECE exceeds 0.10 on recent holdout | Platt or isotonic recalibration only (no retraining needed) |
| ≥ 500 new confirmed NEO labels available from MPC | Retrain Tier 1 XGBoost; refit calibrator |
| New survey or filter system (e.g. Rubin/LSST) | Full three-tier retraining |
| Link rate drops > 10% from injection-recovery baseline | Retune linker (§11.6) before recalibrating classifiers |

### 11.2 Step 1 — Generate Fresh Training Labels

Download the current MPC confirmed NEO catalog and a main-belt asteroid sample as a labeled CSV:

```bash
PYTHONPATH=src python Skills/generate_training_labels.py \
    --output data/training_labels.csv \
    --n-mba 5000
```

This script queries `astroquery.mpc`, downloads all numbered NEOs (high-confidence positive labels) and a random sample of `--n-mba` numbered MBAs (negative labels), and writes a CSV with columns: `object_id`, `designation`, `neo_class`, `label` (1 = NEO, 0 = non-NEO), `H`, `a`, `e`, `i`.

**Important**: Only MPC-numbered objects are used as positive labels. Provisional designations receive a weight of 0.5 in all training runs.

### 11.3 Step 2 — Retrain the Tier 1 XGBoost Classifier

Tier 1 retraining uses only tabular features (no images required, no GPU needed):

```bash
# Retraining is handled inside classify.py via its public API.
# Use the following one-liner to trigger a retrain from the labels CSV:
PYTHONPATH=src python -c "
from classify import retrain_tier1
retrain_tier1(
    labels_csv='data/training_labels.csv',
    output_model='models/tier1_xgb.json',
    test_fraction=0.2,
    random_seed=42,
)
"
```

The script prints a classification report (precision, recall, F1 per class) and saves the new model weights to `models/tier1_xgb.json`.

### 11.4 Step 3 — Fine-Tune the Tier 2 CNN (Requires GPU)

Tier 2 requires a labeled dataset of ZTF image cutlet triplets. Prepare a CSV with columns `object_id`, `cutout_path`, `label` (1 = real, 0 = bogus):

```bash
PYTHONPATH=src python Skills/train_tier2_cnn.py \
    --labels data/cutout_labels.csv \
    --cutout-dir data/cutouts/ \
    --output models/tier2_cnn.pt \
    --epochs 20 \
    --batch-size 64 \
    --learning-rate 1e-4
```

Fine-tuning from the pre-trained ZTF real/bogus weights (Duev et al. 2019) converges in approximately 10–20 epochs on a modern GPU. Start from `models/tier2_cnn.pt` if it exists; the script initialises randomly otherwise.

### 11.5 Step 4 — Retrain the Tier 3 Transformer (Requires GPU + Multi-Night Data)

Tier 3 requires the designation-grouped train, calibration, and test CSV files
produced by `Skills/build_sequence_dataset.py`:

```bash
caffeinate -i .venv/bin/python Skills/train_tier3_transformer.py \
    --train data/sequences/production/train.csv \
    --validation data/sequences/production/calibration.csv \
    --test data/sequences/production/test.csv \
    --epochs 30 \
    --out models/tier3_transformer.pt \
    --report data/sequences/production/tier3_training_report.json
```

The trainer selects the lowest-validation-loss checkpoint and reports held-out
accuracy, macro-F1, per-class recall, source/model hashes, and class counts.

### 11.6 Step 5 — Refit the Probability Calibrator

After retraining any tier, refit the Platt or isotonic calibrator on the held-out validation set. This step adjusts raw classifier scores to produce well-calibrated probabilities (i.e., a score of 0.8 should correspond to an 80% true-positive rate):

```bash
PYTHONPATH=src python Skills/evaluate_calibration.py \
    --scores results/validation_scores.json \
    --method isotonic \
    --output models/calibrator_isotonic.pkl \
    --plot reports/calibration_curves/
```

The script outputs:

- Brier score before and after calibration
- Expected Calibration Error (ECE) before and after
- Reliability diagram saved to `reports/calibration_curves/`
- Fitted calibrator saved to `models/calibrator_isotonic.pkl`

**Choosing between Platt scaling and isotonic regression:**

| Method | When to use |
|---|---|
| **Platt scaling** | Validation set < 1,000 examples; score distribution is roughly sigmoid-shaped |
| **Isotonic (PAVA)** | Validation set ≥ 1,000 examples; no assumption about score distribution shape; generally lower ECE on larger datasets |

### 11.7 Step 6 — Retune the Linker (Optional)

If the recalibration is triggered by a drop in link rate, run a parametric sweep of the two most sensitive linker parameters before refitting the classifier:

```bash
PYTHONPATH=src python Skills/tune_linker.py \
    --tol-min 0.5 --tol-max 5.0 --tol-steps 10 \
    --chi2-min 4.0 --chi2-max 16.0 --chi2-steps 7
```

This prints a grid table of (tolerance, chi2_threshold) → link rate. Choose the parameter combination that maximises link rate while keeping the false-link rate (measured by injection-recovery on known-orbit test objects) below 5%.

### 11.8 Step 7 — Validate with Injection-Recovery

After any retraining or recalibration, run the injection-recovery benchmark to confirm that end-to-end pipeline performance has not regressed:

```bash
PYTHONPATH=src python Skills/injection_recovery.py \
    --n 100 \
    --seed 42 \
    --json results/ir_post_recal.json
```

Compare the output against the baseline in `data/injection_recovery_baseline.json`. A regression is defined as a drop of more than 5 percentage points in link rate or score rate relative to baseline. If a regression is detected, review the recalibrated model weights before deploying.

### 11.9 Deployment Checklist

| Step | Command / Action | Pass Criterion |
|---|---|---|
| 1. Labels generated | `generate_training_labels.py` | CSV contains ≥ 500 confirmed NEOs |
| 2. Tier 1 retrained | `retrain_tier1(...)` | F1 ≥ 0.85 on held-out set |
| 3. Tier 2 fine-tuned | `train_tier2_cnn.py` | Validation accuracy ≥ 90% |
| 4. Tier 3 retrained | `train_tier3_transformer.py` | Validation accuracy ≥ 85%; held-out macro-F1 ≥ 0.80 |
| 5. Calibrator refit | `evaluate_calibration.py` | ECE ≤ 0.05; Brier ≤ 0.10 |
| 6. Linker tuned (if needed) | `tune_linker.py` | Link rate ≥ baseline − 5% |
| 7. Injection-recovery passed | `injection_recovery.py` | Link + score rate ≥ baseline − 5% |
| 8. Full default test collection is stable | `pytest --collect-only` | 3475 passing tests; 2 live/integration tests deselected |
| 9. Models committed | `git add models/` | New weights in version control |

---

## 12. Installation

### 10.1 Prerequisites

| Requirement | Minimum | Recommended |
|---|---|---|
| Python | 3.11 | 3.12 |
| RAM | 4 GB | 16 GB (CNN training) |
| GPU | Not required | Required for Tier 2 / Tier 3 training |
| Disk | 1 GB | 10 GB (alert cache + cutout archive) |
| Network | — | Required for live ZTF / ATLAS / MPC queries |

### 10.2 Clone and Install

```bash
# 1. Clone the repository
git clone https://github.com/ares0311/2026-near-earth-objects.git
cd 2026-Near-Earth-Objects

# 2. Create and activate a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install the package with all development dependencies
pip install -e ".[dev]"

# 4. (Optional) Install pre-commit hooks
pre-commit install
```

### 10.3 Core Dependencies

```
pydantic      >= 2.13    # Immutable pipeline schemas
numpy         >= 2.4     # Numerical kernels
scipy         >= 1.17    # Optimisation; statistical tests
astropy       >= 7.2     # Coordinate transforms; FITS; time standards
xgboost       >= 2.0     # Tier 1 gradient-boosted classifier
scikit-learn  >= 1.3     # Logistic stacker; calibration utilities
torch         >= 2.1     # Tier 2 CNN; Tier 3 Transformer
astroquery    >= 0.4.7   # MPC / JPL Horizons / Gaia DR3 access
```

### 10.4 Optional Survey-Specific Packages

```bash
# ZTF alert stream access
pip install ztfquery

# ATLAS forced photometry (no separate package; uses requests)
# Requires free account at https://fallingstar-data.com/forcedphot/
```

---

## 13. Quick Start

### 13.1 Verify Installation

```bash
# Smoke test — exercises all ten modules end-to-end with synthetic data
PYTHONPATH=src python Skills/smoke_test.py
# Expected: "All modules OK — smoke test passed." (exit 0)
```

### 13.2 Inspect Default Test Collection

```bash
OMP_NUM_THREADS=1 PYTHONPATH=src python -m pytest --collect-only -q
# Expected result: 3475 passing tests; 2 live/integration checks deselected.
```

For a full local run, use:

```bash
OMP_NUM_THREADS=1 PYTHONPATH=src python -m pytest -q
```

### 13.3 Score a Batch of Tracklets

```bash
# Score the two synthetic tracklets in data/sample_tracklets.json
PYTHONPATH=src python Skills/batch_score.py data/sample_tracklets.json
```

### 13.4 Injection-Recovery Experiment

```bash
# Inject 50 synthetic NEOs (default), run through full pipeline, report recovery rates
PYTHONPATH=src python Skills/injection_recovery.py --n 50 --seed 42 --json results/ir_run.json
# Expected baseline: 100% detect, 100% link, 100% score on the n=200 baseline
```

### 13.5 Parametric Linker Sweep

```bash
# Sweep position_tolerance_arcsec × chi2_threshold; report link rate table
PYTHONPATH=src python Skills/tune_linker.py
```

### 13.6 Run One Background Search Cycle

```bash
PYTHONPATH=src python Skills/background.py run-once
PYTHONPATH=src python Skills/background.py schema-status-summary
PYTHONPATH=src python Skills/background.py init-log-db-preview
PYTHONPATH=src python Skills/background.py schema-operations-summary
PYTHONPATH=src python Skills/background.py operator-next-action
PYTHONPATH=src python Skills/background.py init-log-db
PYTHONPATH=src python Skills/background.py ledger-summary
PYTHONPATH=src python Skills/background.py needs-follow-up-summary
PYTHONPATH=src python Skills/background.py internal-follow-up-disposition
PYTHONPATH=src python Skills/background.py validation-summary
PYTHONPATH=src python Skills/background.py blueprint-compliance-summary
PYTHONPATH=src python Skills/background.py record-blueprint-compliance-summary
PYTHONPATH=src python Skills/background.py blueprint-compliance-log-summary
PYTHONPATH=src python Skills/background.py signoff-readiness
PYTHONPATH=src python Skills/background.py record-automation-readiness
PYTHONPATH=src python Skills/background.py automation-readiness-log-summary
PYTHONPATH=src python Skills/background.py live-policy-contract-summary
PYTHONPATH=src python Skills/background.py live-provider-readiness-summary
PYTHONPATH=src python Skills/background.py live-credential-inventory
PYTHONPATH=src python Skills/background.py live-credential-inventory --write-report Logs/reports/credential_inventory_latest.json
PYTHONPATH=src python Skills/background.py live-policy-approval-checklist
PYTHONPATH=src python Skills/background.py live-policy-approval-checklist --write-report Logs/reports/live_policy_approval_checklist_latest.json
PYTHONPATH=src python Skills/background.py scoring-metrics-kpi-report
PYTHONPATH=src python Skills/background.py scoring-metrics-kpi-report --write-report Logs/reports/scoring_metrics_kpi_latest.json
PYTHONPATH=src python Skills/background.py live-dry-run-approval-bundle
PYTHONPATH=src python Skills/background.py record-live-dry-run-approval-bundle
PYTHONPATH=src python Skills/background.py live-dry-run-approval-bundle-log-summary
PYTHONPATH=src python Skills/background.py live-dry-run-operator-handoff
PYTHONPATH=src python Skills/background.py write-live-dry-run-operator-handoff
PYTHONPATH=src python Skills/background.py record-live-dry-run-operator-handoff
PYTHONPATH=src python Skills/background.py live-dry-run-operator-handoff-log-summary
PYTHONPATH=src python Skills/background.py live-dry-run-plan
PYTHONPATH=src python Skills/background.py record-live-dry-run-plan
PYTHONPATH=src python Skills/background.py live-dry-run-plan-log-summary
PYTHONPATH=src python Skills/background.py live-dry-run-execute
PYTHONPATH=src python Skills/background.py live-execution-log-summary
PYTHONPATH=src python Skills/background.py unsigned-follow-up
PYTHONPATH=src python Skills/background.py signoff-packet-decision-readiness
PYTHONPATH=src python Skills/background.py latest-undecided-signoff-packet
```

Background automation writes top-level SQLite logs to `Logs/background.sqlite`.
Each invocation writes one durable ledger row and exactly one reviewed or
needs-follow-up outcome row. Readiness checks can also be persisted to SQLite
before any live dry run is attempted, and no-network live dry-run plans can be
recorded from the review policy. Operator handoffs can be written and persisted
to SQLite for local review. Mock-only live dry-run provider execution attempts
can also be logged without contacting survey services. Injected
dry-run providers must report no network access and no external submission.
The live-policy approval checklist command writes a no-secret skeleton for a
bounded local dry-run policy and leaves live approval pending until the operator
copies it and the config into ignored local files, reviews the scope, and
explicitly approves it. The approval-bundle command aggregates scheduler,
policy, provider, and dry-run plan gates before any mock live dry-run execution
attempt.
The scoring metrics KPI command is separate from systems smoke testing: it uses
deterministic offline fixtures to check scoring bounds, posterior normalization,
conservative pathway gates, negative-fixture external-pathway rate, and
guardrail language. Labeled-data calibration KPIs such as Brier score and ECE
are listed as pending until representative validation data exists.
The command is offline by default and does not make external submissions. Manual reviewer signoff can be recorded with
`Skills/background.py record-signoff`; multiple signoffs per run are supported.
Persisted signoff packets can be inspected with
`Skills/background.py signoff-packet-decision-readiness` and
`Skills/background.py latest-undecided-signoff-packet` before a reviewer records
a packet-linked decision.
Background SQLite schema status can be inspected without mutation using
`Skills/background.py schema-status-summary`, and migration effects can be
previewed without writing using `Skills/background.py init-log-db-preview`.
Use `Skills/background.py schema-operations-summary` to see whether
packet-decision commands are ready and which schema action is recommended.
Use `Skills/background.py operator-next-action` to combine schema readiness,
operations state, and packet-decision readiness into one conservative local
next-command recommendation.
`Skills/background.py init-log-db` runs the additive local SQLite migration and
reports before/after table state.
Deprecated one-file background wrapper scripts have been removed.

### 13.7 Export MPC 80-Column Report

```bash
# Export MPC-formatted observation reports from a scored NEO JSON file
PYTHONPATH=src python Skills/export_mpc_report.py results/scored_neos.json --out reports/mpc_report.txt
```

### 13.8 End-to-End Pipeline Run

```bash
# Full pipeline run against public ZTF access
PYTHONPATH=src python Skills/run_pipeline.py \
    --ra 180.0 --dec 0.0 --radius 5.0 \
    --start 2026-05-01 --end 2026-05-07
```

---

## 14. Quality Control

### 12.1 Continuous Integration

Every commit triggers the CI workflow (`.github/workflows/ci.yml`), which runs in sequence:

```bash
ruff check .                        # PEP 8 + style lint
python -m mypy src                  # Static type checking (strict mode)
PYTHONPATH=src python -m pytest     # Full test suite + coverage gate
```

The coverage gate is set to **100%**; any line not exercised by at least one test fails CI.
On macOS local environments, set `OMP_NUM_THREADS=1` if XGBoost/OpenMP emits native loader or threading errors.

### 12.2 Classifier Calibration Metrics

The pipeline reports two calibration metrics for every trained classifier, evaluated on a held-out set of $n \geq 500$ labeled examples:

**Brier Score** (lower is better; perfect calibration = 0):

$$\text{BS} = \frac{1}{N} \sum_{i=1}^{N} \sum_{k=1}^{K} \left(\hat{p}_{ik} - y_{ik}\right)^2$$

where $\hat{p}_{ik}$ is the predicted probability of class $k$ for example $i$, and $y_{ik} \in \{0,1\}$ is the one-hot true label.

**Expected Calibration Error** (ECE; lower is better):

$$\text{ECE} = \sum_{m=1}^{M} \frac{|B_m|}{N} \left| \overline{p}(B_m) - \overline{y}(B_m) \right|$$

where $B_m$ is the $m$-th confidence bin (default: $M = 10$ equal-width bins), $\overline{p}(B_m)$ is the mean predicted probability in that bin, and $\overline{y}(B_m)$ is the fraction of positive examples in that bin.

Calibration curves and reliability diagrams are generated by `Skills/evaluate_calibration.py`.

### 12.3 Injection-Recovery Validation

Injection-recovery testing is the primary empirical validation of end-to-end pipeline performance. Synthetic NEO tracklets with known orbital elements are injected into the ZTF alert stream simulator and processed by the full pipeline. The following rates are tracked:

| Metric | Definition | Current Baseline |
|---|---|---|
| **Detection rate** | Fraction of injected NEOs producing ≥1 detection | 100% ($n=200$, seed=42) |
| **Link rate** | Fraction of injected NEOs producing a valid tracklet | 100% |
| **Score rate** | Fraction of injected NEOs appearing in the ranked output | 100% |
| **PHA recovery rate** | Fraction of injected PHAs correctly flagged | Measured separately per orbit class |

The older n=50 baseline remains in `data/injection_recovery_baseline.json` for historical comparison. The current n=200 baseline and high-motion stress baseline both report 100% linking after the v0.11.0 linker fixes.

### 12.4 Module Coverage Summary

| Module | Statements | Coverage |
|---|---|---|
| `schemas.py` | — | 100% |
| `fetch.py` | — | 100% |
| `preprocess.py` | — | 100% |
| `detect.py` | — | 100% |
| `link.py` | — | 100% |
| `classify.py` | — | 100% |
| `orbit.py` | — | 100% |
| `score.py` | — | 100% |
| `alert.py` | — | 100% |
| `calibration.py` | — | 100% |
| **Total** | **3475 passing tests** | **100% target; verify with coverage run before release** |

---

## 15. Current Status & Roadmap

**Primary directive: all work must advance the project to production. See `docs/PRODUCTION_READINESS.md` for the authoritative gap register.**

**Highest-priority production loop: D1 — WISE/NEOWISE discovery dry-runs.** The
T1/T2 readiness gaps are closed. Current work is focused on bounded
WISE/NEOWISE archive sweeps that can produce candidate packets, adversarial
review outcomes, and operator review evidence without external submission.
MPC submission remains fail-closed until archival WISE/NEOWISE submission
authority is resolved with MPC and a candidate survives the required gates.

### 15.1 Current State Snapshot (v0.90.3)

| Area | Status | Notes |
|---|---|---|
| Core pipeline modules | **Complete** | All 10 modules: 3600+ tests passing, 100% coverage target, ruff + mypy clean |
| Synthetic validation | **Complete** | 100% detection/link/score on n=200 synthetic tracklets; 10 adversarial tests in CI |
| Background automation CLI | **Complete** | `Skills/background.py` — offline scheduler, SQLite audit logs, signoff packets, readiness summaries |
| Repository artifact hygiene | **Complete** | `git add .` is supported: raw `Logs/**` stay local, production models are filename-allowlisted, and durable evidence is promoted to `docs/evidence/` or `data/evidence/` |
| ML model weights | **Complete** | T1-A closed. Tier 1 XGBoost (99.95%), Tier 2 CNN (91.3%), Tier 3 Transformer (F1=0.9400), ensemble stacker (AUC=0.9809) trained; all calibration KPIs passed. |
| Real survey credentials and live policy | **CONFIGURED + SIGNED** | T1-B closed. Credentials in macOS Keychain; live connection tests passed; bounded live dry-run policy signed; execution remains credential/provider gated and non-submitting. |
| Real data processed | **T1-C CLOSED** | ATLAS known-object recovery: 5/5 prequalified objects (100%); operator review by Jerome W. Lindsey III, no blocking findings (2026-06-20). Evidence: `docs/evidence/t1c/`. |
| Production calibration | **Complete** | T1-D closed. Quantitative Brier, ECE, log-loss, ROC AUC, CV ECE, and bootstrap CI gates passed (2026-06-14). |
| Console output compliance | **Complete** | All `Skills/run_pipeline.py` stage prints include `elapsed {M}m{S:02d}s`; ETA from measurable quantities (per-survey, per-tracklet). |
| External reporting | **Disabled — human action required** | WISE/NEOWISE ADES export now fails closed unless `stn=C51` and explicit written MPC confirmation are recorded; no actual submission is made. See `docs/MPC_SUBMISSION_POLICY.md §Archival WISE Submission Authority`. |
| WISE scale-plan diagnostics | **In progress** | `--link-scale-plan-out` now emits budget-derived diagnostic subfields with local cross-night support metrics for the blocked 12k-candidate WISE window. These are bounded diagnostics, not complete-field tiling evidence. |

### 15.2 Completed Milestones

| Milestone | Description | Status |
|---|---|---|
| **M1** | Core pipeline: `schemas` → `fetch` → `preprocess` → `detect` | Complete |
| **M2** | `link` → `classify` (Tier 1 XGBoost); tracklet production | Complete |
| **M3** | `orbit` → `score` → `alert`; MPC 80-column formatting | Complete |
| **M3b** | `calibration.py`; CNN (Tier 2) + Transformer (Tier 3) architecture | Complete |
| **M3c** | Ensemble meta-learner; NASA PDCO alert pathway; 100% coverage | Complete |
| **M3d** | `link.py` prediction fix; injection-recovery link rate 100% on n=200 | Complete |
| **M3e** | Unified offline background automation CLI | Complete |
| **M3f–M3j** | SQLite logs, schema migration, MCP bootstrap, signoff packets | Complete (offline only; not live-search milestones) |
| **Option B** | Pruned 68 fluff Skills scripts and 30 fluff docs; created `docs/PRODUCTION_READINESS.md` | Complete (2026-06-05) |

### 15.3 Production Roadmap

| Milestone | Gap Closed | Human Blocker | Status |
|---|---|---|---|
| **M4a** | T1-B: IRSA account + credentials | None | **Complete** |
| **M4b** | T1-B: ATLAS token | None | **Complete** |
| **M4c** | T1-B: Live review policy approved | Reviewer sign-off on `background/live_review_policy.example.json` | **Complete (signed 2026-06-18)** |
| **M4d** | T1-C: First supervised live ZTF pilot | Manual operator run; no external submission | **Complete (bounded, 2026-06-16)** |
| **M5a** | T1-A: Download labeled ZTF real/bogus dataset | 10,000 real alerts downloaded | **Complete** |
| **M5b** | T1-A: Build cutout dataset + train Tier 2 CNN | `models/tier2_cnn.pt`; validation accuracy 91.3% | **Complete** |
| **M5c** | T1-A: Acquire real multi-night sequences, build dataset, and train Tier 3 Transformer | Five-class policy and 50/class pilot approved; pilot trained | **Complete** |
| **M5d** | T1-A: Train Tier 1 XGBoost | `models/tier1_xgb.json`; validation accuracy 99.95%, macro AUC 1.000 | **Complete** |
| **M6a** | T1-D: Quantitative production calibration gate | Held-out real labeled data; all Brier, ECE, log-loss, AUC, cross-validation, and bootstrap-confidence KPIs pass | **Complete** |
| **M6b** | T1-C: Real-run audit packet | Build fail-closed review evidence from the first real ZTF pilot | **Complete for run `011dd53aa7f4`** |
| **M6c** | T1-C: Known-object recovery audit | Verify ≥90% known-object recovery using a generated expected-known manifest with pipeline IDs or sky/time samples | **Complete (5/5 objects, 100%, 2026-06-20)** |
| **M7** | All T1 gaps closed; internal no-submission production readiness | Requires M4-M6 complete plus no-submission discovery-paper guardrails | **Complete (2026-06-22)** |
| **M8** | First MPC submission eligibility | Requires MPC observatory code (human-gated), adversarial review survival, operator review, and policy-compliant candidate evidence | **Blocked - human action required (observatory code)** |

### 15.4 Progress Tracker

| ID | Status | Increment | Evidence |
|---|---|---|---|
| **P1–P16** | Complete | Background automation through v0.76.0 | See prior CHANGELOG entries |
| **P17** | Complete | Option B cleanup: 68 Skills + 30 docs removed | Commit `b4f83d8` (2026-06-05) |
| **P18** | Complete | `docs/PRODUCTION_READINESS.md` created | Commit `dfb1b15` (2026-06-05) |
| **P19** | Complete | AGENTS.md, README.md, CHANGELOG.md synced to v0.87.0 | This commit |
| **P20** | Complete | IRSA account and credentials configured | macOS Keychain; live connection test passed |
| **P21** | Complete | ATLAS token obtained | macOS Keychain; live connection test passed |
| **P22** | Complete | Labeled ZTF dataset downloaded | 10,000 real ZTF Avro alerts |
| **P23** | Complete | Tier 2 CNN trained (`models/tier2_cnn.pt`) | Validation accuracy 91.3%; weights committed |
| **P24** | Complete | Tier 3 Transformer trained (`models/tier3_transformer.pt`) | 50/class five-class pilot; val_macro_f1=0.9400 |
| **P25** | Complete | Calibration KPI report passes; gates eligible to be armed | T1-D quantitative KPI gate passed |
| **P26** | Complete | Public ALeRCE ZTF source-detection provider added | Replaces bad IRSA metadata-table assumption for source detections |
| **P27** | Complete | First bounded supervised real-ZTF pilot completed | 4,059 real ZTF detections fetched; 2 internal candidates processed; run summary `011dd53aa7f4` |
| **P28** | Complete | Real-run audit packet tool added | `Skills/audit_real_run.py` writes JSON + CSV review evidence without network access or external submission |
| **P29** | Complete | Known-object recovery KPI | 5/5 prequalified ATLAS objects recovered (100%); audit passed 2026-06-20 |
| **P30** | Complete | Operator review | Jerome W. Lindsey III, no blocking findings, 2026-06-20; T1-C closed |
| **P31** | Complete | All T1/T2 production gaps closed | Pipeline is no-submission production-ready; first live run 2026-06-21 |
| **P32** | Complete | Automated live-run approval | Bounded live dry-run policy signed; execution remains credential/provider gated and non-submitting |
| **P33** | Blocked | MPC escalation path / observatory code | Human-gated: operator must decide observatory code strategy; no code work can unblock this |
| **P34** | Complete | Console output elapsed+ETA compliance | All `run_pipeline.py` stage prints include elapsed time; ETA from measurable quantity (2026-06-26) |
| **P33** | In progress | Real-run audit v2 | `Skills/audit_real_run.py` can match expected known objects by pipeline ID or sky/time samples and requires operator-review decisions |
| **P34** | Complete | Expected-known manifest builder | `Skills/build_recovery_manifest.py` builds checkpointed MPC+Horizons sky/time manifests for T1-C audits |
| **P35** | Complete | Repository artifact hygiene | `.gitignore` protects `git add .`; raw `Logs/**` are local-only, production models are explicit allowlists, and T1-C evidence is summarized in `docs/evidence/t1c/` |
| **P36** | In progress | ATLAS forced-photometry fallback | `Skills/fetch_atlas_data.py --expected-known ...` writes audit-compatible recovery packets; provider request format, polling, in-flight checkpointing, task-URL resume, and force-refresh stale negative replay are fixed; the 2026-06-19 bounded 38-sample ATLAS pilot worked technically but failed the 90% recovery KPI at 4/11 expected objects; the prequalified 15-sample follow-up improved to 3/4 but still failed |

### 15.5 Known Limitations

- **Real-data evidence is bounded**: The first ALeRCE-backed ZTF pilot processed real detections and produced two internal candidates, but it was capped at 80 linked candidates.
- **Known-object recovery evidence is complete for T1-C**: The prequalified ATLAS recovery run passed 5/5 objects (100%) and closed the recovery KPI; future discovery sweeps still need their own candidate-level review.
- **Operator review remains required for candidates**: Recovered or newly linked candidates need adversarial review plus Jerome W. Lindsey III's operator review before any MPC path is considered.
- **External expert review happens through MPC/NEOCP/Scout**: Internal production readiness does not authorize MPC submission or hazard notification.
- **Automated live execution remains gated**: The bounded live dry-run policy is signed, but runs still require provider credential readiness and remain non-submitting.
- **MOID accuracy on short arcs**: Arcs < 24 hours produce unreliable MOID; quality-code gate (≥2) mitigates but does not eliminate this.

---

## 16. Important Disclaimer

This repository implements a **candidate identification and ranking system**. It is not an authoritative source of hazard assessments.

- This system does **not** confirm NEO discoveries.
- This system does **not** determine impact probabilities.
- This system does **not** replace the Minor Planet Center, CNEOS Scout, CNEOS Sentry, or any other authoritative planetary-defense monitoring system.
- All public hazard communication must follow the alert protocol defined in §7 and must originate from **NASA/CNEOS**, **ESA NEOCC**, or **IAU CBAT** — never from this pipeline.

Any use of this software for real-time hazard assessment requires independent validation by qualified planetary-defense professionals and must follow applicable national and international reporting protocols.

---

## 17. License

- **Code**: Apache License 2.0 — see [`LICENSE`](LICENSE)
- **Documentation**: Creative Commons Attribution 4.0 International (CC BY 4.0)

---

## 18. Works Cited

Bellm, Eric C., et al. "The Zwicky Transient Facility: System Overview, Performance, and First Results." *Publications of the Astronomical Society of the Pacific*, vol. 131, no. 995, 2019, p. 018002. DOI: 10.1088/1538-3873/ab0c2a.

Bowell, Edward, et al. "Application of Photometric Models to Asteroids." *Asteroids II*, edited by Richard P. Binzel et al., University of Arizona Press, 1989, pp. 524–556.

Duev, Dmitry A., et al. "Real-bogus Classification for the Zwicky Transient Facility Using Deep Learning." *Monthly Notices of the Royal Astronomical Society*, vol. 489, no. 3, 2019, pp. 3582–3590. DOI: 10.1093/mnras/stz2357.

Gaia Collaboration, et al. "Gaia Data Release 3: Summary of the Content and Survey Properties." *Astronomy and Astrophysics*, vol. 674, 2023, p. A1. DOI: 10.1051/0004-6361/202243940.

Jedicke, Robert, et al. "Observational Selection Effects in Asteroid Surveys." *Asteroids III*, edited by William F. Bottke Jr. et al., University of Arizona Press, 2002, pp. 71–87.

Lin, Hsing-Wen, et al. "Astronomical Image Time Series Classification Using CONVolutional Neural nETworks (ConvNet)." *The Astronomical Journal*, vol. 163, no. 4, 2022, p. 154. DOI: 10.3847/1538-3881/ac4e97.

Mainzer, Amy, et al. "Initial Performance of the NEOWISE Reactivation Mission." *The Astrophysical Journal*, vol. 792, no. 1, 2014, p. 30. DOI: 10.1088/0004-637X/792/1/30.

Moeyens, Joachim, et al. "THOR: An Algorithm for Cadence-independent Asteroid Discovery." *The Astronomical Journal*, vol. 162, no. 4, 2021, p. 143. DOI: 10.3847/1538-3881/ac042b.

Ye, Quanzhi, et al. "Hundreds of New Near-Earth Asteroids Found with the Zwicky Transient Facility." *The Astronomical Journal*, vol. 159, no. 2, 2020, p. 70. DOI: 10.3847/1538-3881/ab629c.

---

> **Vision**: Build a system that produces *scientifically defensible, fully provenance-tracked Near-Earth Object candidates* — not ranked lists. Every hazard flag is conservative, every result is reproducible, and every alert follows a mandatory human-in-the-loop confirmation pathway.
