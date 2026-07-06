# Astrometrics Coding Agents Master Guide

Date: 2026-07-05

Purpose: This file is an implementation guide for coding agents working on the three Astrometrics projects:

- `2026 Technosignatures`
- `2026 Exoplanet Research`
- `2026 Near Earth Objects`

The coding agent should read this file before modifying any model, dataset, scoring, evaluation, candidate-ranking, or detection-pipeline code.

## What The Agent Should Do With This File

1. Copy this file into each repo as `docs/ASTROMETRICS_DETECTION_AGENT_GUIDE.md`, or keep it in a shared Astrometrics docs folder and link to it from each repo README.
2. Treat this as the external research authority for the detection-pipeline evolution plan.
3. Do not redo broad literature research unless explicitly asked.
4. Do not collapse this guide into one model choice. The project intentionally preserves multiple ranked options.
5. Implement from Phase 1 forward unless the user explicitly chooses a later experiment.
6. When adding a feature, reference the relevant section and citation in PR notes, model cards, or dataset cards.
7. If a repo already has equivalent functionality, do not duplicate it. Map the existing implementation to the section below and improve gaps.

## Non-Negotiable Decisions

These decisions are already made for coding agents:

1. Keep the CNN, but freeze it as `benchmark_cnn_v1`.
2. Do not make the CNN the main scientific thesis.
3. Do not train or evaluate using random splits only.
4. Do not treat unlabeled data as negative data.
5. Do not promote any model without injection-recovery results.
6. Do not use accuracy as the primary metric for rare-event discovery.
7. Do not use synthetic-only performance as evidence of real-world performance.
8. Do not allow LLMs to make final detection decisions.
9. Do not accept a candidate without manifest and ledger provenance.
10. Do not change scientific thresholds, labels, or splits without an audit trail.
11. Treat a 4TB external SSD as the normal local Astrometrics workspace when available.
12. Do not mirror public raw archives locally. Public raw TESS, Kepler, JWST, Breakthrough Listen, and survey-image data is disposable cache unless promoted by policy.
13. Cloud/object storage is optional infrastructure for overflow, durability, collaboration, and cloud compute. It is not required for day-one local work.
14. A working SSD is not a backup. Back up manifests, ledgers, configs, reports, candidate evidence, and frozen eval/calibration artifacts separately.

## Local Storage Stance

The expected local setup is:

```text
laptop internal drive = code, environment, and small active files
4TB external SSD = primary Astrometrics workspace and local data cache
public archives = source of truth for re-downloadable raw data
cloud/object storage = optional overflow and durable artifact store
separate backup = recovery for irreplaceable project state
```

Agents should assume the external SSD can comfortably hold active batches for all three repos if they follow the data-selection policy:

1. Store metadata, manifests, target queues, ledgers, labels, configs, reports, derived features, embeddings, frozen eval/calibration sets, and candidate evidence.
2. Keep raw public archive files only for the active batch unless the data is candidate evidence, frozen eval, calibration, expensive to reconstruct, or user-approved offline working data.
3. Prefer archive URIs, product IDs, checksums, query manifests, and regeneration commands over permanent raw-data copies.
4. Keep at least 500GB free on the 4TB external SSD for downloads, temp files, retries, and failed runs.
5. Do not let automated agents use available disk space as permission to broaden a search. Target queues still govern what gets pulled.

## Final Target Architecture

All three repos should converge toward this shared pipeline shape:

```text
raw data
-> dataset manifest and provenance
-> classical candidate generator
-> frozen CNN benchmark score
-> self-supervised embedding
-> tabular/candidate feature scorer
-> anomaly / OOD / PU ranking
-> conformal or empirical calibration
-> injection-recovery sensitivity context
-> candidate report
-> human review ledger
-> retraining queue
```

The research thesis is:

> Calibrated astrophysical discovery pipelines using classical search, self-supervised embeddings, injection-recovery validation, and human-review feedback, with CNNs retained as reproducible internal benchmarks.

## Shared Implementation Package

If the repos share code, create a shared package named:

```text
astrometrics_ml_hardening/
  manifests/
    dataset_manifest.schema.json
    validate_manifest.py
  ledgers/
    candidate_schema.py
    write_candidate.py
    query_candidates.py
  splits/
    grouped_splits.py
    leakage_checks.py
  benchmarks/
    benchmark_cnn_v1/
  injections/
    base.py
    exoplanet_transits.py
    radio_narrowband.py
    neo_moving_sources.py
  embeddings/
    lightcurve_encoder.py
    spectrogram_encoder.py
    image_chip_encoder.py
  scoring/
    tabular_baselines.py
    anomaly_scores.py
    pu_learning.py
  calibration/
    score_quantiles.py
    conformal.py
    calibration_report.py
  review/
    review_schema.py
    review_batch_selection.py
  reports/
    candidate_report.py
    model_card.py
    dataset_card.py
  evals/
    canonical_cases.yaml
    run_evals.py
    regression_report.py
```

If shared code is not practical, implement the same folder names inside each repo.

## Phase 1: Make Results Reproducible

Build this first in all three repos.

### 1. Dataset Manifest System

Likelihood of success: Very high.

Agent task:
- Add a JSON schema for datasets.
- Require every training, scoring, and evaluation run to cite manifest IDs.
- Add validation tests.

Minimum manifest fields:

