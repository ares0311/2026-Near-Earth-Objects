from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from candidate_ledger import (
    CandidateLedgerDefaults,
    ingest_packets,
    init_ledger,
    list_records,
    main,
    record_from_packet,
    upsert_record,
)


def test_init_ledger_records_schema_version(tmp_path: Path) -> None:
    db_path = tmp_path / "candidate_ledger.sqlite"

    init_ledger(db_path)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT value FROM ledger_metadata WHERE key = 'schema_version'"
        ).fetchone()
    assert row == ("1",)


def test_record_from_full_scored_packet_extracts_policy_fields() -> None:
    packet = {
        "tracklet": {
            "object_id": "T-001",
            "observations": [
                {"obs_id": "a", "jd": 2460001.5},
                {"obs_id": "b", "jd": 2460003.5},
            ],
        },
        "posterior": {"neo_candidate": 0.42, "known_object": 0.03},
        "hazard": {"hazard_flag": "unknown", "alert_pathway": "internal_candidate"},
        "metadata": {"scorer_version": "score-v1"},
    }
    defaults = CandidateLedgerDefaults(
        source_dataset_id="manifest-001",
        candidate_generator="Skills/run_pipeline.py",
        regeneration_command="uv run --python 3.14 python Skills/run_pipeline.py ...",
    )

    record = record_from_packet(packet, defaults)

    assert record["candidate_id"] == "T-001"
    assert record["source_dataset_id"] == "manifest-001"
    assert json.loads(record["time_window_json"]) == {
        "start_jd": 2460001.5,
        "end_jd": 2460003.5,
        "scale": "JD",
    }
    assert json.loads(record["model_versions_json"]) == {"scorer_version": "score-v1"}
    assert json.loads(record["raw_packet_json"]) == packet


def test_ingest_pipeline_summary_list_upserts_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "candidate_ledger.sqlite"
    candidate_json = tmp_path / "candidates.json"
    candidate_json.write_text(
        json.dumps([
            {
                "object_id": "C-001",
                "neo_probability": 0.12,
                "discovery_priority": 0.4,
                "hazard_flag": "unknown",
            }
        ]),
        encoding="utf-8",
    )
    defaults = CandidateLedgerDefaults(
        source_dataset_id="manifest-001",
        candidate_generator="Skills/run_pipeline.py",
        regeneration_command="uv run --python 3.14 python Skills/run_pipeline.py ...",
        raw_uri="Logs/reports/example_candidates.json",
        preprocess_version="neo-detection-v0.90.61",
        review_status="needs_adversarial_review",
    )

    count = ingest_packets(db_path, candidate_json, defaults)
    records = list_records(db_path)

    assert count == 1
    assert records[0]["candidate_id"] == "C-001"
    assert records[0]["model_scores"]["neo_probability"] == 0.12
    assert records[0]["review_status"] == "needs_adversarial_review"
    assert records[0]["regeneration_command"].startswith("uv run --python 3.14")


def test_upsert_preserves_created_at_and_updates_review_status(tmp_path: Path) -> None:
    db_path = tmp_path / "candidate_ledger.sqlite"
    defaults = CandidateLedgerDefaults(
        source_dataset_id="manifest-001",
        candidate_generator="generator",
        regeneration_command="command",
    )
    record = record_from_packet({"object_id": "C-001"}, defaults)
    upsert_record(db_path, record)
    first = list_records(db_path)[0]

    updated = {**record, "review_status": "operator_rejected", "review_notes": "artifact"}
    upsert_record(db_path, updated)
    second = list_records(db_path)[0]

    assert second["created_at"] == first["created_at"]
    assert second["review_status"] == "operator_rejected"
    assert second["review_notes"] == "artifact"


def test_cli_ingest_and_list(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "candidate_ledger.sqlite"
    candidate_json = tmp_path / "candidate.json"
    candidate_json.write_text(json.dumps({"object_id": "C-CLI"}), encoding="utf-8")

    assert main([
        "ingest",
        str(candidate_json),
        "--db",
        str(db_path),
        "--source-dataset-id",
        "manifest-cli",
        "--candidate-generator",
        "test-generator",
        "--regeneration-command",
        "test command",
        "--candidate-generator-param",
        "radius=0.1",
    ]) == 0
    assert "Ingested 1 candidate" in capsys.readouterr().out

    assert main(["list", "--db", str(db_path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output[0]["candidate_id"] == "C-CLI"
    assert output[0]["candidate_generator_params"] == {"radius": "0.1"}
