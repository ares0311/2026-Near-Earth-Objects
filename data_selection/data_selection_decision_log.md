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