```yaml
dataset_id:
project:
source_name:
source_url:
instrument:
target_ids:
time_range:
cadence:
band_or_frequency:
data_product_type:
downloaded_at:
local_path:
checksum:
license:
label_source:
label_confidence:
preprocessing_version:
known_caveats:
```

Do not proceed to model work until this exists.

### 2. Candidate Ledger

Likelihood of success: Very high.

Agent task:
- Create a parquet or SQLite candidate ledger.
- Every candidate should be reproducible from the ledger.

Minimum candidate fields:

```yaml
candidate_id:
project:
source_dataset_id:
target_id:
time_window:
raw_uri:
preprocess_version:
candidate_generator:
candidate_generator_params:
model_versions:
model_scores:
calibrated_scores:
score_quantiles:
injection_context:
nearest_known_artifacts:
review_status:
review_notes:
regeneration_command:
created_at:
```

### 3. Freeze CNN Benchmark

Likelihood of success: Very high.

Agent task:
- Move or wrap the current CNN into `benchmark_cnn_v1`.
- Freeze architecture, preprocessing, random seeds, split definitions, and metrics.
- Add a model card.

Expected output:

```text
benchmarks/benchmark_cnn_v1/
  model.py
  preprocess.py
  train.py
  score.py
  MODEL_CARD.md
  locked_config.yaml
```

Do not keep casually tuning this model. It is now the measuring stick.

### 4. Grouped Splits And Leakage Checks

Likelihood of success: Very high.

Agent task:
- Replace random-only train/test splits with grouped splits.
- Keep random split only as a diagnostic.

Required split strategies:

| Repo | Required grouped holdout |
|---|---|
| Technosignatures | by target, cadence, frequency band, telescope/session |
| Exoplanets | by star, Kepler quarter, TESS sector, source catalog |
| NEOs | by night, sky region, survey/instrument, object ID |

### 5. OpenAI-Evals-Style Regression Suite

Likelihood of success: Very high.

Agent task:
- Add canonical examples and regression tests.
- Each pipeline change should produce sample-by-sample comparisons.

Minimum eval cases:
- known BL RFI examples
- injected radio narrowband controls
- confirmed exoplanets
- known exoplanet false positives
- injected transit controls
- known NEO detections
- false NEO link examples

Source rationale: OpenAI Evals emphasizes sample-level model evaluation and regression tracking. See OpenAI, "GPT-4."

## Phase 2: Make Sensitivity Measurable

### 6. Injection-Recovery Harness

Likelihood of success: Very high.

Agent task:
- Build parameterized injections into real backgrounds.
- Produce recovery curves, not just scalar metrics.

Project-specific injection parameters:

| Repo | Injection type | Parameters |
|---|---|---|
| Technosignatures | drifting narrowband signal | SNR, drift rate, bandwidth, intermittency, cadence pattern, RFI proximity |
| Exoplanets | transit signal | depth, duration, period, TTVs, single transit, gaps, stellar variability |
| NEOs | moving source | magnitude, velocity, trail length, seeing, sky background, missed frames |

Expected outputs:

```text
injection_recovery/
  configs/
  inject.py
  recover.py
  recovery_curves.py
  reports/
```

Validation rule:
- A model cannot be promoted unless it has injection-recovery curves.

### 7. Calibration Reports

Likelihood of success: High.

Agent task:
- Convert raw scores into score quantiles or calibrated p-value-like outputs.
- Do not invent a threshold.

Minimum outputs:

```yaml
raw_score:
calibrated_score:
score_quantile:
calibration_dataset_id:
threshold_version:
false_discovery_estimate:
```

Source rationale: Conformal and OOD work supports conservative score interpretation under finite samples. See Novello, Dalmau, and Andeol.

## Phase 3: Add Frontier Representations

### 8. Exoplanet Light-Curve Embeddings

Likelihood of success: High.

Agent task:
- Add a self-supervised light-curve embedding pipeline.
- Compare against CNN and BLS/TLS feature baselines.

Models to benchmark:
- FALCO-style self-supervised transformer.
- ASTROMER-style light-curve embeddings.
- AstroCo-style conformer embeddings.
- Google TimesFM-style time-series foundation model baseline.

Required data:
- unlabeled Kepler/TESS light curves
- confirmed planets
- false positives
- stellar variability labels
- injection-recovery sets

Validation:
- Must improve grouped holdout, top-k review yield, or injection recovery.

### 9. Technosignature Radio Embeddings

Likelihood of success: High.

Agent task:
- Add masked spectrogram / waterfall representation learning.
- Build a nearest-neighbor index of BL/RFI examples.

Training objectives to try:
- masked spectrogram reconstruction
- contrastive cadence learning
- same-target/different-cadence discrimination
- RFI-family clustering

Validation:
- Must improve RFI rejection or top-k candidate triage over current `semisupervised_anomaly_score`.

### 10. RFI Atlas

Likelihood of success: High.

Agent task:
- Build an RFI family atlas.
- Every technosignature candidate report should show nearest known RFI neighbors.

Minimum fields:

```yaml
rfi_family_id:
description:
frequency_range:
morphology:
cadence_behavior:
known_sources:
example_candidate_ids:
embedding_centroid:
veto_rules:
```

### 11. NEO Tracklet / Orbit-Linking Core

Likelihood of success: High.

