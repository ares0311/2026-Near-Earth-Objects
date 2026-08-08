#!/usr/bin/env python3
"""Phase 6 restart/resume gate over the real Phase 5 durable-state bundle.

The gate refuses fixtures and prose: it requires a passing Phase 5 report whose
steps show an installed real-data process was interrupted after durable progress
and then resumed. It copies that raw state snapshot to an isolated directory,
launches two fresh installed NEOHunter processes outside the repository, proves
state remains readable, and proves an executed manifest cannot run again.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PASS = "PASS"
FAIL = "FAIL"
NOT_EXECUTED = "NOT_EXECUTED"
REPORT_SCHEMA_VERSION = "hunter-restart-resume-gate-1.0.0"


def _run(executable: Path, command: str, state_root: Path, cwd: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.update(
        {
            "NEOHUNTER_HOME": str(state_root),
            "NEOHUNTER_RESOURCE_ROOT": str(REPO_ROOT),
            "NO_COLOR": "1",
        }
    )
    argv = [str(executable), "--no-animation", "--no-color", "--command", command]
    completed = subprocess.run(
        argv, cwd=cwd, env=env, text=True, capture_output=True,
        check=False, timeout=300,
    )
    return {
        "command": argv,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _find_snapshot(report: dict[str, Any]) -> Path | None:
    files = report.get("state_files")
    if not isinstance(files, list) or not files:
        return None
    paths = [REPO_ROOT / str(item.get("path", "")) for item in files if isinstance(item, dict)]
    existing = [path for path in paths if path.is_file()]
    if not existing:
        return None
    common = Path(os.path.commonpath([str(path) for path in existing]))
    while not common.name.startswith("state_snapshot_") and common != REPO_ROOT:
        common = common.parent
    return common if common.name.startswith("state_snapshot_") and common.is_dir() else None


def run_gate(phase5_report: Path) -> dict[str, Any]:
    executable_text = shutil.which("NEOHunter")
    if executable_text is None:
        return {"status": NOT_EXECUTED, "reason": "NEOHunter is not installed on PATH"}
    if not phase5_report.is_file():
        return {"status": NOT_EXECUTED, "reason": f"Phase 5 report is missing: {phase5_report}"}
    try:
        live = json.loads(phase5_report.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": FAIL, "reason": f"Phase 5 report is unreadable: {exc}"}
    if live.get("schema_version") != "hunter-live-acceptance-gate-1.0.0":
        return {"status": FAIL, "reason": "Phase 5 report has the wrong schema"}
    if live.get("status") != PASS:
        return {"status": NOT_EXECUTED, "reason": "Phase 5 real-data gate has not passed"}
    steps = {step.get("label"): step for step in live.get("steps", []) if isinstance(step, dict)}
    interrupted = steps.get("new_interrupted", {})
    resumed = steps.get("new_resumed", {})
    if not interrupted.get("interrupted_after_durable_progress") or resumed.get("exit_code") != 0:
        return {"status": FAIL, "reason": "Phase 5 lacks real interrupted-and-resumed evidence"}
    search_id = str(live.get("new_search_id", "")).strip()
    manifest_sha = str(live.get("new_manifest_sha256", "")).strip()
    if not search_id or len(manifest_sha) != 64:
        return {"status": FAIL, "reason": "Phase 5 lacks exact New manifest identity"}
    snapshot = _find_snapshot(live)
    if snapshot is None:
        return {"status": FAIL, "reason": "Phase 5 raw durable-state snapshot is missing"}

    executable = Path(executable_text).resolve()
    with tempfile.TemporaryDirectory(prefix="neo-restart-gate-") as raw:
        root = Path(raw)
        copied_state = root / "state"
        shutil.copytree(snapshot, copied_state)
        database = copied_state / "data_selection" / "hunter_state.sqlite"
        if not database.is_file():
            return {"status": FAIL, "reason": "snapshot lacks hunter_state.sqlite"}
        with sqlite3.connect(database) as conn:
            row = conn.execute(
                "SELECT status FROM search_manifests WHERE search_id=?", (search_id,)
            ).fetchone()
            ids = [
                item[0]
                for item in conn.execute(
                    "SELECT target_id FROM search_manifest_targets WHERE search_id=? ORDER BY rank",
                    (search_id,),
                ).fetchall()
            ]
        first = _run(executable, "/Show-Follow-Ups all", copied_state, root)
        second = _run(executable, f"/Run-Search {search_id}", copied_state, root)
        with sqlite3.connect(database) as conn:
            final_ids = [
                item[0]
                for item in conn.execute(
                    "SELECT target_id FROM search_manifest_targets WHERE search_id=? ORDER BY rank",
                    (search_id,),
                ).fetchall()
            ]

    passed = row is not None and row[0] == "executed" and first["exit_code"] == 0
    passed = passed and second["exit_code"] != 0 and final_ids == ids and len(ids) == 5
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "gate": "phase-6-restart-resume",
        "status": PASS if passed else FAIL,
        "reason": (
            "two fresh processes read durable state; completed exact manifest was not repeated"
            if passed else "fresh-process state read or no-repeat assertion failed"
        ),
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "code_identity": head,
        "phase5_report": str(phase5_report),
        "search_id": search_id,
        "manifest_sha256": manifest_sha,
        "first_process": first,
        "second_process": second,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase5-report", type=Path,
        default=REPO_ROOT / "Logs/prod_closure/phase5_live_evidence/report.json",
    )
    parser.add_argument(
        "--json", type=Path,
        default=REPO_ROOT / "Logs/prod_closure/restart_resume_report.json",
    )
    args = parser.parse_args(argv)
    report = run_gate(args.phase5_report)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{report['status']}: {report.get('reason', '')}")
    print(f"report written to {args.json}")
    return 0 if report["status"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
