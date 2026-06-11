#!/usr/bin/env python3
"""Run the approved Tier 3 pilot as one resumable, fail-closed workflow."""

from __future__ import annotations

import argparse
import csv
import fcntl
import importlib.util
import json
import platform
import sqlite3
import subprocess
import sys
import uuid
from collections import Counter
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE = ROOT / "data" / "sequences" / "tier3_pilot_v2"
DEFAULT_DB_PATH = ROOT / "Logs" / "tier3_pilot.sqlite"
DEFAULT_ACTIVE_MARKER = ROOT / "Logs" / "tier3_pilot.active.json"
REQUIRED_PYTHON = "3.14.3"
STAGE_ORDER = ("manifest", "mpc_acquisition", "alerce_acquisition", "prepare_splits")


@dataclass(frozen=True)
class PilotPaths:
    """Hold every operator artifact below one resumable workspace."""

    workspace: Path
    manifest: Path
    mpc: Path
    alerce: Path
    splits: Path

    @classmethod
    def from_workspace(cls, workspace: Path) -> PilotPaths:
        """Build stable artifact paths from the selected workspace."""
        return cls(
            workspace=workspace,
            manifest=workspace / "tier3_pilot_manifest.csv",
            mpc=workspace / "mpc_sequences.json",
            alerce=workspace / "alerce_artifacts.json",
            splits=workspace / "splits",
        )


def _utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(UTC).isoformat()


def _load_skill(filename: str) -> Any:
    """Load one Skill once so a checkout change cannot swap code mid-run."""
    path = ROOT / "Skills" / filename
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load required Skill: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(*args: str) -> str:
    """Run one read-only git inspection command."""
    result = subprocess.run(
        ("git", *args),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _preflight() -> dict[str, str]:
    """Require the pinned interpreter and a clean merged main checkout."""
    version = platform.python_version()
    if version != REQUIRED_PYTHON:
        raise RuntimeError(
            f"Tier 3 pilot requires Python {REQUIRED_PYTHON}; current interpreter is {version}"
        )
    branch = _git("branch", "--show-current")
    if branch != "main":
        raise RuntimeError(f"Tier 3 pilot must run from merged main; current branch is {branch!r}")
    dirty = _git("status", "--porcelain", "--untracked-files=no")
    if dirty:
        raise RuntimeError("tracked files are modified; use a clean merged main checkout")

    # Import both optional clients before any long acquisition begins.
    __import__("astroquery.mpc")
    alerce = __import__("alerce")
    return {
        "branch": branch,
        "commit": _git("rev-parse", "HEAD"),
        "python_version": version,
        "alerce_version": str(getattr(alerce, "__version__", "unknown")),
    }


def _assert_repo_unchanged(expected: dict[str, str]) -> None:
    """Abort if another process switches or edits the shared checkout."""
    branch = _git("branch", "--show-current")
    commit = _git("rev-parse", "HEAD")
    dirty = _git("status", "--porcelain", "--untracked-files=no")
    if branch != expected["branch"] or commit != expected["commit"] or dirty:
        raise RuntimeError(
            "repository state changed during the operator run; "
            "the checkpoint is safe, but this run is stopped"
        )


def _init_db(db_path: Path) -> None:
    """Create the append-only top-level SQLite pilot ledger."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS pilot_runs (
                run_id TEXT PRIMARY KEY,
                started_at_utc TEXT NOT NULL,
                finished_at_utc TEXT,
                status TEXT NOT NULL,
                git_commit TEXT,
                python_version TEXT,
                workspace TEXT NOT NULL,
                failed_stage TEXT,
                error_type TEXT,
                error_message TEXT
            );
            CREATE TABLE IF NOT EXISTS pilot_stage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                started_at_utc TEXT NOT NULL,
                finished_at_utc TEXT,
                status TEXT NOT NULL,
                detail_json TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES pilot_runs(run_id)
            );
            """
        )


def _insert_run(db_path: Path, run_id: str, workspace: Path) -> None:
    """Record a new run before performing preflight or network work."""
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO pilot_runs (
                run_id, started_at_utc, status, workspace
            ) VALUES (?, ?, 'running', ?)
            """,
            (run_id, _utc_now(), str(workspace)),
        )


def _update_run(
    db_path: Path,
    run_id: str,
    *,
    status: str,
    preflight: dict[str, str] | None = None,
    failed_stage: str | None = None,
    error: BaseException | None = None,
) -> None:
    """Finish or enrich one run ledger row without storing sensitive values."""
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            UPDATE pilot_runs
            SET finished_at_utc = ?,
                status = ?,
                git_commit = COALESCE(?, git_commit),
                python_version = COALESCE(?, python_version),
                failed_stage = ?,
                error_type = ?,
                error_message = ?
            WHERE run_id = ?
            """,
            (
                _utc_now() if status != "running" else None,
                status,
                preflight.get("commit") if preflight else None,
                preflight.get("python_version") if preflight else None,
                failed_stage,
                type(error).__name__ if error else None,
                str(error)[:1000] if error else None,
                run_id,
            ),
        )