Agent task:
- Center NEO discovery around tracklet/orbit linking.
- CNNs should classify image chips/artifacts, not serve as the whole detector.

Methods to implement or wrap:
- THOR-style cadence-independent linking.
- HelioLinC3D/HOPS-style processing.
- nonlinear digital tracking where compute allows.

Validation:
- Report completeness and purity over known objects and injected objects.

### 12. Tabular Candidate Scoring

Likelihood of success: High.

Agent task:
- Build candidate-level tabular scorers for all repos.
- Start with XGBoost/LightGBM/CatBoost.
- Then benchmark TabNet, TabFM, TabPFN, or TabICL-style models.

Useful features:
- raw detector scores
- CNN score
- embedding distance to known artifacts
- host-star metadata
- cadence metadata
- astrometric residuals
- injection sensitivity context
- human review labels

Validation:
- Must beat simple boosted trees or add useful interpretability/calibration.

## Phase 4: Add Advanced Experiments

These are not first-week tasks. Implement after Phases 1-3.

### 13. Raw / Unfolded TESS Transformer

Likelihood of success: Medium-high.

Goal:
- Detect transits without relying solely on phase folding.

Reason:
- Phase folding can erase single-transit and anomalous per-transit behavior.

### 14. Individual Anomalous Transit Detector

Likelihood of success: Medium-high.

Goal:
- Search individual transits for anomalous timing, depth, asymmetry, missing events, or extra events.

Use:
- exoplanet science
- optical technosignature-adjacent anomaly search

### 15. Positive-Unlabeled Learning

Likelihood of success: Medium-high.

Goal:
- Train when positives or artifacts are known but unlabeled data may be contaminated.

Use cases:
- known RFI vs unreviewed BL hits
- confirmed/injected exoplanets vs unlabeled light curves
- reviewed artifacts plus unreviewed candidates

Do not assume unlabeled equals negative.

### 16. Human Review Feedback Loop

Likelihood of success: Medium-high.

Agent task:
- Treat human review as structured training data.
- Add active-learning batch selection.

Review labels:
- artifact
- known RFI family
- likely false positive
- plausible but weak
- follow-up worthy
- preprocessing failure
- duplicate
- injected control

### 17. NEO Graph / Trajectory Model

Likelihood of success: Medium.

Goal:
- Represent detections as graph nodes and physical compatibility as edges.
- Train a model to score candidate trajectories or links.

### 18. JWST / Spectra Retrieval Surrogates

Likelihood of success: Medium.

Goal:
- Treat JWST spectra as characterization, not first-pass detection.
- Use neural posterior estimation or transformer-derived informative priors to accelerate Bayesian retrieval.

Validation:
- Must remain consistent with classical retrieval within posterior/evidence checks.

## Phase 5: Later / Speculative

Do not prioritize these until earlier phases are healthy.

| Idea | Likelihood | Rule |
|---|---|---|
| Multimodal CLIP-style astronomy embeddings | Medium | Useful after each modality has stable manifests and embeddings. |
| Generic time-series foundation models | Medium | Benchmark, do not assume they beat domain-specific models. |
| Diffusion/consistency synthetic data | Low-medium | Never use generated data as discovery evidence. |
| LLM candidate report assistant | Low-medium | It may critique reports, but cannot decide detections. |
| Fully neural end-to-end detector | Low | Experimental only; must pass injection-recovery and grouped holdouts. |

## Data Selection Rules: Training Data vs Live Search Data

This section is mandatory for coding agents. Training data and live search data serve different purposes and must be selected by different rules.

Training data hardens the model stack. Live search data maximizes the chance of producing material scientific contributions.

Do not mix these decision criteria.

### Core Distinction

| Data type | Main purpose | Selection logic | Success metric |
|---|---|---|---|
| Training data | Make models robust, calibrated, and honest about uncertainty | Diversity, labels, failure modes, distribution coverage, hard negatives | Better grouped holdout, calibration, injection recovery, artifact rejection |
| Live search data | Find candidates worth publishing, following up, or contributing to catalogs | Scientific value, novelty, observability, target priority, follow-up leverage | New candidates, validated null results, recoveries, follow-up-ready reports |

### Rules For Training Data

Training data should not be chosen because it is exciting. It should be chosen because it improves the pipeline's ability to avoid fooling itself.

Agent tasks:

1. Prioritize labeled and reviewable data over merely large data.
2. Include boring negatives, common artifacts, edge cases, and historical failures.
3. Preserve source diversity across instruments, cadences, sky regions, and pipelines.
4. Include synthetic injections only with explicit synthetic provenance.
5. Maintain separate real-only and synthetic-inclusive evaluation sets.
6. Treat unlabeled data as unlabeled, not negative.
7. Use grouped splits that test transfer across mission, target, sector, cadence, or survey.
8. Record all training data in manifests.
9. Record all label sources and label confidence.
10. Keep a frozen canonical eval set that agents are not allowed to optimize directly.

### Training Data Selection Score

When deciding whether to add a training dataset, score it from 0-3 on each criterion.

| Criterion | What to reward |
|---|---|
| Label quality | confirmed labels, expert review, catalog provenance, clear false-positive class |
| Distribution coverage | new instrument, sector, cadence, sky region, frequency band, object class |
| Failure-mode value | artifacts, RFI, false positives, systematics, edge cases |
| Calibration value | useful for score thresholds, uncertainty checks, top-k review calibration |
| Injection compatibility | supports realistic injections into real backgrounds |
| Reproducibility | stable source, documented API, checksums, clear license |
| Leakage safety | can be split by target/time/source without contamination |
| Cost practicality | feasible storage, compute, and download process |

