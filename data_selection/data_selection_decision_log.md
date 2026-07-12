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
