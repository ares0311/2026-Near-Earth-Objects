# Data Selection Decision Log

## 2026-07-08 — Adopt Astrometrics Data Selection Controls

Decision: Treat `docs/astrometrics_data_selection_policy.md`,
`docs/astrometrics_coding_agents_master_guide.md`, and
`docs/astrometrics_external_and_cloud_storage_policy.md` as mandatory
repository directives for future production work.

Rationale: Recent ZTF DR24 work closed all active production gates except
paused Gate Z3, but the new cross-project Astrometrics policies require
durable data-role separation, acquisition discipline, manifest planning, and
storage controls before more data selection or model-promotion work.

Scope:

- No new data was acquired.
- No scoring thresholds were changed.
- No MPC submission behavior was enabled.
- Gate Z3 candidate-pair searching remains paused to avoid a repeated
  low-yield loop unless the operator explicitly restarts that path.

Next data-selection action: define a scored, role-specific target queue before
any new production batch or live-search command is handed to the operator.

## 2026-07-11 — First genuinely new ZTF DR24 discovery-field selection

Date: 2026-07-11
Repo: 2026 Near Earth Objects
Data: Real UW ZTF public alert archive detections for 2 new nights
Role: live_search
Acquisition mode: batch (bounded, checkpointed, per-night)
Estimated download GB: <0.1 GB (per-night kept-observation counts in the
  existing manifest range from 0 to ~290 rows; `--max-per-night` safety cap
  is 5000)
Training priority score: N/A (not training data)
Live search priority score: 0.9238 (top-ranked field; see
  `data_selection/target_priority_queue.csv` rank 1 for this run)
