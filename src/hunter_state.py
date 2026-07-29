"""SQLite durable-state store for the Hunter search lifecycle.

Keeps the planning ``target_catalog`` distinct from src/candidate_ledger.py's
post-detection candidate evidence. The other durable entities are search manifest
(``search_manifests`` + ``search_manifest_targets``), search run
(``search_runs`` + ``search_run_targets``), append-only target search history
(``target_search_history``), and follow-up registry (``follow_up_registry``).

The legacy ``target_priority_queue.csv`` remains an imported scientific-planning
source, but it is not safe as the transactional production history store: ranks are
not stable identifiers and manifest/run writes cannot be committed with CSV updates.
This module is therefore the canonical history system of record. Existing durable
manifest targets are backfilled as history during the schema-v2 migration so a
previously selected target cannot silently become ``new`` again.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "3"

_SEARCH_MODES = {"new", "follow_up"}
_MANIFEST_STATUSES = {"pending", "executed", "expired"}
_RUN_STATUSES = {"running", "completed", "partial", "failed"}
_RUN_TERMINAL_STATUSES = _RUN_STATUSES - {"running"}
_TARGET_EXECUTION_STATUSES = {"success", "null_result", "failed", "skipped"}
_FOLLOW_UP_STATUSES = {"open", "actioned", "dismissed", "expired"}
_VALIDITY_STATES = {
    "valid",
    "stale-but-usable",
    "refresh-required",
    "invalid",
    "unknown",
}


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


_TARGET_ID_PATTERN = re.compile(r"^radec_(-?\d+\.\d+)_(-?\d+\.\d+)$")


def radec_from_target_id(target_id: str) -> tuple[float, float]:
    """Inverse of ``target_id_from_radec`` -- used where a target's RA/Dec is
    needed but only its durable ``target_id`` string is stored (e.g. the
    follow-up registry)."""
    match = _TARGET_ID_PATTERN.match(target_id)
    if match is None:
        raise ValueError(f"target_id {target_id!r} is not a radec_<ra>_<dec> key")
    return float(match.group(1)), float(match.group(2))


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
            CREATE TABLE IF NOT EXISTS target_catalog (
                target_id TEXT NOT NULL,
                primary_survey_id TEXT NOT NULL,
                canonical_id TEXT NOT NULL,
                target_kind TEXT NOT NULL,
                survey TEXT NOT NULL,
                ra_deg REAL NOT NULL,
                dec_deg REAL NOT NULL,
                neo_class TEXT NOT NULL,
                catalog_version TEXT NOT NULL,
                ranking_score REAL NOT NULL,
                estimated_storage_mb REAL NOT NULL,
                estimated_compute_seconds REAL NOT NULL,
                scientific_metrics_json TEXT NOT NULL,
                source_provenance_json TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (catalog_version, target_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_target_catalog_class_score "
            "ON target_catalog(neo_class, ranking_score DESC)"
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
                coverage_provenance_json TEXT NOT NULL DEFAULT '{}',
                validity_state TEXT NOT NULL DEFAULT 'unknown',
                primary_survey_id TEXT NOT NULL DEFAULT '',
                canonical_id TEXT NOT NULL DEFAULT '',
                target_kind TEXT NOT NULL DEFAULT 'sky_field',
                survey TEXT NOT NULL DEFAULT 'ZTF DR24',
                prior_search_count INTEGER NOT NULL DEFAULT 0,
                prior_search_provenance_json TEXT NOT NULL DEFAULT '[]',
                estimated_storage_mb REAL NOT NULL DEFAULT 0,
                estimated_compute_seconds REAL NOT NULL DEFAULT 0,
                scientific_metrics_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (search_id, target_id)
            )
            """
        )
        manifest_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(search_manifest_targets)").fetchall()
        }
        if "coverage_provenance_json" not in manifest_columns:
            conn.execute(
                "ALTER TABLE search_manifest_targets "
                "ADD COLUMN coverage_provenance_json TEXT NOT NULL DEFAULT '{}'"
            )
        if "validity_state" not in manifest_columns:
            conn.execute(
                "ALTER TABLE search_manifest_targets "
                "ADD COLUMN validity_state TEXT NOT NULL DEFAULT 'unknown'"
            )
        manifest_additions = {
            "primary_survey_id": "TEXT NOT NULL DEFAULT ''",
            "canonical_id": "TEXT NOT NULL DEFAULT ''",
            "target_kind": "TEXT NOT NULL DEFAULT 'sky_field'",
            "survey": "TEXT NOT NULL DEFAULT 'ZTF DR24'",
            "prior_search_count": "INTEGER NOT NULL DEFAULT 0",
            "prior_search_provenance_json": "TEXT NOT NULL DEFAULT '[]'",
            "estimated_storage_mb": "REAL NOT NULL DEFAULT 0",
            "estimated_compute_seconds": "REAL NOT NULL DEFAULT 0",
            "scientific_metrics_json": "TEXT NOT NULL DEFAULT '{}'",
        }
        for column, definition in manifest_additions.items():
            if column not in manifest_columns:
                conn.execute(
                    f"ALTER TABLE search_manifest_targets ADD COLUMN {column} {definition}"
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
            CREATE TABLE IF NOT EXISTS target_search_history (
                history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id TEXT NOT NULL,
                search_id TEXT NOT NULL REFERENCES search_manifests(search_id),
                run_id TEXT,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                source TEXT NOT NULL,
                nights_json TEXT NOT NULL,
                provenance_json TEXT NOT NULL,
                UNIQUE(search_id, target_id, status)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_target_history_target "
            "ON target_search_history(target_id, occurred_at)"
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
                required_data TEXT NOT NULL DEFAULT '',
                estimated_storage_mb REAL NOT NULL DEFAULT 0,
                estimated_compute_seconds REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        follow_up_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(follow_up_registry)").fetchall()
        }
        follow_up_additions = {
            "required_data": "TEXT NOT NULL DEFAULT ''",
            "estimated_storage_mb": "REAL NOT NULL DEFAULT 0",
            "estimated_compute_seconds": "REAL NOT NULL DEFAULT 0",
        }
        for column, definition in follow_up_additions.items():
            if column not in follow_up_columns:
                conn.execute(
                    f"ALTER TABLE follow_up_registry ADD COLUMN {column} {definition}"
                )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_follow_up_status ON follow_up_registry(status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_follow_up_target ON follow_up_registry(target_id)"
        )
        now = _utc_now()
        # Schema-v1 manifests are real prior selection evidence. Import them
        # idempotently so upgrading cannot make an old target appear new.
        conn.execute(
            """
            INSERT OR IGNORE INTO target_search_history(
                target_id, search_id, run_id, mode, status, occurred_at,
                source, nights_json, provenance_json
            )
            SELECT t.target_id, m.search_id, NULL, m.mode, 'legacy_manifest_import',
                   m.created_at, 'hunter_state_schema_v2_migration', '[]',
                   '{"migration":"manifest-target-backfill"}'
            FROM search_manifest_targets AS t
            JOIN search_manifests AS m ON m.search_id = t.search_id
            WHERE NOT EXISTS (
                SELECT 1 FROM target_search_history AS h
                WHERE h.search_id = t.search_id AND h.target_id = t.target_id
            )
            """
        )
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
    coverage_provenance: dict[str, Any] | None = None
    validity_state: str = "unknown"
    primary_survey_id: str = ""
    canonical_id: str = ""
    target_kind: str = "sky_field"
    survey: str = "ZTF DR24"
    prior_search_count: int = 0
    prior_search_provenance: list[dict[str, Any]] | None = None
    estimated_storage_mb: float = 0.0
    estimated_compute_seconds: float = 0.0
    scientific_metrics: dict[str, Any] | None = None


@dataclass(frozen=True)
class CatalogTarget:
    target_id: str
    primary_survey_id: str
    canonical_id: str
    target_kind: str
    survey: str
    ra_deg: float
    dec_deg: float
    neo_class: str
    ranking_score: float
    estimated_storage_mb: float
    estimated_compute_seconds: float
    scientific_metrics: dict[str, Any]
    source_provenance: dict[str, Any]


def upsert_target_catalog(
    db_path: Path,
    *,
    catalog_version: str,
    targets: list[CatalogTarget],
) -> int:
    """Durably materialize a versioned planning universe."""

    _non_empty(catalog_version, "catalog_version")
    if not targets:
        raise ValueError("target catalog must contain at least one target")
    if len({target.target_id for target in targets}) != len(targets):
        raise ValueError("target catalog must contain unique target_id values")
    init_db(db_path)
    now = _utc_now()
    with closing(connect(db_path)) as conn:
        for target in targets:
            conn.execute(
                """
                INSERT INTO target_catalog(
                    target_id, primary_survey_id, canonical_id, target_kind, survey,
                    ra_deg, dec_deg, neo_class, catalog_version, ranking_score,
                    estimated_storage_mb, estimated_compute_seconds,
                    scientific_metrics_json, source_provenance_json,
                    first_seen_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(catalog_version, target_id) DO UPDATE SET
                    primary_survey_id=excluded.primary_survey_id,
                    canonical_id=excluded.canonical_id,
                    target_kind=excluded.target_kind,
                    survey=excluded.survey,
                    ra_deg=excluded.ra_deg,
                    dec_deg=excluded.dec_deg,
                    neo_class=excluded.neo_class,
                    catalog_version=excluded.catalog_version,
                    ranking_score=excluded.ranking_score,
                    estimated_storage_mb=excluded.estimated_storage_mb,
                    estimated_compute_seconds=excluded.estimated_compute_seconds,
                    scientific_metrics_json=excluded.scientific_metrics_json,
                    source_provenance_json=excluded.source_provenance_json,
                    updated_at=excluded.updated_at
                """,
                (
                    _non_empty(target.target_id, "target_id"),
                    _non_empty(target.primary_survey_id, "primary_survey_id"),
                    _non_empty(target.canonical_id, "canonical_id"),
                    _non_empty(target.target_kind, "target_kind"),
                    _non_empty(target.survey, "survey"),
                    target.ra_deg,
                    target.dec_deg,
                    _non_empty(target.neo_class, "neo_class"),
                    catalog_version,
                    target.ranking_score,
                    target.estimated_storage_mb,
                    target.estimated_compute_seconds,
                    _json(target.scientific_metrics),
                    _json(target.source_provenance),
                    now,
                    now,
                ),
            )
        conn.commit()
    return len(targets)


def list_target_catalog(
    db_path: Path, *, catalog_version: str | None = None
) -> list[dict[str, Any]]:
    init_db(db_path)
    query = "SELECT * FROM target_catalog"
    params: tuple[Any, ...] = ()
    if catalog_version is not None:
        query += " WHERE catalog_version = ?"
        params = (catalog_version,)
    query += " ORDER BY ranking_score DESC, target_id"
    with closing(connect(db_path)) as conn:
        rows = conn.execute(query, params).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["scientific_metrics"] = _loads(item.pop("scientific_metrics_json"))
        item["source_provenance"] = _loads(item.pop("source_provenance_json"))
        result.append(item)
    return result


def target_catalog_count(db_path: Path, *, catalog_version: str) -> int:
    init_db(db_path)
    with closing(connect(db_path)) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM target_catalog WHERE catalog_version = ?",
            (_non_empty(catalog_version, "catalog_version"),),
        ).fetchone()
    return int(row["n"])


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
    if not sufficiency_met:
        raise ValueError("search manifest requires sufficiency_met=true")
    if len(targets) != requested_n:
        raise ValueError(
            "search manifest target count must exactly match requested_n "
            f"({len(targets)} != {requested_n})"
        )
    if len({t.target_id for t in targets}) != len(targets):
        raise ValueError("manifest targets must have unique target_id values")
    invalid_validity = [
        t.validity_state for t in targets if t.validity_state not in _VALIDITY_STATES
    ]
    if invalid_validity:
        raise ValueError(f"invalid manifest target validity_state {invalid_validity[0]!r}")

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
            if mode == "new":
                prior = conn.execute(
                    "SELECT 1 FROM target_search_history WHERE target_id = ? LIMIT 1",
                    (target.target_id,),
                ).fetchone()
                if prior is not None:
                    raise ValueError(
                        f"target {target.target_id} already has governing search history "
                        "and is not eligible for mode=new"
                    )
            conn.execute(
                """
                INSERT INTO search_manifest_targets(
                    search_id, rank, target_id, ra_deg, dec_deg, score,
                    selection_reason, coverage_inventory_id,
                    coverage_provenance_json, validity_state, primary_survey_id,
                    canonical_id, target_kind, survey, prior_search_count,
                    prior_search_provenance_json, estimated_storage_mb,
                    estimated_compute_seconds, scientific_metrics_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    _json(target.coverage_provenance or {}),
                    target.validity_state,
                    target.primary_survey_id,
                    target.canonical_id,
                    target.target_kind,
                    target.survey,
                    target.prior_search_count,
                    _json(target.prior_search_provenance or []),
                    target.estimated_storage_mb,
                    target.estimated_compute_seconds,
                    _json(target.scientific_metrics or {}),
                ),
            )
            conn.execute(
                """
                INSERT INTO target_search_history(
                    target_id, search_id, run_id, mode, status, occurred_at,
                    source, nights_json, provenance_json
                ) VALUES (?, ?, NULL, ?, 'selected_pending', ?,
                          'hunter_manifest_selection', '[]', ?)
                """,
                (
                    target.target_id,
                    search_id,
                    mode,
                    now,
                    _json(
                        {
                            "ranking_policy_digest": ranking_policy_digest,
                            "selection_reason": target.selection_reason,
                        }
                    ),
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
    manifest["targets"] = []
    for row in target_rows:
        target = dict(row)
        target["coverage_provenance"] = _loads(
            target.pop("coverage_provenance_json")
        )
        target["prior_search_provenance"] = _loads(
            target.pop("prior_search_provenance_json")
        )
        target["scientific_metrics"] = _loads(target.pop("scientific_metrics_json"))
        manifest["targets"].append(target)
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


def get_latest_run_for_search(db_path: Path, search_id: str) -> dict[str, Any] | None:
    """Used by ``run-new-search`` to resume an interrupted run or refuse to
    silently re-execute an already-completed one, instead of always minting
    a fresh run_id."""
    init_db(db_path)
    with closing(connect(db_path)) as conn:
        row = conn.execute(
            "SELECT run_id FROM search_runs WHERE search_id = ? ORDER BY started_at DESC LIMIT 1",
            (search_id,),
        ).fetchone()
    if row is None:
        return None
    return get_search_run(db_path, row["run_id"])


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


def update_search_run_model_versions(
    db_path: Path, run_id: str, updates: dict[str, Any]
) -> None:
    """Add provenance fields to an existing run without discarding prior versions."""
    if not updates:
        raise ValueError("model-version updates must not be empty")
    run = get_search_run(db_path, run_id)
    merged = {**run["model_versions"], **updates}
    with closing(connect(db_path)) as conn:
        conn.execute(
            "UPDATE search_runs SET model_versions_json = ? WHERE run_id = ?",
            (_json(merged), run_id),
        )
        conn.commit()


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


def commit_target_result(
    db_path: Path,
    *,
    run_id: str,
    search_id: str,
    mode: str,
    target_id: str,
    execution_status: str,
    candidate_ids: list[str],
    error_message: str | None,
    nights_acquired: list[str],
    provenance: dict[str, Any],
) -> None:
    """Atomically checkpoint a run target and append its governing history.

    Candidate-ledger/follow-up side effects happen before this transaction and
    are idempotent. A crash therefore leaves this target retryable; once this
    transaction commits, resume may safely skip it without losing downstream
    results.
    """
    if execution_status not in _TARGET_EXECUTION_STATUSES:
        raise ValueError(
            f"execution_status must be one of {sorted(_TARGET_EXECUTION_STATUSES)}, "
            f"got {execution_status!r}"
        )
    if mode not in _SEARCH_MODES:
        raise ValueError(f"mode must be one of {sorted(_SEARCH_MODES)}, got {mode!r}")
    init_db(db_path)
    now = _utc_now()
    with closing(connect(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO target_search_history(
                target_id, search_id, run_id, mode, status, occurred_at,
                source, nights_json, provenance_json
            ) VALUES (?, ?, ?, ?, ?, ?, 'hunter_run_execution', ?, ?)
            ON CONFLICT(search_id, target_id, status) DO UPDATE SET
                run_id=excluded.run_id,
                nights_json=excluded.nights_json,
                provenance_json=excluded.provenance_json
            """,
            (
                _non_empty(target_id, "target_id"),
                _non_empty(search_id, "search_id"),
                _non_empty(run_id, "run_id"),
                mode,
                execution_status,
                now,
                _json(nights_acquired),
                _json(provenance),
            ),
        )
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
                _json(candidate_ids),
                error_message,
                _json(nights_acquired),
                now,
            ),
        )
        conn.commit()