Training data priority:

```text
training_priority =
  label_quality
  + distribution_coverage
  + failure_mode_value
  + calibration_value
  + injection_compatibility
  + reproducibility
  + leakage_safety
  + cost_practicality
```

Default rule:
- Add datasets scoring 18 or higher.
- Queue datasets scoring 14-17 for targeted use.
- Do not add datasets below 14 unless the user approves a specific reason.

### Rules For Live Search Data

Live search data should be chosen to maximize material scientific contribution, not just model confidence.

Agent tasks:

1. Balance new target searches with follow-on searches.
2. Prefer targets where a positive, negative, or null result would be scientifically useful.
3. Prefer targets where follow-up is feasible.
4. Prefer data products with clean provenance and enough context for publication-quality reporting.
5. Avoid repeatedly searching easy, over-mined data unless the method is materially better.
6. Keep "high-priority null results" as valid outputs when they constrain parameter space.
7. Always separate live search candidates from training and calibration data.

### Live Search Data Selection Score

Score live search targets or datasets from 0-3 on each criterion.

| Criterion | What to reward |
|---|---|
| Scientific novelty | undersearched targets, new parameter space, new cadence/frequency/magnitude regime |
| Prior significance | known high-interest object, TOI/KOI/NEO risk, nearby star, unusual system |
| Follow-up leverage | observable again, cross-instrument confirmation possible, community interest |
| Data quality | sufficient SNR/depth/cadence/metadata for credible candidate reports |
| Method advantage | your pipeline can add something previous searches likely missed |
| Publication value | result would support a note, catalog contribution, null constraint, or follow-up request |
| Community integration | compatible with MPC, ExoFOP, MAST, BL archive, NASA Exoplanet Archive, or other community systems |
| New/follow-up balance | supports either a new target campaign or a planned follow-up slot |

Live search priority:

```text
live_search_priority =
  scientific_novelty
  + prior_significance
  + followup_leverage
  + data_quality
  + method_advantage
  + publication_value
  + community_integration
  + new_followup_balance
```

Default rule:
- Search datasets or targets scoring 18 or higher.
- Search 14-17 only if they fill a portfolio gap.
- Avoid below 14 unless needed for controls or method validation.

### New Search vs Follow-On Search Balance

Default portfolio:

| Search category | Target share | Purpose |
|---|---:|---|
| New targets / new data regions | 60% | maximize discovery and novelty |
| Follow-on / reanalysis targets | 30% | confirm, refine, or challenge prior candidates |
| Controls / calibration live runs | 10% | keep the live pipeline honest |

Agents may adjust this only with an explicit decision log entry.

Adjustment rules:
- Increase follow-on to 50% if there are unresolved high-value candidates.
- Increase new search to 75% if the candidate queue is stale or already reviewed.
- Increase controls to 20% after major pipeline changes.

### Preventing Data Contamination

Agents must maintain separate data roles:

| Role | Can train on it? | Can tune thresholds on it? | Can report discoveries from it? |
|---|---|---|---|
| Training | yes | no | no |
| Validation | indirect model selection only | no | no |
| Calibration | no | yes | no |
| Frozen eval | no | no | no |
| Live search | no | no | yes |
| Follow-up live search | no | no | yes |

If live search data is later used for training, it must be demoted into a future training manifest and excluded from future claims of blind discovery.

### Technosignatures Data Selection

Training data should prioritize:
- real BL/SETI hit tables with known RFI or review labels
- MeerKAT BLUSE hit rows already used by `semisupervised_anomaly_score`
- BL GBT/Parkes/Murriyang examples with cadence metadata
- known RFI families and common false positives
- injected drifting narrowband signals in real backgrounds
- off-target/on-target cadence failures

Live search data should prioritize:
- nearby stars with exoplanets or high astrobiological interest
- TESS/Kepler targets with relevant exoplanet geometry
- undersearched frequency bands or cadence patterns
- targets with previous interesting but unconfirmed BL-like events
- high-value null-result target classes
- datasets where the pipeline searches a parameter space previous work did not cover

New/follow-up balance:
- 60% new targets or new parameter-space searches
- 30% follow-on of high-interest exoplanet/SETI targets or previous anomalies
- 10% controls, including known RFI-heavy sessions

Do not:
- train on a target and later claim a blind live search on the same target/session
- score a signal as interesting without nearest RFI-neighbor context
- report high anomaly score without calibration context

### Exoplanet Data Selection

Training data should prioritize:
- confirmed planets from Kepler/TESS
- certified false positives and eclipsing binaries
- stellar variability classes
- Kepler-to-TESS transfer sets
- TESS sector diversity
- injected transits in real light curves
- single-transit and long-period examples
- centroid/background examples where available

Live search data should prioritize:
- undersearched TESS FFIs or faint-star samples
- high-priority TOIs/KOIs needing independent vetting
- systems with habitable-zone potential
- nearby bright stars where follow-up is feasible
- multi-planet systems where additional planets are plausible
- single-transit events needing recovery or period constraints
- anomalous transit systems where per-transit behavior matters