Storage cost penalty: 0 (well under the <=5GB tier)
Why this data: All 14 nights already ingested (`Skills/ztf_alert_archive_ingest.py
  --status`) were selected to track one specific known designation (72966,
  Gate Z3's positive-control search) via targeted RA/Dec matching a real
  reference ephemeris -- none were chosen via the project's own undersearched-
  population selection algorithm. This is the first field selected via
  `Skills/select_survey_fields.py --mode aten` (quadrature/dawn-dusk,
  elongation 60-100 deg, ~85% undiscovered population) for a genuinely new
  discovery-oriented sweep, per `docs/astrometrics_data_selection_policy.md`'s
  "new_discovery_field" category (60% portfolio share) rather than
  "recovery_followup" (the Z3 designation-tracking work, 30% share).
Why not alternatives: Ranks 2-8 from the same run (see target queue) are
  reasonable alternates; rank 1 (RA 89.3, Dec 22.5) was chosen as the highest
  composite score (coverage gap 0.945, population density 0.821, geometry
  0.984, elongation 83.0 deg -- near-optimal quadrature).
Why this acquisition mode: Two real nights (20200914, 20200916, JD
  2459106.5-2459108.5), a calendar year (2020) not present in any prior
  ingest, well within ZTF's operational history and the archive's confirmed-
  reachable range. Two nights, 2 days apart, is the minimum needed for
  `link()`'s multi-night tracklet requirement; not sharded across terminal
  tabs -- two sequential per-night calls to one external service, too few
  independent units to benefit, and this session already holds the only
  active checkpoint/manifest lock.
Eviction or pin rule: Checkpoint retained under
  `Logs/pipeline_runs/ztf_alert_archive_ingest/` (gitignored, local); compact
  summary auto-committed to the shared manifest
  (`Logs/reports/ztf_alert_archive_ingest_manifest.jsonl`) per the shared-
  manifest standing rule.
Leakage risks: None -- this is real archived data selection, not a
  train/validation/test split.
Manifest: `Logs/reports/ztf_alert_archive_ingest_manifest.jsonl` (per-night
  entries); `data_selection/target_priority_queue.csv` rank 1 of this run's
  8-row batch.
Expected scientific or model-hardening value: First test of whether the
  fully-closed ZTF DR24 pipeline (Gates Z1,Z2,Z4-Z7) produces any surviving
  candidate on a field never targeted at a known object. Per
  `docs/ZTF_DR24_PRODUCTION_GATES.md`'s Production Definition, a null result
  (all tracklets rejected by adversarial review) is an expected, valid
  outcome and not evidence the pipeline is unready.
Citations: `docs/astrometrics_data_selection_policy.md` (NEO live-search
  scoring formula, new/follow-up portfolio balance);
  `docs/ZTF_DR24_PRODUCTION_GATES.md` (Production Definition, Stop
  Conditions).

new_target_search

## 2026-07-12 — tier2_cnn_v4 synthetic hard-negative training supplement

Date: 2026-07-12
Repo: 2026 Near Earth Objects
Data: 3,000 deterministic synthetic sub-pixel artifact triplets generated
  on demand by `SyntheticArtifactDataset`
Role: training
Acquisition mode: generated in memory; no download and no persisted payload
Estimated storage: negligible persistent storage (manifest only)
Why this data: `tier2_cnn_v3` was rejected after scoring 200/200 synthetic
  sub-pixel artifacts as false discoveries. The supplement directly targets
  that measured shape-discrimination failure while leaving validation and
  test data real-only.
Why not alternatives: Real bogus examples already contained comparable
  proportions of spike-like examples in v1 and v3 training data, so simply
  acquiring more of the same real distribution was not supported by the
  root-cause evidence. An architecture change was a larger intervention than
  the demonstrated failure required.
Generator parameters: n=3000, seed=0, sigma range 0.05-0.35 px, magnitude
  range 18-21, background range 2-40; every sample labeled
  `stellar_artifact`.
Leakage controls: Synthetic samples are appended to the training split only;
  the 18,000-row validation and 13,500-row test splits remain real-only.
Manifest: `data_selection/dataset_manifests/tier2_cnn_v4_synthetic_hard_negatives_v1.json`
Known limitation: The acceptance test uses the same artifact family, so its
  0/200 result demonstrates closure of the targeted failure mode but is not
  independent evidence of broad real-world artifact robustness. Real-data
  calibration remains the independent distribution check.
Citations: `docs/evidence/a7/2026-07-12-model-rejected-retune-required.md`;
  `docs/evidence/a7/2026-07-12-hard-negative-augmentation-implemented.md`;
  `docs/evidence/a7/2026-07-12-tier2_cnn_v4-real-retrain-and-acceptance-test.md`.

## 2026-07-12 — Second and third new-field selections (aten + ieo diversity)

Date: 2026-07-12
Repo: 2026 Near Earth Objects
Data: Real UW ZTF public alert archive detections for 2 new fields x 2 new
  nights each (4 nights total)
Role: live_search
Acquisition mode: batch (bounded, checkpointed, per-night, 4 concurrent
  processes)
Estimated download GB: <0.5 GB total (per-night kept-observation counts to
  date range 0-316 rows; `--max-per-night` safety cap is 5000 per night)
Live search priority score: 0.9189 (aten rank 2) and 0.9621 (ieo rank 1) --
  see `data_selection/target_priority_queue.csv` for this run's full
  8-row batches under each mode
Storage cost penalty: 0
Why this data: Continuing the new-field discovery-sweep portfolio after the
  first field (RA 89.3, Dec 22.5) returned a clean null result (see prior
  entry and `docs/evidence/live/2026-07-11-first-new-discovery-sweep.md`).
  Diversifying across both undersearched-population categories this project
  supports: `--mode aten` (quadrature/dawn-dusk, ~85% undiscovered) and
  `--mode ieo` (twilight Atira, ~97% undiscovered -- the highest-value
  category available). Picked aten rank 2 (RA 97.42, Dec 22.5) rather than
  rank 1, because rank 1 is the same field already searched -- confirmed
  `select_survey_fields.py --history-dir` does not recognize
  `Skills/ztf_alert_archive_ingest.py`'s checkpoint format as prior
  coverage (a real, minor tooling gap noted here but not yet fixed; the
  history mechanism was built for `run_pipeline.py`'s own run-directory
  layout). Manual rank selection substitutes for that gap in the interim.
Why not alternatives: Ranks 3-8 in each mode (see target queue) are
  reasonable alternates; picked top-available-novel score in each mode.
Why this acquisition mode: Two new fields x two nights each = 4 real
  archive nights (20230914/20230916, JD 2460201.5-2460203.5), a calendar
  year not present in any prior ingest. September dates chosen to preserve
  the same seasonal solar-elongation geometry the selection scores were
  computed for (JD 2459107.5, September 2020) rather than recomputing for
  a different time of year. Sharded across 4 concurrent background
  processes (one per night): the prior 2-night batch (2026-07-11) completed
  with zero errors, zero rate-limit responses, and (after initial slow
  throughput resolved itself) acceptable latency -- per the standing
  concurrency-escalation rule, this batch steps up by +2 (2 -> 4) rather
  than repeating the same concurrency level indefinitely.
Eviction or pin rule: Checkpoints retained under
  `Logs/pipeline_runs/ztf_alert_archive_ingest/` (gitignored, local);
  compact summaries auto-committed to the shared manifest.
Leakage risks: None -- real archived data selection, not a
  train/validation/test split.
Manifest: `Logs/reports/ztf_alert_archive_ingest_manifest.jsonl`;
  `data_selection/target_priority_queue.csv` (both mode batches from this
  run).
Expected scientific or model-hardening value: Builds toward a real search
  portfolio across the two population-bias categories this project's own
  selection algorithm supports, per
  `docs/astrometrics_coding_agents_master_guide.md`'s 60/30/10 new/
  follow-up/control balance. A null result on this batch (like the first)
  remains a valid, expected outcome per the Production Definition.
Citations: `docs/astrometrics_data_selection_policy.md`;
  `docs/ZTF_DR24_PRODUCTION_GATES.md`.

new_target_search

## 2026-07-14 — Six-shard ZTF DR24 60/30/10 portfolio search

Date: 2026-07-14
Repo: 2026 Near Earth Objects
Data: Real UW ZTF public alert archives for six bounded 2024 September nights,
  filtered in one streaming pass per night across nine sky fields; one
  post-ingest moving-source injection supplies the control allocation
Role: live_search
Acquisition mode: six disjoint archive-night shards launched by
  `Skills/run_sharded_download.py`; one worker per shard, for six aggregate UW
  streams. Raw nightly archives are never persisted.
Estimated transfer: 38.98 GB, based on verified HTTP Content-Length values in
  `data_selection/batch_manifests/ztf_dr24_portfolio_2024sep_v1.json`
Estimated persistent storage: at most 1.0 GB under the 5,000-observation
  per-field/night cap; current project data is approximately 10 GB, safely
  below the 100 GB ceiling.
Portfolio: six new ranked fields (three Aten and three IEO), three follow-up
  fields from the 2020/2023 sweeps, and one post-ingest injection control.
Why this data: It extends the bounded archival search across both prioritized
  undersearched populations while revisiting prior null/incomplete fields. A
  single multi-field pass avoids downloading the same multi-gigabyte nightly
  archive once per field.
Why this concurrency: The prior four-stream UW archive batch completed without
  rate limiting or service errors. Six streams is the standing policy's bounded
  +2 probe. Thirty-six simultaneous archive streams are not justified by the
  measured service ceiling, and each shard owns only one night, so additional
  inner workers would provide no work.
Checkpoint and retry plan: Atomic per-night checkpoints live under
  `Logs/pipeline_runs/ztf_alert_archive_portfolio/`; completed shards are
  resumable through the parent manifest. A failed night is restarted from its
  stream boundary without duplicating completed nights.
Leakage and review controls: Historical replay only, with a 2024-09-21 cutoff.
  Time-aware known-object exclusion is required before candidate review.
  Automated adversarial review and operator review remain mandatory; no MPC
  submission, external alert, or impact-probability claim is authorized.
Manifest: `data_selection/batch_manifests/ztf_dr24_portfolio_2024sep_v1.json`;
  shared execution state in `Logs/reports/sharded_download_manifest.jsonl`.
Expected value: A larger, diversity-balanced real-data search test of the
  production candidate pipeline. A clean null result remains scientifically
  valid and does not alter the research path.
Citations: `docs/astrometrics_data_selection_policy.md`;
  `docs/astrometrics_coding_agents_master_guide.md`;
  `docs/ZTF_DR24_PRODUCTION_GATES.md`.

new_target_search

## 2026-07-14 — Coverage-selected ZTF DR24 four-night portfolio

Date: 2026-07-14
Repo: 2026 Near Earth Objects
Data: Four UW ZTF public nightly alert archives selected from real IRSA
  science-image exposure metadata for the six new Aten/IEO fields
Role: live_search
Acquisition mode: stream/process/evict with four disjoint archive-night shards
  and one worker per shard; raw tar archives are never persisted
Estimated transfer: 26.670482707 GB from verified HTTP Content-Length values
Estimated persistent storage: at most 1.0 GB under the 5,000-observation
  per-field/night cap; project-managed data remains near 10 GB
Why this data: The first six-night portfolio guessed common September dates
  and left five of six new fields without repeat coverage. Metadata-only run
  `9a9e148f570d162b` queried a bounded 365-day interval for every new field;
  all six passed with 44-110 distinct exposure nights. An exhaustive
  four-night combination check then selected the lowest-transfer quartet that
  gives every new field at least three covered nights.
Selected nights: 20240321, 20240422, 20240504, 20240603. Each new field has
  central-box exposure coverage on exactly three of the four. The four remote
  archives total 26,670,482,707 bytes. A 74-byte 20240114 placeholder was
  explicitly rejected as unusable.
Why this concurrency: There are four independent nightly archives, so four
  shards x one worker is the complete useful parallel layout. Six shards would
  create two empty children; 6x6 would exceed both the work count and the
  empirically justified UW ceiling. The prior real UW run proved six streams
  safe, so four is within measured bounds.
Checkpoint and retry plan: Atomic per-night checkpoints under
  `Logs/pipeline_runs/ztf_alert_archive_portfolio/`; parent status in
  `Logs/reports/sharded_download_manifest.jsonl`; resume skips successful
  nights and restarts only incomplete streams.
Leakage and review controls: Historical replay only, before the 2024-09-21
  cutoff. Live-search data remains excluded from training/calibration.
  Time-aware known-object exclusion and adversarial plus operator review are
  mandatory before any candidate review.
Manifest: `data_selection/batch_manifests/ztf_dr24_coverage_selected_2024_v1.json`
Evidence: `docs/evidence/live/2026-07-14-ztf-field-night-coverage-preflight.md`
Expected value: A coverage-qualified real archival search of all six new
  fields. Metadata coverage does not guarantee retained alerts or tracklets;
  a clean null remains scientifically valid.
Safety: No MPC/NEOCP submission, NASA/PDCO contact, public alert, discovery
  claim, or impact-probability claim is authorized.

new_target_search

## 2026-07-14 — Coverage-selected ZTF DR24 result

Date: 2026-07-14
Repo: 2026 Near Earth Objects
Data: Completed four-night replay for
  `ztf_dr24_coverage_selected_2024_v1`
Role: live_search_result
Execution: Run `017eb50381badb75`; four archive-night shards x one worker;
  26.670482707 GB streamed in 10m36s; raw archives evicted during streaming
Storage: 2.2 MB durable checkpoints, keeping the project near 12 GB total and
  far below the 100 GB ceiling
Observed volume: 567,025 alerts scanned; 5,416 retained at `rb >= 0.5`
Production result: Five new fields had at least two populated retained nights;
  four had three. Association at `min_observations=3` formed zero tracklets.
Sensitivity: 222 fits at `min_observations=2`; every fit has exactly two
  observations across exactly two nights and is not a candidate.
Control: Fresh isolated ZTF injection run, seed 42, passed 20/20 detection,
  linking, and scoring using the documented analytic real/bogus proxy.
Interpretation: Exposure-level preflight improved the number of populated
  field/night cells but cannot guarantee retained alerts or a valid moving
  path. The completed batch is an honest null association result, not a model
  rejection or a discovery claim.
Evidence: `docs/evidence/live/2026-07-14-ztf-coverage-qualified-search-result.md`
Safety: Candidate review remains fail-closed. No time-aware known-object
  exclusion, classification, scoring, adversarial review, MPC/NEOCP
  submission, public alert, or impact-probability statement is authorized.

new_target_search

## 2026-07-14 — Sparse-field ZTF DR24 expansion

Date: 2026-07-14
Repo: 2026 Near Earth Objects
Data: Three unused UW ZTF public nightly archives targeting Aten 81.18,+22.50
  and IEO 147.53,+15.00
Role: live_search
Selection: Rank unused nights by combined target-field central-box exposure
  rows; HEAD-verify the top 12; choose the minimum-transfer three-night
  combination giving each target at least 80 rows
Nights: 20231003, 20231029, 20240429
Verified transfer: 19.053230740 GB
Exposure allocation: 98 rows for Aten 81.18; 88 for IEO 147.53
Execution: Three archive-night shards x one worker; raw archives streamed and
  evicted; retained output capped at 1 GB
Why this data: Run `017eb50381badb75` left these fields with only one and two
  populated retained nights. This is a bounded continuation of the same
  archival research path, not a model change or promotion decision.
Manifest: `data_selection/batch_manifests/ztf_dr24_sparse_field_expansion_2024_v1.json`
Evidence: `docs/evidence/live/2026-07-14-ztf-sparse-field-expansion-selection.md`
Safety: Historical replay and internal review only. No external submission,
  authority contact, public alert, discovery claim, or impact claim.

new_target_search

## 2026-07-14 — Sparse expansion and cross-batch result

Date: 2026-07-14
Repo: 2026 Near Earth Objects
Role: live_search_result
Execution: Run `56c2348f31302291`; three shards; 19.053230740 GB streamed;
  402,053 alerts scanned; 2,311 retained; 1.1 MB persisted
Single-batch result: Zero production tracklets and zero sensitivity tracklets;
  fresh isolated control passed 20/20 detection, linking, and scoring
Cross-batch result: Combined with `ztf_dr24_coverage_selected_2024_v1`; IEO
  147.53 had four retained nights and 8,956 seed pairs but zero production
  tracklets. All 70 sensitivity fits were two-point/two-night non-candidates.
Decision gate: No candidate-review queue exists. Further bulk expansion needs
  an explicit research decision rather than automatic continuation.
Evidence: `docs/evidence/live/2026-07-14-ztf-sparse-expansion-and-cross-batch-result.md`
Safety: No known-object exclusion, classification, scoring, adversarial review,
  submission, authority contact, public alert, discovery claim, or impact claim.

new_target_search
