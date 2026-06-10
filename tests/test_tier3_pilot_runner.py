"""Offline tests for the atomic Tier 3 operator workflow."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest


def _load_runner() -> Any:
    """Load the operator Skill directly."""
    path = Path(__file__).resolve().parents[1] / "Skills" / "run_tier3_pilot.py"
    spec = importlib.util.spec_from_file_location("tier3_pilot_runner", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _preflight() -> dict[str, str]:
    """Return a deterministic merged-main snapshot for offline tests."""
    return {
        "branch": "main",
        "commit": "abc123",
        "python_version": "3.14.3",
        "alerce_version": "2.3.0",
    }


def test_runner_completes_all_stages_and_records_sqlite(tmp_path: Path) -> None:
    """A successful run should produce one ordered, auditable ledger."""
    module = _load_runner()
    calls: list[str] = []
    stages = {
        stage: (lambda stage=stage: calls.append(stage) or {"stage": stage})
        for stage in module.STAGE_ORDER
    }
    db_path = tmp_path / "Logs" / "tier3.sqlite"
    marker = tmp_path / "Logs" / "active.json"

    result = module.run_pilot(
        tmp_path / "workspace",
        db_path,
        active_marker=marker,
        preflight_fn=_preflight,
        guard_fn=lambda expected: None,
        stages=stages,
    )

    assert result["status"] == "completed"
    assert calls == list(module.STAGE_ORDER)
    assert marker.exists() is False
    status = module.latest_status(db_path)
    assert status["status"] == "completed"
    assert [stage["status"] for stage in status["stages"]] == ["completed"] * 4


def test_runner_stops_after_first_failed_stage(tmp_path: Path) -> None:
    """Later stages must never execute after an incomplete acquisition."""
    module = _load_runner()
    calls: list[str] = []

    def fail_mpc() -> dict[str, Any]:
        """Simulate a transient provider failure after manifest creation."""
        calls.append("mpc_acquisition")
        raise TimeoutError("provider timeout")

    stages = {
        "manifest": lambda: calls.append("manifest") or {"ok": True},
        "mpc_acquisition": fail_mpc,
        "alerce_acquisition": lambda: calls.append("alerce_acquisition") or {},
        "prepare_splits": lambda: calls.append("prepare_splits") or {},
    }
    db_path = tmp_path / "Logs" / "tier3.sqlite"

    with pytest.raises(TimeoutError, match="provider timeout"):
        module.run_pilot(
            tmp_path / "workspace",
            db_path,
            active_marker=tmp_path / "Logs" / "active.json",
            preflight_fn=_preflight,
            guard_fn=lambda expected: None,
            stages=stages,
        )

    assert calls == ["manifest", "mpc_acquisition"]
    status = module.latest_status(db_path)
    assert status["status"] == "failed"
    assert status["failed_stage"] == "mpc_acquisition"
    assert status["stages"][-1]["status"] == "failed"


def test_runner_rejects_candidate_pool_below_target(tmp_path: Path) -> None:
    """The reserve pool must be large enough to replace rejected candidates."""
    module = _load_runner()

    with pytest.raises(ValueError, match="candidate_pool_per_class"):
        module.run_pilot(
            tmp_path / "workspace",
            tmp_path / "tier3.sqlite",
            candidate_pool_per_class=49,
            target_per_class=50,
        )


def test_latest_status_handles_missing_database(tmp_path: Path) -> None:
    """Status inspection should be useful before the first run."""
    module = _load_runner()

    assert module.latest_status(tmp_path / "missing.sqlite")["status"] == "not_started"
