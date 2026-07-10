"""Tests for A4 production-candidate policy gates in train_tier1_xgboost.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _load_skill():
    path = Path(__file__).resolve().parents[1] / "Skills" / "train_tier1_xgboost.py"
    spec = importlib.util.spec_from_file_location("train_tier1_xgboost", path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _write_report(path: Path, *, passed: bool) -> Path:
    path.write_text(
        json.dumps({
            "schema_version": "grouped-split-leakage-v1",
            "passed": passed,
            "hard_leakage": {},
            "missing_required_splits": [],
        }),
        encoding="utf-8",
    )
    return path


def test_main_production_candidate_requires_passing_grouped_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_skill()
    alerts = tmp_path / "alerts.json"
    alerts.write_text("[]", encoding="utf-8")
    failing = _write_report(tmp_path / "failing.json", passed=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "train_tier1_xgboost.py",
            "--alerts", str(alerts),
            "--mpc-labels", str(tmp_path / "missing_mpc.csv"),
            "--grouped-split-report", str(failing),
            "--production-candidate",
            "--dry-run",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        mod.main()

    assert exc.value.code == 1


def _write_one_alert(path: Path) -> Path:
    path.write_text(json.dumps([{"label": 0, "rb": 0.9, "drb": 0.9}]), encoding="utf-8")
    return path


def test_main_production_candidate_accepts_passing_grouped_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_skill()
    alerts = _write_one_alert(tmp_path / "alerts.json")
    passing = _write_report(tmp_path / "passing.json", passed=True)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "train_tier1_xgboost.py",
            "--alerts", str(alerts),
            "--mpc-labels", str(tmp_path / "missing_mpc.csv"),
            "--synthetic-minor", "0",
            "--grouped-split-report", str(passing),
            "--production-candidate",
            "--dry-run",
        ],
    )

    mod.main()


def test_main_without_production_candidate_ignores_missing_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_skill()
    alerts = _write_one_alert(tmp_path / "alerts.json")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "train_tier1_xgboost.py",
            "--alerts", str(alerts),
            "--mpc-labels", str(tmp_path / "missing_mpc.csv"),
            "--synthetic-minor", "0",
            "--dry-run",
        ],
    )

    mod.main()