New/follow-up balance:
- 55% new TESS/Kepler search regions or faint-star samples
- 35% follow-on TOIs/KOIs/single-transit systems
- 10% controls and known benchmark systems

Do not:
- optimize only on phase-folded curves
- mix confirmed/candidate labels without label-confidence fields
- use NASA Exoplanet Archive candidate status as a clean positive label without recording status

### Near Earth Object Data Selection

Training data should prioritize:
- known asteroid detections with astrometric metadata
- false detections and survey artifacts
- image chips with WCS and timing metadata
- tracklet/linking failures
- injected moving sources in real images
- multiple nights and sky regions
- object classes with different rates of motion

Live search data should prioritize:
- recent observations where reporting can still matter
- sky regions with NEO discovery potential
- under-processed archival data with sufficient metadata
- candidates with follow-up windows still open
- objects or tracklets needing recovery
- data that can produce MPC-compatible astrometry

New/follow-up balance:
- 60% new discovery-oriented search fields
- 30% recovery/follow-up of uncertain tracklets or objects needing orbit improvement
- 10% known-object controls and injection controls

Do not:
- treat image-chip classification as the whole NEO detector
- run live search without known-object crossmatch
- produce candidate reports without MPC-readiness fields

### Data Selection Artifacts To Add

Each repo should add:

```text
data_selection/
  training_data_policy.md
  live_search_policy.md
  data_role_registry.yaml
  target_priority_queue.csv
  followup_priority_queue.csv
  data_selection_decision_log.md
```

`data_role_registry.yaml` should include:

```yaml
dataset_id:
role: training | validation | calibration | frozen_eval | live_search | followup_live_search
project:
source:
allowed_uses:
forbidden_uses:
split_group_keys:
manifest_path:
notes:
```

`target_priority_queue.csv` should include:

```text
target_id,project,source,scientific_novelty,prior_significance,followup_leverage,data_quality,method_advantage,publication_value,community_integration,new_followup_balance,total_priority,status,notes
```

`followup_priority_queue.csv` should include:

```text
candidate_id,target_id,project,reason_for_followup,urgency,observability,needed_data,community_destination,total_priority,status,notes
```

### Agent Decision Rule

When choosing data, the coding agent must write:

```markdown
## Data Selection Decision

Date:
Repo:
Data:
Role:
Training priority score:
Live search priority score:
Why this data:
Why not alternatives:
Leakage risks:
Manifest:
Expected scientific or model-hardening value:
```

If the data is live search data, the agent must also state whether it is:

```text
new_target_search
followup_search
control_live_run
```

## Project-Specific Instructions

### Technosignatures Repo

Primary objective:
- Harden the BL/SETI hit-ranking pipeline and calibrate `semisupervised_anomaly_score`.

Build order:

1. BL dataset manifest.
2. Candidate ledger.
3. Freeze CNN benchmark if image/waterfall CNN exists.
4. Injection-recovery for drifting narrowband signals.
5. RFI atlas.
6. Score calibration for `semisupervised_anomaly_score`.
7. Masked spectrogram/waterfall embeddings.
8. Positive-unlabeled learning.
9. Human review loop.

Minimum candidate report:

```yaml
candidate_id:
target:
frequency:
drift_rate:
snr:
cadence_status:
turboSETI_or_detector_params:
semisupervised_anomaly_score:
calibrated_score_quantile:
nearest_rfi_neighbors:
injection_recovery_context:
waterfall_plot:
review_status:
```

External resources to organize:
- Breakthrough Listen archive access notes.
- BL hit table schemas.
- RFI labels and examples.
- Injection parameter configs.
- Literature PDFs/links from Works Cited.

### Exoplanet Repo

Primary objective:
- Build a hybrid transit discovery/vetting system, not a CNN-only classifier.

Build order:

1. Kepler/TESS/JWST manifest system.
2. BLS/TLS classical search wrapper.
3. Candidate ledger.
4. Freeze phase-folded CNN benchmark.
5. Transit injection-recovery.
6. Tabular vetting scorer using Gaia/candidate features.
7. Self-supervised light-curve embeddings.
8. Raw/unfolded TESS transformer.
9. Individual anomalous-transit detector.
10. JWST retrieval surrogate, only after detection pipeline is stable.

Minimum candidate report:

```yaml
candidate_id:
star_id:
mission:
sector_or_quarter:
period:
epoch:
duration:
depth:
BLS_or_TLS_score:
cnn_benchmark_score:
embedding_score:
tabular_vetting_score:
centroid_check:
odd_even_check:
gaia_context:
injection_recovery_context:
calibrated_score_quantile:
review_status:
```

External resources to organize:
- MAST pull scripts.
- NASA Exoplanet Archive crossmatch.
- ExoFOP-TESS crossmatch.
- Gaia metadata.
- Kepler/TESS false-positive catalogs.
- FALCO/ASTROMER/AstroCo links.

### Near Earth Objects Repo

Primary objective:
- Build a moving-object discovery pipeline centered on source extraction and tracklet/orbit linking.

Build order:

1. Observation manifest.
2. Source extraction and difference-imaging wrapper.
3. Candidate ledger.
4. Tracklet/orbit-linking core.
5. Injection-recovery for moving sources.
6. CNN image-chip/artifact benchmark.
7. Tabular/linkage scorer.
8. Graph trajectory association model.
9. Video transformer tracklet model.
10. Nonlinear digital tracking or HPC experiment.