def _record_stage(
    db_path: Path,
    run_id: str,
    stage: str,
    *,
    started_at: str,
    status: str,
    detail: dict[str, Any],
) -> None:
    """Append one durable stage outcome to SQLite."""
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO pilot_stage_log (
                run_id, stage, started_at_utc, finished_at_utc, status, detail_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                stage,
                started_at,
                _utc_now(),
                status,
                json.dumps(detail, sort_keys=True),
            ),
        )


@contextmanager
def _exclusive_run(marker: Path, run_id: str, workspace: Path) -> Any:
    """Prevent overlapping pilot runs and advertise the shared-checkout boundary."""
    marker.parent.mkdir(parents=True, exist_ok=True)
    with marker.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"another Tier 3 pilot run is active; inspect {marker}") from exc
        handle.seek(0)
        handle.truncate()
        handle.write(
            json.dumps(
                {
                    "run_id": run_id,
                    "started_at_utc": _utc_now(),
                    "workspace": str(workspace),
                    "instruction": "Do not switch branches or edit tracked files.",
                },
                indent=2,
            )
        )
        handle.flush()
        try:
            yield
        finally:
            marker.unlink(missing_ok=True)


def _manifest_counts(path: Path) -> dict[str, int]:
    """Count unique manifest designations by class."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    designations = [str(row.get("designation", "")).strip() for row in rows]
    if not designations or any(not designation for designation in designations):
        raise RuntimeError("manifest contains a blank designation")
    if len(designations) != len(set(designations)):
        raise RuntimeError("manifest contains duplicate designations")
    return dict(sorted(Counter(str(row["neo_class"]) for row in rows).items()))


def _default_stages(
    paths: PilotPaths,
    *,
    candidate_pool_per_class: int,
    target_per_class: int,
    workers: int = 1,
    mpc_query_delay_seconds: float = 1.0,
    alerce_query_delay_seconds: float = 0.5,
) -> dict[str, Callable[[], dict[str, Any]]]:
    """Build the four production pilot stages from modules loaded once."""
    labels = _load_skill("generate_training_labels.py")
    mpc = _load_skill("query_mpc_observations.py")
    alerce = _load_skill("fetch_alerce_artifact_sequences.py")
    preparation = _load_skill("build_sequence_dataset.py")

    def manifest_stage() -> dict[str, Any]:
        """Generate or validate a reserve label pool."""
        if not paths.manifest.exists():
            rows = labels.build_tier3_pilot_manifest(candidate_pool_per_class)
            labels.write_csv(rows, paths.manifest)
        counts = _manifest_counts(paths.manifest)
        expected = {
            "neo_candidate": candidate_pool_per_class,
            "known_object": candidate_pool_per_class,
            "main_belt_asteroid": candidate_pool_per_class,
            "other_solar_system": candidate_pool_per_class,
        }
        if counts != expected:
            raise RuntimeError(
                f"manifest counts do not match the configured reserve pool: {counts}"
            )
        return {"path": str(paths.manifest), "class_counts": counts}

    def mpc_stage() -> dict[str, Any]:
        """Acquire accepted MPC histories from the larger reserve pool."""
        dataset = mpc.collect_sequence_dataset(
            paths.manifest,
            paths.mpc,
            candidate_pool_per_class * 4,
            min_observations=3,
            min_nights=2,
            max_observations_per_object=20,
            retries=2,
            query_delay_seconds=mpc_query_delay_seconds,
            max_consecutive_query_errors=3,
            target_per_class=target_per_class,
            resume=True,
            workers=workers,
        )
        return {"path": str(paths.mpc), **dataset["summary"]}

    def alerce_stage() -> dict[str, Any]:
        """Acquire the public broker artifact class with bounded light queries."""
        dataset = alerce.collect_artifact_sequences(
            paths.alerce,
            target_per_class,
            probability=0.90,
            min_observations=3,
            min_nights=2,
            max_observations_per_object=20,
            query_delay_seconds=alerce_query_delay_seconds,
            request_timeout_seconds=30.0,
            request_attempts=4,
            retry_delay_seconds=5.0,
            candidate_page_size=25,
            max_candidate_pages=40,
            resume=True,
            workers=workers,
        )
        return {"path": str(paths.alerce), **dataset["summary"]}

    def preparation_stage() -> dict[str, Any]:
        """Build splits only after both acquisition contracts pass."""
        report = preparation.prepare_sequence_splits(
            [paths.mpc, paths.alerce],
            paths.splits,
            min_per_class=target_per_class,
        )
        return {
            "path": str(paths.splits / "preparation_report.json"),
            "validation": report["validation"],
            "split_class_counts": report["split_class_counts"],
        }

    return {
        "manifest": manifest_stage,
        "mpc_acquisition": mpc_stage,
        "alerce_acquisition": alerce_stage,
        "prepare_splits": preparation_stage,
    }


def run_pilot(
    workspace: Path,
    db_path: Path,
    *,
    candidate_pool_per_class: int = 100,
    target_per_class: int = 50,
    workers: int = 1,
    mpc_query_delay_seconds: float = 1.0,
    alerce_query_delay_seconds: float = 0.5,
    active_marker: Path = DEFAULT_ACTIVE_MARKER,
    preflight_fn: Callable[[], dict[str, str]] = _preflight,
    guard_fn: Callable[[dict[str, str]], None] = _assert_repo_unchanged,
    stages: dict[str, Callable[[], dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Execute every pilot stage, stopping on the first incomplete contract."""
    if candidate_pool_per_class < target_per_class:
        raise ValueError("candidate_pool_per_class cannot be below target_per_class")
    paths = PilotPaths.from_workspace(workspace)
    paths.workspace.mkdir(parents=True, exist_ok=True)
    _init_db(db_path)
    run_id = str(uuid.uuid4())
    _insert_run(db_path, run_id, workspace)
    preflight: dict[str, str] | None = None
    current_stage = "preflight"

    try:
        with _exclusive_run(active_marker, run_id, workspace):
            preflight = preflight_fn()
            _update_run(db_path, run_id, status="running", preflight=preflight)
            stage_functions = stages or _default_stages(
                paths,
                candidate_pool_per_class=candidate_pool_per_class,
                target_per_class=target_per_class,
                workers=workers,
                mpc_query_delay_seconds=mpc_query_delay_seconds,
                alerce_query_delay_seconds=alerce_query_delay_seconds,
            )
            results: dict[str, Any] = {}
            for stage in STAGE_ORDER:
                current_stage = stage
                guard_fn(preflight)
                started_at = _utc_now()
                try:
                    detail = stage_functions[stage]()
                    guard_fn(preflight)
                except Exception as exc:
                    _record_stage(
                        db_path,
                        run_id,
                        stage,
                        started_at=started_at,
                        status="failed",
                        detail={"error_type": type(exc).__name__, "message": str(exc)[:1000]},
                    )
                    raise
                _record_stage(
                    db_path,
                    run_id,
                    stage,
                    started_at=started_at,
                    status="completed",
                    detail=detail,
                )
                results[stage] = detail
            _update_run(db_path, run_id, status="completed", preflight=preflight)
            return {"run_id": run_id, "status": "completed", "stages": results}
    except Exception as exc:
        _update_run(
            db_path,
            run_id,
            status="failed",
            preflight=preflight,
            failed_stage=current_stage,
            error=exc,
        )
        raise


