#!/usr/bin/env python3
"""Phase 5 gate: installed real-data New and Follow-up acceptance.

This gate launches the resolved installed ``NEOHunter`` executable from outside
the repository with ``PYTHONPATH`` removed. It uses a repository-owned isolated
state root, real authoritative sources, exact five-target manifests, a deliberate
process interruption after durable target progress, restart/resume, and a final
fresh-process no-repeat check. It never submits externally.

The command is intentionally live and potentially long-running. A missing
executable or active Tier 3 operator marker is NOT_EXECUTED; an executed product
failure is FAIL. Raw stdout, stderr, environment identity, SQLite state, manifests,
checkpoints, and hashes are retained below the requested evidence directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_SCHEMA_VERSION = "hunter-live-acceptance-gate-1.0.0"
PASS = "PASS"
FAIL = "FAIL"
NOT_EXECUTED = "NOT_EXECUTED"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run(
    executable: Path,
    command: str,
    *,
    env: dict[str, str],
    cwd: Path,
    evidence_dir: Path,
    label: str,
    timeout: int = 7200,
) -> dict[str, Any]:
    argv = [str(executable), "--no-animation", "--no-color", "--command", command]
    completed = subprocess.run(
        argv, cwd=cwd, env=env, text=True, capture_output=True,
        check=False, timeout=timeout,
    )
    stdout_path = evidence_dir / f"{label}.stdout.txt"
    stderr_path = evidence_dir / f"{label}.stderr.txt"
    stdout_path.write_text(completed.stdout)
    stderr_path.write_text(completed.stderr)
    return {
        "label": label,
        "command": argv,
        "exit_code": completed.returncode,
        "stdout_path": str(stdout_path.relative_to(REPO_ROOT)),
        "stderr_path": str(stderr_path.relative_to(REPO_ROOT)),
        "stdout_sha256": _sha256(stdout_path),
        "stderr_sha256": _sha256(stderr_path),
    }


def _latest_manifest(database: Path, mode: str) -> dict[str, Any] | None:
    if not database.is_file():
        return None
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM search_manifests WHERE mode=? ORDER BY created_at DESC LIMIT 1",
            (mode,),
        ).fetchone()
        if row is None:
            return None
        targets = conn.execute(
            "SELECT * FROM search_manifest_targets WHERE search_id=? ORDER BY rank",
            (row["search_id"],),
        ).fetchall()
    return {**dict(row), "targets": [dict(target) for target in targets]}


def _durable_target_count(database: Path, search_id: str) -> int:
    if not database.is_file():
        return 0
    with sqlite3.connect(database) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM search_run_targets rt
            JOIN search_runs r ON r.run_id=rt.run_id
            WHERE r.search_id=?
            """,
            (search_id,),
        ).fetchone()
    return int(row[0]) if row else 0