def list_target_history(
    db_path: Path, target_id: str | None = None
) -> list[dict[str, Any]]:
    """Return append-only history in chronological order with decoded evidence."""
    init_db(db_path)
    query = "SELECT * FROM target_search_history"
    params: tuple[Any, ...] = ()
    if target_id is not None:
        query += " WHERE target_id = ?"
        params = (target_id,)
    query += " ORDER BY occurred_at, history_id"
    with closing(connect(db_path)) as conn:
        rows = conn.execute(query, params).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["nights"] = _loads(item.pop("nights_json"))
        item["provenance"] = _loads(item.pop("provenance_json"))
        result.append(item)
    return result


def searched_target_ids(db_path: Path) -> set[str]:
    """All stable identities ever reserved or searched under governing history."""
    init_db(db_path)
    with closing(connect(db_path)) as conn:
        rows = conn.execute("SELECT DISTINCT target_id FROM target_search_history").fetchall()
    return {str(row["target_id"]) for row in rows}


def acquired_nights_for_target(db_path: Path, target_id: str) -> set[str]:
    """Union the real nights already acquired for a target across all runs."""
    nights: set[str] = set()
    for event in list_target_history(db_path, target_id):
        nights.update(str(night) for night in event["nights"])
    return nights


def add_follow_up(
    db_path: Path,
    target_id: str,
    reason: str,
    priority: float,
    recommended_action: str,
    evidence_ref: str,
    candidate_id: str | None = None,
    originating_run_id: str | None = None,
    required_data: str = "operator review packet and independent follow-up astrometry",
    estimated_storage_mb: float = 0.0,
    estimated_compute_seconds: float = 0.0,
) -> int:
    init_db(db_path)
    now = _utc_now()
    with closing(connect(db_path)) as conn:
        existing = conn.execute(
            """
            SELECT follow_up_id FROM follow_up_registry
            WHERE target_id = ?
              AND candidate_id IS ?
              AND originating_run_id IS ?
            LIMIT 1
            """,
            (target_id, candidate_id, originating_run_id),
        ).fetchone()
        if existing is not None:
            return int(existing["follow_up_id"])
        cur = conn.execute(
            """
            INSERT INTO follow_up_registry(
                target_id, candidate_id, flagged_at, reason, evidence_ref,
                priority, status, recommended_action, originating_run_id,
                required_data, estimated_storage_mb, estimated_compute_seconds,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?)
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
                _non_empty(required_data, "required_data"),
                estimated_storage_mb,
                estimated_compute_seconds,
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