def latest_status(db_path: Path) -> dict[str, Any]:
    """Return the latest run and its ordered stage outcomes."""
    if not db_path.exists():
        return {"status": "not_started", "db_path": str(db_path)}
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        run = connection.execute(
            "SELECT * FROM pilot_runs ORDER BY started_at_utc DESC LIMIT 1"
        ).fetchone()
        if run is None:
            return {"status": "not_started", "db_path": str(db_path)}
        stages = connection.execute(
            """
            SELECT stage, started_at_utc, finished_at_utc, status, detail_json
            FROM pilot_stage_log
            WHERE run_id = ?
            ORDER BY id
            """,
            (run["run_id"],),
        ).fetchall()
    return {
        **dict(run),
        "stages": [
            {
                "stage": stage["stage"],
                "started_at_utc": stage["started_at_utc"],
                "finished_at_utc": stage["finished_at_utc"],
                "status": stage["status"],
                "detail": json.loads(stage["detail_json"]),
            }
            for stage in stages
        ],
    }


def main() -> int:
    """Parse the one-command operator interface."""
    parser = argparse.ArgumentParser(
        description="Run or inspect the approved fail-closed Tier 3 pilot."
    )
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--candidate-pool-per-class", type=int, default=100)
    parser.add_argument("--target-per-class", type=int, default=50)
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel fetch threads for MPC and ALeRCE acquisition stages (default 1).",
    )
    parser.add_argument(
        "--mpc-query-delay",
        type=float,
        default=1.0,
        dest="mpc_query_delay_seconds",
        help="Seconds between MPC queries per worker (default 1.0; try 0.5 to double throughput).",
    )
    parser.add_argument(
        "--alerce-query-delay",
        type=float,
        default=0.5,
        dest="alerce_query_delay_seconds",
        help="Seconds to wait between ALeRCE queries per worker (default 0.5).",
    )
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(latest_status(args.db), indent=2, sort_keys=True))
        return 0
    try:
        result = run_pilot(
            args.workspace,
            args.db,
            candidate_pool_per_class=args.candidate_pool_per_class,
            target_per_class=args.target_per_class,
            workers=args.workers,
            mpc_query_delay_seconds=args.mpc_query_delay_seconds,
            alerce_query_delay_seconds=args.alerce_query_delay_seconds,
        )
    except Exception as exc:
        print(f"Tier 3 pilot stopped safely: {exc}", file=sys.stderr)
        print(
            "Inspect the checkpoint and SQLite status, then rerun the same command.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