def _interrupt_after_progress(
    executable: Path,
    search_id: str,
    database: Path,
    *,
    env: dict[str, str],
    cwd: Path,
    evidence_dir: Path,
    timeout: int,
) -> dict[str, Any]:
    command = f"/Run-Search {search_id}"
    argv = [str(executable), "--no-animation", "--no-color", "--command", command]
    process = subprocess.Popen(
        argv, cwd=cwd, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + timeout
    interrupted = False
    while process.poll() is None and time.monotonic() < deadline:
        if _durable_target_count(database, search_id) >= 1:
            process.terminate()
            interrupted = True
            break
        time.sleep(0.25)
    if process.poll() is None and not interrupted:
        process.kill()
    stdout, stderr = process.communicate(timeout=30)
    stdout_path = evidence_dir / "new_interrupted.stdout.txt"
    stderr_path = evidence_dir / "new_interrupted.stderr.txt"
    stdout_path.write_text(stdout)
    stderr_path.write_text(stderr)
    return {
        "label": "new_interrupted",
        "command": argv,
        "exit_code": process.returncode,
        "interrupted_after_durable_progress": interrupted,
        "durable_targets_before_restart": _durable_target_count(database, search_id),
        "stdout_path": str(stdout_path.relative_to(REPO_ROOT)),
        "stderr_path": str(stderr_path.relative_to(REPO_ROOT)),
        "stdout_sha256": _sha256(stdout_path),
        "stderr_sha256": _sha256(stderr_path),
    }


def _snapshot_files(root: Path, evidence_dir: Path) -> list[dict[str, Any]]:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    snapshot = evidence_dir / f"state_snapshot_{stamp}"
    shutil.copytree(root, snapshot)
    records = []
    for path in sorted(snapshot.rglob("*")):
        if path.is_file():
            records.append(
                {
                    "path": str(path.relative_to(REPO_ROOT)),
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
    return records


def execute_gate(args: argparse.Namespace) -> dict[str, Any]:
    marker = REPO_ROOT / "Logs" / "tier3_pilot.active.json"
    if marker.exists():
        return {"status": NOT_EXECUTED, "reason": f"active operator marker: {marker}"}
    executable_text = shutil.which("NEOHunter")
    if executable_text is None:
        return {"status": NOT_EXECUTED, "reason": "NEOHunter is not installed on PATH"}
    executable = Path(executable_text).resolve()
    evidence_dir = args.evidence_dir.resolve()
    state_root = args.state_root.resolve()
    try:
        evidence_dir.relative_to(REPO_ROOT)
        state_root.relative_to(REPO_ROOT)
    except ValueError:
        return {
            "status": NOT_EXECUTED,
            "reason": "state and evidence directories must be repository-owned",
        }
    if (
        state_root == evidence_dir
        or state_root.is_relative_to(evidence_dir)
        or evidence_dir.is_relative_to(state_root)
    ):
        return {
            "status": NOT_EXECUTED,
            "reason": "state and evidence directories must be disjoint",
        }
    if state_root.exists() and any(state_root.iterdir()):
        return {
            "status": NOT_EXECUTED,
            "reason": f"refusing to mutate non-empty state directory: {state_root}",
        }
    if evidence_dir.exists() and any(evidence_dir.iterdir()):
        return {
            "status": NOT_EXECUTED,
            "reason": f"refusing to overwrite non-empty evidence directory: {evidence_dir}",
        }
    evidence_dir.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)
    database = state_root / "data_selection" / "hunter_state.sqlite"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.update(
        {
            "NEOHUNTER_HOME": str(state_root),
            "NEOHUNTER_RESOURCE_ROOT": str(REPO_ROOT),
            "NO_COLOR": "1",
        }
    )
    steps: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="neo-live-gate-") as raw_cwd:
        cwd = Path(raw_cwd)
        create_new = _run(
            executable, "/New-Search 5", env=env, cwd=cwd,
            evidence_dir=evidence_dir, label="new_create",
        )
        steps.append(create_new)
        if create_new["exit_code"] != 0:
            return _finish(FAIL, "real New manifest creation failed", steps, args, executable)
        new_manifest = _latest_manifest(database, "new")
        if new_manifest is None or len(new_manifest["targets"]) != 5:
            return _finish(FAIL, "New did not freeze exactly five targets", steps, args, executable)
        if len(str(new_manifest.get("manifest_sha256", ""))) != 64:
            return _finish(
                FAIL,
                "New manifest lacks a persisted SHA-256 identity",
                steps,
                args,
                executable,
            )
        new_ids = [row["target_id"] for row in new_manifest["targets"]]
        interrupted = _interrupt_after_progress(
            executable, new_manifest["search_id"], database, env=env, cwd=cwd,
            evidence_dir=evidence_dir, timeout=args.interrupt_timeout,
        )
        steps.append(interrupted)
        if not interrupted["interrupted_after_durable_progress"]:
            return _finish(
                FAIL,
                "could not establish interrupted durable New work",
                steps,
                args,
                executable,
            )
        resumed = _run(
            executable, f"/Run-Search {new_manifest['search_id']}", env=env, cwd=cwd,
            evidence_dir=evidence_dir, label="new_resumed",
        )
        steps.append(resumed)
        if resumed["exit_code"] != 0:
            return _finish(FAIL, "New resume failed", steps, args, executable)

        create_followup = _run(
            executable, "/Follow-Up-Search 5", env=env, cwd=cwd,
            evidence_dir=evidence_dir, label="followup_create",
        )
        steps.append(create_followup)
        if create_followup["exit_code"] != 0:
            return _finish(FAIL, "real Follow-up manifest creation failed", steps, args, executable)
        followup_manifest = _latest_manifest(database, "follow-up")
        if followup_manifest is None or len(followup_manifest["targets"]) != 5:
            return _finish(
                FAIL,
                "Follow-up did not freeze exactly five targets",
                steps,
                args,
                executable,
            )
        if len(str(followup_manifest.get("manifest_sha256", ""))) != 64:
            return _finish(
                FAIL,
                "Follow-up manifest lacks a persisted SHA-256 identity",
                steps,
                args,
                executable,
            )
        followup_run = _run(
            executable, f"/Run-Search {followup_manifest['search_id']}", env=env, cwd=cwd,
            evidence_dir=evidence_dir, label="followup_run",
        )
        steps.append(followup_run)
        if followup_run["exit_code"] != 0:
            return _finish(FAIL, "Follow-up execution failed", steps, args, executable)

        restart = _run(
            executable, "/Show-Follow-Ups all", env=env, cwd=cwd,
            evidence_dir=evidence_dir, label="restart_show_followups",
        )
        steps.append(restart)
        repeat = _run(
            executable, f"/Run-Search {new_manifest['search_id']}", env=env, cwd=cwd,
            evidence_dir=evidence_dir, label="restart_no_repeat",
        )
        steps.append(repeat)
        exit_step = _run(
            executable, "/Exit", env=env, cwd=cwd,
            evidence_dir=evidence_dir, label="exit",
        )
        steps.append(exit_step)

    final_new = _latest_manifest(database, "new")
    final_ids = [row["target_id"] for row in (final_new or {}).get("targets", [])]
    passed = (
        restart["exit_code"] == 0
        and repeat["exit_code"] != 0
        and exit_step["exit_code"] == 0
        and final_ids == new_ids
        and final_new is not None
        and final_new["manifest_sha256"] == new_manifest["manifest_sha256"]
    )
    files = _snapshot_files(state_root, evidence_dir)
    result = _finish(
        PASS if passed else FAIL,
        "installed real New/Follow-up, interruption, restart, and no-repeat complete"
        if passed else "restart changed the manifest or repeated completed work",
        steps,
        args,
        executable,
    )
    result["new_search_id"] = new_manifest["search_id"]
    result["new_manifest_sha256"] = new_manifest["manifest_sha256"]
    result["followup_search_id"] = followup_manifest["search_id"]
    result["followup_manifest_sha256"] = followup_manifest["manifest_sha256"]
    result["state_files"] = files
    return result


def _finish(
    status: str,
    reason: str,
    steps: list[dict[str, Any]],
    args: argparse.Namespace,
    executable: Path,
) -> dict[str, Any]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "gate": "phase-5-real-data-new-and-follow-up",
        "status": status,
        "reason": reason,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "code_identity": head,
        "environment": {
            "platform": platform.platform(),
            "python": sys.version,
            "executable": str(executable),
            "state_root": str(args.state_root.resolve()),
            "working_tree_dirty": bool(
                subprocess.run(
                    ["git", "status", "--porcelain"], cwd=REPO_ROOT,
                    capture_output=True, text=True, check=False,
                ).stdout.strip()
            ),
        },
        "steps": steps,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-root", type=Path,
        default=None,
    )
    parser.add_argument(
        "--evidence-dir", type=Path,
        default=None,
    )
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--interrupt-timeout", type=int, default=7200)
    args = parser.parse_args(argv)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    if args.state_root is None:
        args.state_root = REPO_ROOT / "Logs" / "prod_closure" / f"phase5_live_state_{stamp}"
    if args.evidence_dir is None:
        args.evidence_dir = (
            REPO_ROOT / "Logs" / "prod_closure" / f"phase5_live_evidence_{stamp}"
        )
    output = (args.json or (args.evidence_dir / "report.json")).resolve()
    try:
        output.relative_to(REPO_ROOT)
    except ValueError:
        print(f"{NOT_EXECUTED}: report path must be repository-owned: {output}")
        return 1
    report = execute_gate(args)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{report['status']}: {report.get('reason', '')}")
    print(f"report written to {output}")
    return 0 if report["status"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
