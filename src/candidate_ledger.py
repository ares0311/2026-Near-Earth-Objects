"""SQLite candidate ledger for reproducible Astrometrics candidate packets."""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT = "2026 Near Earth Objects"
SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class CandidateLedgerDefaults:
    source_dataset_id: str
    candidate_generator: str
    regeneration_command: str
    target_id: str = "unknown"
    raw_uri: str = "not-recorded"
    preprocess_version: str = "not-recorded"
    review_status: str = "pending_review"
    review_notes: str = ""
    candidate_generator_params: dict[str, Any] | None = None
    model_versions: dict[str, Any] | None = None
    score_quantiles: dict[str, Any] | None = None
    injection_context: dict[str, Any] | None = None
    nearest_known_artifacts: list[dict[str, Any]] | None = None
    time_window: dict[str, Any] | None = None


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _loads(text: str) -> Any:
    return json.loads(text)


def _non_empty(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_ledger(db_path: Path) -> None:
    with closing(connect(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ledger_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS candidates (
                candidate_id TEXT PRIMARY KEY,
                project TEXT NOT NULL,
                source_dataset_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                time_window_json TEXT NOT NULL,
                raw_uri TEXT NOT NULL,
                preprocess_version TEXT NOT NULL,
                candidate_generator TEXT NOT NULL,
                candidate_generator_params_json TEXT NOT NULL,
                model_versions_json TEXT NOT NULL,
                model_scores_json TEXT NOT NULL,
                calibrated_scores_json TEXT NOT NULL,
                score_quantiles_json TEXT NOT NULL,
                injection_context_json TEXT NOT NULL,
                nearest_known_artifacts_json TEXT NOT NULL,
                review_status TEXT NOT NULL,
                review_notes TEXT NOT NULL,
                regeneration_command TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                raw_packet_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_candidates_source_dataset "
            "ON candidates(source_dataset_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_candidates_review_status "
            "ON candidates(review_status)"
        )
        now = _utc_now()
        conn.execute(
            """
            INSERT INTO ledger_metadata(key, value, updated_at)
            VALUES('schema_version', ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (SCHEMA_VERSION, now),
        )
        conn.commit()


def _packet_candidate_id(packet: dict[str, Any]) -> str:
    if isinstance(packet.get("object_id"), str):
        return packet["object_id"]
    tracklet = packet.get("tracklet")
    if isinstance(tracklet, dict) and isinstance(tracklet.get("object_id"), str):
        return tracklet["object_id"]
    if isinstance(packet.get("candidate_id"), str):
        return packet["candidate_id"]
    raise ValueError("candidate packet must include object_id, candidate_id, or tracklet.object_id")


def _time_window_from_packet(
    packet: dict[str, Any], defaults: CandidateLedgerDefaults
) -> dict[str, Any]:
    if defaults.time_window is not None:
        return defaults.time_window
    tracklet = packet.get("tracklet")
    observations = tracklet.get("observations", []) if isinstance(tracklet, dict) else []
    jds = [
        obs.get("jd")
        for obs in observations
        if isinstance(obs, dict) and isinstance(obs.get("jd"), int | float)
    ]
    if jds:
        return {"start_jd": min(jds), "end_jd": max(jds), "scale": "JD"}
    return {"start": "not-recorded", "end": "not-recorded", "scale": "unknown"}


def _model_scores_from_packet(packet: dict[str, Any]) -> dict[str, Any]:
    scores: dict[str, Any] = {}
    if "neo_probability" in packet:
        scores["neo_probability"] = packet["neo_probability"]
    if "discovery_priority" in packet:
        scores["discovery_priority"] = packet["discovery_priority"]
    posterior = packet.get("posterior")
    if isinstance(posterior, dict):
        scores["posterior"] = posterior
    hazard = packet.get("hazard")
    if isinstance(hazard, dict):
        scores["hazard"] = {
            key: hazard.get(key)
            for key in ("hazard_flag", "alert_pathway", "moid_au", "neo_class")
            if key in hazard
        }
    return scores


def _model_versions_from_packet(
    packet: dict[str, Any], defaults: CandidateLedgerDefaults
) -> dict[str, Any]:
    versions = dict(defaults.model_versions or {})
    metadata = packet.get("metadata")
    if isinstance(metadata, dict) and metadata.get("scorer_version"):
        versions.setdefault("scorer_version", metadata["scorer_version"])
    return versions


def record_from_packet(
    packet: dict[str, Any], defaults: CandidateLedgerDefaults
) -> dict[str, Any]:
    candidate_id = _packet_candidate_id(packet)
    now = _utc_now()
    model_scores = _model_scores_from_packet(packet)
    return {
        "candidate_id": candidate_id,
        "project": PROJECT,
        "source_dataset_id": defaults.source_dataset_id,
        "target_id": defaults.target_id if defaults.target_id != "unknown" else candidate_id,
        "time_window_json": _json(_time_window_from_packet(packet, defaults)),
        "raw_uri": defaults.raw_uri,
        "preprocess_version": defaults.preprocess_version,
        "candidate_generator": defaults.candidate_generator,
        "candidate_generator_params_json": _json(defaults.candidate_generator_params or {}),
        "model_versions_json": _json(_model_versions_from_packet(packet, defaults)),
        "model_scores_json": _json(model_scores),
        "calibrated_scores_json": _json(model_scores),
        "score_quantiles_json": _json(defaults.score_quantiles or {}),
        "injection_context_json": _json(defaults.injection_context or {}),
        "nearest_known_artifacts_json": _json(defaults.nearest_known_artifacts or []),
        "review_status": defaults.review_status,
        "review_notes": defaults.review_notes,
        "regeneration_command": defaults.regeneration_command,
        "created_at": now,
        "updated_at": now,
        "raw_packet_json": _json(packet),
    }


def validate_record(record: dict[str, Any]) -> None:
    for key in (
        "candidate_id",
        "project",
        "source_dataset_id",
        "target_id",
        "raw_uri",
        "preprocess_version",
        "candidate_generator",
        "review_status",
        "regeneration_command",
        "created_at",
        "updated_at",
    ):
        _non_empty(record[key], key)
    if record["project"] != PROJECT:
        raise ValueError(f"project must be {PROJECT!r}")
    for key in (
        "time_window_json",
        "candidate_generator_params_json",
        "model_versions_json",
        "model_scores_json",
        "calibrated_scores_json",
        "score_quantiles_json",
        "injection_context_json",
        "nearest_known_artifacts_json",
        "raw_packet_json",
    ):
        _loads(record[key])


def upsert_record(db_path: Path, record: dict[str, Any]) -> None:
    validate_record(record)
    init_ledger(db_path)
    with closing(connect(db_path)) as conn:
        existing = conn.execute(
            "SELECT created_at FROM candidates WHERE candidate_id = ?",
            (record["candidate_id"],),
        ).fetchone()
        if existing is not None:
            record = {**record, "created_at": existing["created_at"], "updated_at": _utc_now()}
        columns = tuple(record)
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(
            f"{column}=excluded.{column}" for column in columns if column != "candidate_id"
        )
        conn.execute(
            f"""
            INSERT INTO candidates({", ".join(columns)})
            VALUES({placeholders})
            ON CONFLICT(candidate_id) DO UPDATE SET {updates}
            """,
            tuple(record[column] for column in columns),
        )
        conn.commit()


def load_candidate_packets(path: Path) -> list[dict[str, Any]]:
    decoded = json.loads(path.read_text(encoding="utf-8"))
    packets = decoded if isinstance(decoded, list) else [decoded]
    if not all(isinstance(packet, dict) for packet in packets):
        raise ValueError("candidate input must be a JSON object or list of objects")
    return packets


def ingest_packets(
    db_path: Path, candidate_json: Path, defaults: CandidateLedgerDefaults
) -> int:
    count = 0
    for packet in load_candidate_packets(candidate_json):
        upsert_record(db_path, record_from_packet(packet, defaults))
        count += 1
    return count


def list_records(db_path: Path) -> list[dict[str, Any]]:
    init_ledger(db_path)
    with closing(connect(db_path)) as conn:
        rows = conn.execute("SELECT * FROM candidates ORDER BY candidate_id").fetchall()
    records: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        for key in list(item):
            if key.endswith("_json"):
                item[key[:-5]] = _loads(item.pop(key))
        records.append(item)
    return records


def _parse_key_values(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"expected KEY=VALUE, got {value!r}")
        key, item = value.split("=", 1)
        parsed[_non_empty(key, "key")] = item
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init_cmd = sub.add_parser("init", help="create or migrate the candidate ledger")
    init_cmd.add_argument("--db", type=Path, required=True)

    ingest_cmd = sub.add_parser("ingest", help="ingest pipeline candidate JSON into the ledger")
    ingest_cmd.add_argument("candidate_json", type=Path)
    ingest_cmd.add_argument("--db", type=Path, required=True)
    ingest_cmd.add_argument("--source-dataset-id", required=True)
    ingest_cmd.add_argument("--candidate-generator", required=True)
    ingest_cmd.add_argument("--regeneration-command", required=True)
    ingest_cmd.add_argument("--target-id", default="unknown")
    ingest_cmd.add_argument("--raw-uri", default="not-recorded")
    ingest_cmd.add_argument("--preprocess-version", default="not-recorded")
    ingest_cmd.add_argument("--review-status", default="pending_review")
    ingest_cmd.add_argument("--review-notes", default="")
    ingest_cmd.add_argument(
        "--candidate-generator-param",
        action="append",
        default=[],
        metavar="KEY=VALUE",
    )

    list_cmd = sub.add_parser("list", help="print ledger rows as JSON")
    list_cmd.add_argument("--db", type=Path, required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "init":
        init_ledger(args.db)
        print(f"Initialized candidate ledger: {args.db}")
        return 0
    if args.command == "ingest":
        params = _parse_key_values(args.candidate_generator_param)
        defaults = CandidateLedgerDefaults(
            source_dataset_id=args.source_dataset_id,
            candidate_generator=args.candidate_generator,
            regeneration_command=args.regeneration_command,
            target_id=args.target_id,
            raw_uri=args.raw_uri,
            preprocess_version=args.preprocess_version,
            review_status=args.review_status,
            review_notes=args.review_notes,
            candidate_generator_params=params,
        )
        count = ingest_packets(args.db, args.candidate_json, defaults)
        print(f"Ingested {count} candidate(s) into {args.db}")
        return 0
    if args.command == "list":
        print(json.dumps(list_records(args.db), indent=2, sort_keys=True))
        return 0
    raise AssertionError(f"unhandled command {args.command}")  # pragma: no cover
