"""SQLite durable-state store for the Hunter search lifecycle.

Complements src/candidate_ledger.py (candidate provenance -- the "candidate catalog"
Hunter entity, unchanged by this module) with the remaining required durable Hunter
entities: search manifest (``search_manifests`` + ``search_manifest_targets``), search
run (``search_runs`` + ``search_run_targets``), and follow-up registry
(``follow_up_registry``).

Target search history is intentionally NOT duplicated here. It already exists, tested
and wired into the production selector, as ``data_selection/target_priority_queue.csv``
via ``Skills/select_survey_fields.py``'s ``load_target_queue_history()`` /
``append_fields_to_target_queue()`` / ``update_target_queue_status()``. Building a
parallel SQLite history table would create exactly the kind of duplicate,
drift-prone store the Hunter directive warns against. Instead, ``target_id_from_radec``
below intentionally mirrors ``select_survey_fields._coordinate_key``'s
``round(x, 2)`` rounding convention, so a freshly ranked grid cell and its historical
CSV record always resolve to the identical key.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1"

_SEARCH_MODES = {"new", "follow_up"}
_MANIFEST_STATUSES = {"pending", "executed", "expired"}
_RUN_STATUSES = {"running", "completed", "partial", "failed"}
_RUN_TERMINAL_STATUSES = _RUN_STATUSES - {"running"}
_TARGET_EXECUTION_STATUSES = {"success", "null_result", "failed", "skipped"}
_FOLLOW_UP_STATUSES = {"open", "actioned", "dismissed", "expired"}


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _loads(text: str) -> Any:
    return json.loads(text)


def _non_empty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def target_id_from_radec(ra_deg: float, dec_deg: float) -> str:
    """Deterministic target key shared across manifests, runs, and follow-ups."""
    return f"radec_{round(float(ra_deg), 2):.2f}_{round(float(dec_deg), 2):.2f}"


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path) -> None:
    with closing(connect(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hunter_state_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS search_manifests (
                search_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                mode TEXT NOT NULL,
                requested_n INTEGER NOT NULL,
                actual_n_selected INTEGER NOT NULL,
                ranking_policy_path TEXT NOT NULL,
                ranking_policy_digest TEXT NOT NULL,
                discovery_pool_size_explored INTEGER NOT NULL,
                sufficiency_met INTEGER NOT NULL,
                config_json TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS search_manifest_targets (
                search_id TEXT NOT NULL REFERENCES search_manifests(search_id),
                rank INTEGER NOT NULL,
                target_id TEXT NOT NULL,
                ra_deg REAL NOT NULL,
                dec_deg REAL NOT NULL,
                score REAL NOT NULL,
                selection_reason TEXT NOT NULL,
                coverage_inventory_id TEXT,
                PRIMARY KEY (search_id, target_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_manifest_targets_search "
            "ON search_manifest_targets(search_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS search_runs (
                run_id TEXT PRIMARY KEY,
                search_id TEXT NOT NULL REFERENCES search_manifests(search_id),
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                git_sha TEXT NOT NULL,
                model_versions_json TEXT NOT NULL,
                failure_reason TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_search_runs_search_id ON search_runs(search_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS search_run_targets (
                run_id TEXT NOT NULL REFERENCES search_runs(run_id),
                target_id TEXT NOT NULL,
                execution_status TEXT NOT NULL,
                candidate_ids_json TEXT NOT NULL,
                error_message TEXT,
                nights_acquired_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (run_id, target_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS follow_up_registry (
                follow_up_id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id TEXT NOT NULL,
                candidate_id TEXT,
                flagged_at TEXT NOT NULL,
                reason TEXT NOT NULL,
                evidence_ref TEXT NOT NULL,
                priority REAL NOT NULL,
                status TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                originating_run_id TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_follow_up_status ON follow_up_registry(status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_follow_up_target ON follow_up_registry(target_id)"
        )
        now = _utc_now()
        conn.execute(
            """
            INSERT INTO hunter_state_metadata(key, value, updated_at)
            VALUES('schema_version', ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (SCHEMA_VERSION, now),
        )
        conn.commit()


@dataclass(frozen=True)
class ManifestTarget:
    target_id: str
    ra_deg: float
    dec_deg: float
    score: float
    selection_reason: str
    coverage_inventory_id: str | None = None


