# Candidate Ledger

A2 requires candidate packets to be reproducible from a local SQLite or parquet
ledger. This repository uses SQLite because it is available in the Python
standard library and is durable enough for operator review packets.

Create or ingest a ledger with:

```bash
PYTHONPATH=src uv run --python 3.14 python Skills/candidate_ledger.py init \
  --db data_selection/candidate_ledger.sqlite

PYTHONPATH=src uv run --python 3.14 python Skills/candidate_ledger.py ingest \
  Logs/reports/example_candidates.json \
  --db data_selection/candidate_ledger.sqlite \
  --source-dataset-id manifest-id \
  --candidate-generator Skills/run_pipeline.py \
  --regeneration-command "PYTHONPATH=src uv run --python 3.14 python Skills/run_pipeline.py ..."
```

The SQLite database itself is local operational state and should not be
committed. Commit manifest definitions, schema changes, reports, and compact
evidence summaries instead.

Required ledger fields are implemented in `src/candidate_ledger.py`:

- `candidate_id`
- `project`
- `source_dataset_id`
- `target_id`
- `time_window`
- `raw_uri`
- `preprocess_version`
- `candidate_generator`
- `candidate_generator_params`
- `model_versions`
- `model_scores`
- `calibrated_scores`
- `score_quantiles`
- `injection_context`
- `nearest_known_artifacts`
- `review_status`
- `review_notes`
- `regeneration_command`
- `created_at`
- `updated_at`
- `raw_packet`