Minimum candidate report:

```yaml
candidate_id:
observation_ids:
sky_region:
time_span:
detections:
tracklet_score:
orbit_fit:
astrometric_residuals:
known_object_crossmatch:
cnn_artifact_score:
tabular_linkage_score:
injection_recovery_context:
mpc_submission_readiness:
review_status:
```

External resources to organize:
- MPC formats.
- JPL/Horizons integration notes.
- survey image/WCS metadata.
- known object crossmatch data.
- THOR/HOPS/nonlinear digital tracking papers.

## External Resource Organization

Each repo should add:

```text
docs/research/
  README.md
  works_cited.md
  model_options.md
  data_sources.md
  agent_decision_log.md
```

`docs/research/README.md` should tell future agents:

```text
Start with ASTROMETRICS_DETECTION_AGENT_GUIDE.md.
Do not perform broad literature research unless the user asks.
When implementing a model, cite the relevant source from works_cited.md.
When making a decision, add it to agent_decision_log.md.
```

`agent_decision_log.md` should use:

```markdown
## YYYY-MM-DD Decision

Repo:
Decision:
Why:
Alternatives considered:
Citation:
Validation plan:
```

## Agent PR Checklist

Before a PR or commit, answer:

1. Did I preserve `benchmark_cnn_v1`?
2. Did I add or update a dataset manifest?
3. Did I write candidate outputs to the ledger?
4. Did I use grouped splits?
5. Did I run canonical evals?
6. Did I avoid treating unlabeled examples as negatives?
7. Did I include injection-recovery where relevant?
8. Did I report top-k yield, AUPRC, FDR, and calibration rather than only accuracy?
9. Did I cite the relevant research in MLA style?
10. Did I avoid allowing an LLM to make final scientific decisions?

## Missing Items / Suggestions For The User

The project is close to having a strong external research plan. The remaining missing pieces are mostly operational:

1. Decide whether the three repos should share one package, `astrometrics_ml_hardening`, or copy a common folder structure into each repo.
2. Decide where durable data manifests and candidate ledgers live: inside each repo, in a shared data repo, or in an external database.
3. Decide the first canonical eval set for each repo. This is the most important near-term scientific control.
4. Decide whether human review will be notebook-based first or whether a small local web UI is worth building.
5. Decide how large local training should be allowed to get on your Mac before moving GPU-heavy work elsewhere.
6. For technosignatures, define the review vocabulary for RFI/artifact families before training more models.
7. For exoplanets, decide whether the first serious benchmark is Kepler-only, TESS-only, or Kepler-to-TESS transfer.
8. For NEOs, decide the first survey/image source before implementing tracklet linking.

My strongest suggestion: implement Phase 1 and Phase 2 before any new frontier model. Those phases make every later experiment easier to trust.

## Works Cited

Aboulfotouh, Ahmed, Ashkan Eshaghbeigi, Dimitrios Karslidis, and Hatem Abou-Zeid. "Self-Supervised Radio Pre-training: Toward Foundational Models for Spectrogram Learning." arXiv, 14 Nov. 2024, https://arxiv.org/abs/2411.09849.

Aboulfotouh, Ahmed, Ashkan Eshaghbeigi, and Hatem Abou-Zeid. "Building 6G Radio Foundation Models with Transformer Architectures." arXiv, 15 Nov. 2024, https://arxiv.org/abs/2411.09996.

Anand, Ankit, et al. "Finding Increasingly Large Extremal Graphs with AlphaZero and Tabu Search." Google DeepMind, 6 Nov. 2023, https://deepmind.google/research/publications/44214/.

Anthropic. "Agentic Misalignment: How LLMs Could Be Insider Threats." Anthropic Research, 2025, https://www.anthropic.com/research/agentic-misalignment.

Anthropic. "Mapping the Mind of a Large Language Model." Anthropic Research, 21 May 2024, https://www.anthropic.com/research/mapping-mind-language-model.

Anthropic. "Open-Sourcing Circuit-Tracing Tools." Anthropic Research, 29 May 2025, https://www.anthropic.com/research/open-source-circuit-tracing.

Anthropic. "Towards Monosemanticity: Decomposing Language Models with Dictionary Learning." Anthropic Research, 5 Oct. 2023, https://www.anthropic.com/research/towards-monosemanticity-decomposing-language-models-with-dictionary-learning.

Arik, Sercan, and Tomas Pfister. "TabNet: Attentive Interpretable Tabular Learning." Google Research, 2021, https://research.google/pubs/tabnet-attentive-interpretable-tabular-learning/.

Burns, Collin, et al. "Weak-to-Strong Generalization." OpenAI, 14 Dec. 2023, https://openai.com/index/weak-to-strong-generalization/.

Cabrera-Vives, G., et al. "ATAT: Astronomical Transformer for Time Series and Tabular Data." arXiv, 5 May 2024, https://arxiv.org/abs/2405.03078.

Choi, Kukjin, Jihun Yi, Jisoo Mok, and Sungroh Yoon. "Self-Supervised Time-Series Anomaly Detection Using Learnable Data Augmentation." arXiv, 18 June 2024, https://arxiv.org/abs/2406.12260.

Dax, Maximilian, et al. "Flow Matching for Scalable Simulation-Based Inference." arXiv, 26 May 2023, https://arxiv.org/abs/2305.17161.