def create_search_manifest(
    db_path: Path,
    search_id: str,
    mode: str,
    requested_n: int,
    ranking_policy_path: str,
    ranking_policy_digest: str,
    targets: list[ManifestTarget],
    discovery_pool_size_explored: int,
    sufficiency_met: bool,
    config: dict[str, Any],
) -> None:
    """Persist a durable, pending search manifest with its exact selected targets.

    This must be called before any execution. ``run-new-search`` only ever loads the
    manifest back via ``get_search_manifest``/``get_latest_pending_manifest`` -- it
    never regenerates the selection.
    """
    if mode not in _SEARCH_MODES:
        raise ValueError(f"mode must be one of {sorted(_SEARCH_MODES)}, got {mode!r}")
    if requested_n <= 0:
        raise ValueError("requested_n must be positive")
    if len(targets) > requested_n:
        raise ValueError("targets must not exceed requested_n")
    if len({t.target_id for t in targets}) != len(targets):
        raise ValueError("manifest targets must have unique target_id values")

    init_db(db_path)
    now = _utc_now()
    with closing(connect(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO search_manifests(
                search_id, created_at, mode, requested_n, actual_n_selected,
                ranking_policy_path, ranking_policy_digest, discovery_pool_size_explored,
                sufficiency_met, config_json, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """,
            (
                search_id,
                now,
                mode,
                requested_n,
                len(targets),
                ranking_policy_path,
                ranking_policy_digest,
                discovery_pool_size_explored,
                int(sufficiency_met),
                _json(config),
            ),
        )
        for rank, target in enumerate(targets, start=1):
            conn.execute(
                """
                INSERT INTO search_manifest_targets(
                    search_id, rank, target_id, ra_deg, dec_deg, score,
                    selection_reason, coverage_inventory_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    search_id,
                    rank,
                    target.target_id,
                    target.ra_deg,
                    target.dec_deg,
                    target.score,
                    target.selection_reason,
                    target.coverage_inventory_id,
                ),
            )
        conn.commit()


def get_search_manifest(db_path: Path, search_id: str) -> dict[str, Any]:
    init_db(db_path)
    with closing(connect(db_path)) as conn:
        manifest_row = conn.execute(
            "SELECT * FROM search_manifests WHERE search_id = ?", (search_id,)
        ).fetchone()
        if manifest_row is None:
            raise ValueError(f"no search manifest found for search_id {search_id!r}")
        target_rows = conn.execute(
            "SELECT * FROM search_manifest_targets WHERE search_id = ? ORDER BY rank",
            (search_id,),
        ).fetchall()
    manifest = dict(manifest_row)
    manifest["config"] = _loads(manifest.pop("config_json"))
    manifest["sufficiency_met"] = bool(manifest["sufficiency_met"])
    manifest["targets"] = [dict(row) for row in target_rows]
    return manifest


def get_latest_pending_manifest(db_path: Path, mode: str | None = None) -> dict[str, Any]:
    init_db(db_path)
    with closing(connect(db_path)) as conn:
        if mode is not None:
            row = conn.execute(
                "SELECT search_id FROM search_manifests WHERE status = 'pending' "
                "AND mode = ? ORDER BY created_at DESC LIMIT 1",
                (mode,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT search_id FROM search_manifests WHERE status = 'pending' "
                "ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
    if row is None:
        raise ValueError("no pending search manifest exists")
    return get_search_manifest(db_path, row["search_id"])


def mark_manifest_status(db_path: Path, search_id: str, status: str) -> None:
    if status not in _MANIFEST_STATUSES:
        raise ValueError(f"status must be one of {sorted(_MANIFEST_STATUSES)}, got {status!r}")
    init_db(db_path)
    with closing(connect(db_path)) as conn:
        cur = conn.execute(
            "UPDATE search_manifests SET status = ? WHERE search_id = ?",
            (status, search_id),
        )
        if cur.rowcount == 0:
            raise ValueError(f"no search manifest found for search_id {search_id!r}")
        conn.commit()


def create_search_run(
    db_path: Path,
    run_id: str,
    search_id: str,
    git_sha: str,
    model_versions: dict[str, Any],
) -> None:
    init_db(db_path)
    now = _utc_now()
    with closing(connect(db_path)) as conn:
        exists = conn.execute(
            "SELECT 1 FROM search_manifests WHERE search_id = ?", (search_id,)
        ).fetchone()
        if exists is None:
            raise ValueError(f"no search manifest found for search_id {search_id!r}")
        conn.execute(
            """
            INSERT INTO search_runs(
                run_id, search_id, started_at, completed_at, status,
                git_sha, model_versions_json, failure_reason
            ) VALUES (?, ?, ?, NULL, 'running', ?, ?, NULL)
            """,
            (run_id, search_id, now, _non_empty(git_sha, "git_sha"), _json(model_versions)),
        )
        conn.commit()


def get_search_run(db_path: Path, run_id: str) -> dict[str, Any]:
    init_db(db_path)
    with closing(connect(db_path)) as conn:
        row = conn.execute(
            "SELECT * FROM search_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
    if row is None:
        raise ValueError(f"no search run found for run_id {run_id!r}")
    run = dict(row)
    run["model_versions"] = _loads(run.pop("model_versions_json"))
    return run


def complete_search_run(
    db_path: Path, run_id: str, status: str, failure_reason: str | None = None
) -> None:
    if status not in _RUN_TERMINAL_STATUSES:
        raise ValueError(
            f"terminal status must be one of {sorted(_RUN_TERMINAL_STATUSES)}, got {status!r}"
        )
    init_db(db_path)
    now = _utc_now()
    with closing(connect(db_path)) as conn:
        cur = conn.execute(
            "UPDATE search_runs SET status = ?, completed_at = ?, failure_reason = ? "
            "WHERE run_id = ?",
            (status, now, failure_reason, run_id),
        )
        if cur.rowcount == 0:
            raise ValueError(f"no search run found for run_id {run_id!r}")
        conn.commit()


def upsert_run_target(
    db_path: Path,
    run_id: str,
    target_id: str,
    execution_status: str,
    candidate_ids: list[str] | None = None,
    error_message: str | None = None,
    nights_acquired: list[str] | None = None,
) -> None:
    if execution_status not in _TARGET_EXECUTION_STATUSES:
        raise ValueError(
            f"execution_status must be one of {sorted(_TARGET_EXECUTION_STATUSES)}, "
            f"got {execution_status!r}"
        )
    init_db(db_path)
    now = _utc_now()
    with closing(connect(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO search_run_targets(
                run_id, target_id, execution_status, candidate_ids_json,
                error_message, nights_acquired_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, target_id) DO UPDATE SET
                execution_status=excluded.execution_status,
                candidate_ids_json=excluded.candidate_ids_json,
                error_message=excluded.error_message,
                nights_acquired_json=excluded.nights_acquired_json,
                updated_at=excluded.updated_at
            """,
            (
                run_id,
                target_id,
                execution_status,
                _json(candidate_ids or []),
                error_message,
                _json(nights_acquired or []),
                now,
            ),
        )
        conn.commit()


def get_run_targets(db_path: Path, run_id: str) -> dict[str, dict[str, Any]]:
    """Keyed by target_id -- used by ``run-new-search`` to skip already-completed
    targets on resume after an interruption."""
    init_db(db_path)
    with closing(connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT * FROM search_run_targets WHERE run_id = ?", (run_id,)
        ).fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        item["candidate_ids"] = _loads(item.pop("candidate_ids_json"))
        item["nights_acquired"] = _loads(item.pop("nights_acquired_json"))
        result[item["target_id"]] = item
    return result


def add_follow_up(
    db_path: Path,
    target_id: str,
    reason: str,
    priority: float,
    recommended_action: str,
    evidence_ref: str,
    candidate_id: str | None = None,
    originating_run_id: str | None = None,
) -> int:
    init_db(db_path)
    now = _utc_now()
    with closing(connect(db_path)) as conn:
        cur = conn.execute(
            """
            INSERT INTO follow_up_registry(
                target_id, candidate_id, flagged_at, reason, evidence_ref,
                priority, status, recommended_action, originating_run_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
            """,
            (
                _non_empty(target_id, "target_id"),
                candidate_id,
                now,
                _non_empty(reason, "reason"),
                _non_empty(evidence_ref, "evidence_ref"),
                priority,
                _non_empty(recommended_action, "recommended_action"),
                originating_run_id,
                now,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_follow_ups(
    db_path: Path, status: str | None = "open", limit: int | None = None
) -> list[dict[str, Any]]:
    init_db(db_path)
    query = "SELECT * FROM follow_up_registry"
    params: tuple[Any, ...] = ()
    if status is not None:
        if status not in _FOLLOW_UP_STATUSES:
            raise ValueError(f"status must be one of {sorted(_FOLLOW_UP_STATUSES)}, got {status!r}")
        query += " WHERE status = ?"
        params = (status,)
    query += " ORDER BY priority DESC, flagged_at DESC"
    if limit is not None:
        query += f" LIMIT {int(limit)}"
    with closing(connect(db_path)) as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def update_follow_up_status(db_path: Path, follow_up_id: int, status: str) -> None:
    if status not in _FOLLOW_UP_STATUSES:
        raise ValueError(f"status must be one of {sorted(_FOLLOW_UP_STATUSES)}, got {status!r}")
    init_db(db_path)
    now = _utc_now()
    with closing(connect(db_path)) as conn:
        cur = conn.execute(
            "UPDATE follow_up_registry SET status = ?, updated_at = ? WHERE follow_up_id = ?",
            (status, now, follow_up_id),
        )
        if cur.rowcount == 0:
            raise ValueError(f"no follow-up found for follow_up_id {follow_up_id}")
        conn.commit()
