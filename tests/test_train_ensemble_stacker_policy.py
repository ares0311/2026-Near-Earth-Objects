"""Tests for production-candidate policy gates in train_ensemble_stacker.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _load_skill():
    path = Path(__file__).resolve().parents[1] / "Skills" / "train_ensemble_stacker.py"
    spec = importlib.util.spec_from_file_location("train_ensemble_stacker", path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _write_report(path: Path, *, passed: bool, schema: str = "grouped-split-leakage-v1") -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": schema,
                "passed": passed,
                "hard_leakage": {},
                "missing_required_splits": [],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_grouped_split_gate_passes_valid_report(tmp_path: Path) -> None:
    mod = _load_skill()
    report = _write_report(tmp_path / "grouped.json", passed=True)

    gate = mod._load_grouped_split_gate(report)

    assert gate["passed"] is True
    assert gate["blockers"] == []


def test_grouped_split_gate_blocks_missing_invalid_and_failing(tmp_path: Path) -> None:
    mod = _load_skill()
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    failing = _write_report(tmp_path / "failing.json", passed=False)
    wrong_schema = _write_report(tmp_path / "wrong.json", passed=True, schema="wrong")

    assert mod._load_grouped_split_gate(None)["blockers"] == [
        "grouped_split_report_missing"
    ]
    assert mod._load_grouped_split_gate(tmp_path / "missing.json")["blockers"] == [
        "grouped_split_report_missing"
    ]
    assert mod._load_grouped_split_gate(invalid)["blockers"] == [
        "grouped_split_report_invalid_json"
    ]
    assert mod._load_grouped_split_gate(failing)["blockers"] == [
        "grouped_split_report_not_passing"
    ]
    assert mod._load_grouped_split_gate(wrong_schema)["blockers"] == [
        "grouped_split_report_schema_mismatch"
    ]


def test_main_production_candidate_requires_passing_grouped_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_skill()
    alerts = tmp_path / "alerts.json"
    alerts.write_text("[]", encoding="utf-8")
    xgb = tmp_path / "model.json"
    xgb.write_text("{}", encoding="utf-8")
    failing = _write_report(tmp_path / "failing.json", passed=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "train_ensemble_stacker.py",
            "--alerts", str(alerts),
            "--xgb-model", str(xgb),
            "--grouped-split-report", str(failing),
            "--production-candidate",
            "--dry-run",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        mod.main()

    assert exc.value.code == 1


def test_main_production_candidate_accepts_passing_grouped_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_skill()
    alerts = tmp_path / "alerts.json"
    alerts.write_text("[]", encoding="utf-8")
    xgb = tmp_path / "model.json"
    xgb.write_text("{}", encoding="utf-8")
    passing = _write_report(tmp_path / "passing.json", passed=True)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "train_ensemble_stacker.py",
            "--alerts", str(alerts),
            "--xgb-model", str(xgb),
            "--grouped-split-report", str(passing),
            "--production-candidate",
            "--dry-run",
        ],
    )

    mod.main()