Deng, Ziquan, Xiwei Xuan, Kwan-Liu Ma, and Zhaodan Kong. "A Reliable Framework for Human-in-the-Loop Anomaly Detection in Time Series." arXiv, 6 May 2024, https://arxiv.org/abs/2405.03234.

Deka, Tonmoy, et al. "A Next-Generation Exoplanet Atmospheric Retrieval Framework for Transmission Spectroscopy (NEXOTRANS): Comparative Characterization for WASP-39 b Using JWST NIRISS, NIRSpec PRISM, and MIRI Observations." arXiv, 26 Apr. 2025, https://arxiv.org/abs/2504.18815.

Ding, Xueying, Nikita Seleznev, Senthil Kumar, C. Bayan Bruss, and Leman Akoglu. "From Explanation to Action: An End-to-End Human-in-the-Loop Framework for Anomaly Reasoning and Management." arXiv, 6 Apr. 2023, https://arxiv.org/abs/2304.03368.

Donoso-Oliva, C., et al. "ASTROMER: A Transformer-Based Embedding for the Representation of Light Curves." arXiv, 2 May 2022, https://arxiv.org/abs/2205.01677.

Geirhos, Robert, Roland S. Zimmermann, Blair Bilodeau, Wieland Brendel, and Been Kim. "Don't Trust Your Eyes: On the (Un)Reliability of Feature Visualizations." Google DeepMind, 7 June 2024, https://deepmind.google/research/publications/49869/.

Google Research. "A Decoder-Only Foundation Model for Time-Series Forecasting." Google Research Blog, 2 Feb. 2024, https://research.google/blog/a-decoder-only-foundation-model-for-time-series-forecasting/.

Google Research. "Calibration Properties of Time-Series Foundation Models: An Empirical Analysis." Google Research, 2025, https://research.google/pubs/calibration-properties-of-time-series-foundation-models-an-empirical-analysis/.

Google Research. "Introducing TabFM: A Zero-Shot Foundation Model for Tabular Data." Google Research Blog, 30 June 2026, https://research.google/blog/introducing-tabfm-a-zero-shot-foundation-model-for-tabular-data/.

Google Research. "Time Series Foundation Models Can Be Few-Shot Learners." Google Research Blog, 23 Sept. 2025, https://research.google/blog/time-series-foundation-models-can-be-few-shot-learners/.

Grinsztajn, Leo, et al. "TabPFN-2.5: Advancing the State of the Art in Tabular Foundation Models." arXiv, 11 Nov. 2025, https://arxiv.org/abs/2511.08667.

Hansen, Matthew T., and Jason A. Dittmann. "Single Transit Detection in Kepler with Machine Learning and Onboard Spacecraft Diagnostics." arXiv, 6 Mar. 2024, https://arxiv.org/abs/2403.03427.

Hudson, Drew A., et al. "SODA: Bottleneck Diffusion Models for Representation Learning." Google DeepMind, 29 Nov. 2023, https://deepmind.google/research/publications/44213/.

Kong, Weihao, and Abhimanyu Das. "Introducing TabFM: A Zero-Shot Foundation Model for Tabular Data." Google Research Blog, 30 June 2026, https://research.google/blog/introducing-tabfm-a-zero-shot-foundation-model-for-tabular-data/.

Lafarga, M., et al. "Automatic Search for Transiting Planets in TESS-SPOC FFIs with RAVEN: Over 100 Newly Validated Planets and Over 2000 Vetted Candidates." arXiv, 23 Mar. 2026, https://arxiv.org/abs/2603.22597.

Lam, Remi, et al. "GraphCast: Learned Global Weather Forecasting." Google DeepMind, 14 Nov. 2023, https://deepmind.google/research/publications/22598/.

Li, Weijian, et al. "StarEmbed: Benchmarking Time Series Foundation Models on Astronomical Observations of Variable Stars." arXiv, 7 Oct. 2025, https://arxiv.org/abs/2510.06200.

Moeyens, Joachim, et al. "THOR: An Algorithm for Cadence-Independent Asteroid Discovery." arXiv, 3 May 2021, https://arxiv.org/abs/2105.01056.

Muttenthaler, Lukas, et al. "Improving Neural Network Representations Using Human Similarity Judgments." Google DeepMind, 10 Dec. 2023, https://deepmind.google/research/publications/improving-neural-network-representations-using-human-similarity-judgments/.

Novello, Paul, Joseba Dalmau, and Leo Andeol. "Out-of-Distribution Detection Should Use Conformal Prediction (and Vice-Versa?)." arXiv, 18 Mar. 2024, https://arxiv.org/abs/2403.11532.

OpenAI. "CLIP: Connecting Text and Images." OpenAI, 5 Jan. 2021, https://openai.com/index/clip/.

OpenAI. "Consistency Models." OpenAI, 20 June 2024, https://openai.com/index/consistency-models/.

OpenAI. "Finding GPT-4's Mistakes with GPT-4." OpenAI, 27 June 2024, https://openai.com/index/finding-gpt4s-mistakes-with-gpt-4/.

OpenAI. "GPT-4." OpenAI, 14 Mar. 2023, https://openai.com/index/gpt-4-research/.

OpenAI. "Learning to Reason with LLMs." OpenAI, 12 Sept. 2024, https://openai.com/index/learning-to-reason-with-llms/.

OpenAI. "Summarizing Books with Human Feedback." OpenAI, 23 Sept. 2021, https://openai.com/index/summarizing-books/.

Pagliaro, L., T. Zingales, G. Piotto, I. Giovannini, and G. Mantovan. "Exoformer: Accelerating Bayesian Atmospheric Retrievals with Transformer Neural Networks." arXiv, 29 Mar. 2026, https://arxiv.org/abs/2603.27623.

Pardo, Snir, Dovi Poznanski, Steve Croft, Andrew P. V. Siemion, and Matthew Lebofsky. "Using Anomaly Detection to Search for Technosignatures in Breakthrough Listen Observations." arXiv, 6 May 2025, https://arxiv.org/abs/2505.03927.

Parker, Liam, et al. "AstroCLIP: A Cross-Modal Foundation Model for Galaxies." arXiv, 4 Oct. 2023, https://arxiv.org/abs/2310.03024.

Painter, Caleb, et al. "A Novel Technosignature Search in the Breakthrough Listen Green Bank Telescope Archive." arXiv, 8 Dec. 2024, https://arxiv.org/abs/2412.05786.

Price, Ilan, et al. "GenCast: Learning Skillful Ensemble Forecasting of Medium-Range Weather." Google DeepMind, 25 Dec. 2023, https://deepmind.google/research/publications/gencast-learning-skillful-ensemble-forecasting-of-medium-range-weather/.

Qu, Jingang, David Holzmueller, Gael Varoquaux, and Marine Le Morvan. "TabICL: A Tabular Foundation Model for In-Context Learning on Large Data." arXiv, 8 Feb. 2025, https://arxiv.org/abs/2502.05564.

Rizhko, Mariia, and Joshua S. Bloom. "AstroM3: A Self-Supervised Multimodal Model for Astronomy." arXiv, 13 Nov. 2024, https://arxiv.org/abs/2411.08842.

Roth, Joshua T., et al. "The T16 Planet Hunt: 10,000 New Planet Candidates from TESS Cycle 1 and the Confirmation of a Hot Jupiter Around TIC 183374187." arXiv, 20 Apr. 2026, https://arxiv.org/abs/2604.18579.

Ruhlmann, Pierre-Louis, Pedro L. C. Rodrigues, Michael Arbel, and Florence Forbes. "Flow Matching for Robust Simulation-Based Inference under Model Misspecification." arXiv, 27 Sept. 2025, https://arxiv.org/abs/2509.23385.

Salinas, Helem, et al. "Exoplanet Transit Candidate Identification in TESS Full-Frame Images via a Transformer-Based Algorithm." arXiv, 11 Feb. 2025, https://arxiv.org/abs/2502.07542.

Sanchez-Ferrera, Aitor, Borja Calvo, and Jose A. Lozano. "A Review on Self-Supervised Learning for Time Series Anomaly Detection: Recent Advances and Open Challenges." arXiv, 25 Jan. 2025, https://arxiv.org/abs/2501.15196.

Sanchez-Ferrera, Aitor, Usue Mori, Borja Calvo, and Jose A. Lozano. "NeuCoReClass AD: Redefining Self-Supervised Time Series Anomaly Detection." arXiv, 29 July 2025, https://arxiv.org/abs/2508.00909.

Tan, Antony, Pavlos Protopapas, Martina Cadiz-Leyton, Guillermo Cabrera-Vives, Cristobal Donoso-Oliva, and Ignacio Becker. "ASTROCO: Self-Supervised Conformer-Style Transformers for Light-Curve Embeddings." arXiv, 29 Sept. 2025, https://arxiv.org/abs/2509.24134.

Takahashi, Hiroshi, Tomoharu Iwata, Atsutoshi Kumagai, and Yuuki Yamanaka. "Deep Positive-Unlabeled Anomaly Detection for Contaminated Unlabeled Data." arXiv, 29 May 2024, https://arxiv.org/abs/2405.18929.

Vasist, Malavika, Francois Rozet, Olivier Absil, Paul Molliere, Evert Nasedkin, and Gilles Louppe. "Neural Posterior Estimation for Exoplanetary Atmospheric Retrieval." arXiv, 16 Jan. 2023, https://arxiv.org/abs/2301.06575.

Wang, Shao-Han, et al. "A Heliocentric-Orbiting Objects Processing System (HOPS) for the Wide Field Survey Telescope: Architecture, Processing Workflow, and Preliminary Results." arXiv, 29 Jan. 2025, https://arxiv.org/abs/2501.17472.

Wolfe, Sean, and M. Reza Emami. "Near-Earth Asteroid Detection Using Video Transformer Networks." Aerospace Science and Technology, vol. 165, Oct. 2025, article 110495, https://www.sciencedirect.com/science/article/pii/S1270963825005668.

Zuckerman, Anna, James Davenport, Steve Croft, Andrew Siemion, and Imke de Pater. "The Breakthrough Listen Search for Intelligent Life: Detection and Characterization of Anomalous Transits in Kepler Lightcurves." arXiv, 13 Dec. 2023, https://arxiv.org/abs/2312.07903.

Zuo, Xiaoxiong, et al. "FALCO: A Foundation Model of Astronomical Light Curves for Time Domain Astronomy." arXiv, 28 Apr. 2025, https://arxiv.org/abs/2504.20290.
