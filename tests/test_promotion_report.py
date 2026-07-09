"""Tests for fail-closed model promotion reports."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from promotion_report import PromotionInputs, build_promotion_report


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _manifest(dataset_id: str = "manifest:test") -> dict[str, object]:
    return {
        "dataset_id": dataset_id,
        "project": "2026 Near Earth Objects",
        "role": "frozen_eval",
        "source_name": "synthetic fixture",
        "source_url": "local-fixture",
        "instrument": "fixture",
        "target_ids": ["fixture-target"],
        "time_range": {"start": "2450000.5", "end": "2450001.5", "scale": "JD"},
        "cadence": "synthetic",
        "band_or_frequency": "synthetic",
        "data_product_type": "json",
        "downloaded_at": "2026-07-09T00:00:00Z",
        "local_path": "tests/fixtures",
        "checksum": {"algorithm": "none", "value": "not-applicable"},
        "license": "test-fixture",
        "label_source": "unit-test",
        "label_confidence": "synthetic",
        "preprocessing_version": "test",
        "known_caveats": ["unit-test fixture"],
    }


def _inputs(tmp_path: Path, **overrides: object) -> PromotionInputs:
    manifest = _write_json(tmp_path / "manifest.json", _manifest())
    grouped = _write_json(
        tmp_path / "grouped.json",
        {"schema_version": "grouped-split-leakage-v1", "passed": True},
    )
    canonical = _write_json(
        tmp_path / "canonical.json",
        {"schema_version": "canonical-eval-report-v1", "passed": True},
    )
    recovery = _write_json(
        tmp_path / "recovery.json",
        {"schema_version": "injection-recovery-curves-v1", "passed": True},
    )
    calibration = _write_json(
        tmp_path / "calibration.json",
        {"promotion_gate_passed": True, "thresholds": {}, "tiers": [{"all_kpis_pass": True}]},
    )
    fdr = _write_json(tmp_path / "fdr.json", {"false_discovery_rate": 0.01})
    audit = tmp_path / "audit.md"
    audit.write_text("Pretrained model audit: no pretrained weights promoted.", encoding="utf-8")
    model_card = tmp_path / "MODEL_CARD.md"
    model_card.write_text("Benchmark model card.", encoding="utf-8")
    values: dict[str, object] = {
        "model_id": "benchmark_cnn_v1",
        "model_type": "tier2_cnn",
        "model_version": "0.90.66",
        "dataset_manifests": (manifest,),
        "grouped_split_report": grouped,
        "canonical_eval_report": canonical,
        "injection_recovery_report": recovery,
        "calibration_report": calibration,
        "false_discovery_report": fdr,
        "pretrained_audit": audit,
        "benchmark_model_card": model_card,
        "operator_signoff_id": "internal-model-promotion-fixture",
        "max_false_discovery_rate": 0.05,
    }
    values.update(overrides)
    return PromotionInputs(**values)  # type: ignore[arg-type]


def test_build_promotion_report_allows_when_all_evidence_passes(tmp_path: Path) -> None:
    report = build_promotion_report(_inputs(tmp_path))

    assert report["schema_version"] == "model-promotion-report-v1"
    assert report["promotion_allowed"] is True
    assert report["promotion_blockers"] == []
    assert report["safety"]["mpc_submission_authorized"] is False
    assert {item["name"] for item in report["evidence"]} == {
        "dataset_manifest",
        "grouped_split_report",
        "canonical_eval_report",
        "injection_recovery_report",
        "calibration_report",
        "false_discovery_report",
        "pretrained_audit",
        "benchmark_model_card",
    }


def test_build_promotion_report_blocks_missing_and_failing_evidence(tmp_path: Path) -> None:
    canonical = _write_json(
        tmp_path / "bad-canonical.json",
        {"schema_version": "wrong", "passed": False},
    )
    recovery = _write_json(
        tmp_path / "bad-recovery.json",
        {"schema_version": "injection-recovery-curves-v1", "passed": False},
    )
    calibration = _write_json(
        tmp_path / "bad-calibration.json",
        {"promotion_gate_passed": False},
    )
    fdr = _write_json(tmp_path / "bad-fdr.json", {"false_discovery_rate": 0.2})
    audit = tmp_path / "empty-audit.md"
    audit.write_text("", encoding="utf-8")
    report = build_promotion_report(
        _inputs(
            tmp_path,
            dataset_manifests=(),
            grouped_split_report=tmp_path / "missing-grouped.json",
            canonical_eval_report=canonical,
            injection_recovery_report=recovery,
            calibration_report=calibration,
            false_discovery_report=fdr,
            pretrained_audit=audit,
            benchmark_model_card=tmp_path / "missing-card.md",
            operator_signoff_id=None,
        )
    )

    assert report["promotion_allowed"] is False
    blockers = set(report["promotion_blockers"])
    assert {
        "dataset_manifest_missing",
        "grouped_split_report_missing",
        "canonical_eval_report_schema_mismatch",
        "canonical_eval_report_not_passing",
        "injection_recovery_report_not_passing",
        "calibration_gate_not_passed",
        "calibration_thresholds_missing",
        "calibration_tiers_missing",
        "false_discovery_rate_above_limit",
        "pretrained_audit_empty",
        "benchmark_model_card_missing",
        "operator_signoff_missing",
    }.issubset(blockers)


def test_manifest_validation_blocks_invalid_json_root_and_metadata(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    wrong_root = _write_json(tmp_path / "wrong-root.json", [])
    wrong_project = _write_json(
        tmp_path / "wrong-project.json",
        {"dataset_id": "bad", "project": "Other"},
    )

    report = build_promotion_report(
        _inputs(
            tmp_path,
            dataset_manifests=(invalid, wrong_root, wrong_project),
        )
    )

    blockers = report["promotion_blockers"]
    assert "dataset_manifest_invalid_json" in blockers
    assert blockers.count("dataset_manifest_invalid_json") == 2
    assert "dataset_manifest_missing_required_fields" in blockers
    assert "dataset_manifest_wrong_project" in blockers


def test_false_discovery_report_blocks_missing_numeric_rate(tmp_path: Path) -> None:
    fdr = _write_json(tmp_path / "bad-fdr.json", {"false_discovery_rate": "unknown"})
    report = build_promotion_report(_inputs(tmp_path, false_discovery_report=fdr))

    assert report["promotion_allowed"] is False
    assert "false_discovery_rate_missing" in report["promotion_blockers"]


def test_missing_calibration_and_false_discovery_reports_block(tmp_path: Path) -> None:
    report = build_promotion_report(
        _inputs(
            tmp_path,
            calibration_report=tmp_path / "missing-calibration.json",
            false_discovery_report=tmp_path / "missing-fdr.json",
        )
    )

    assert "calibration_report_missing" in report["promotion_blockers"]
    assert "false_discovery_report_missing" in report["promotion_blockers"]


def test_cli_writes_report_and_returns_failure_for_blockers(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path, operator_signoff_id=None)
    out = tmp_path / "promotion.json"
    cmd = [
        sys.executable,
        "Skills/build_promotion_report.py",
        "--model-id",
        inputs.model_id,
        "--model-type",
        inputs.model_type,
        "--model-version",
        inputs.model_version,
        "--dataset-manifest",
        str(inputs.dataset_manifests[0]),
        "--grouped-split-report",
        str(inputs.grouped_split_report),
        "--canonical-eval-report",
        str(inputs.canonical_eval_report),
        "--injection-recovery-report",
        str(inputs.injection_recovery_report),
        "--calibration-report",
        str(inputs.calibration_report),
        "--false-discovery-report",
        str(inputs.false_discovery_report),
        "--pretrained-audit",
        str(inputs.pretrained_audit),
        "--benchmark-model-card",
        str(inputs.benchmark_model_card),
        "--out",
        str(out),
    ]
    result = subprocess.run(cmd, check=False, text=True, capture_output=True)

    assert result.returncode == 1
    assert "promotion_allowed=false" in result.stdout
    assert json.loads(out.read_text(encoding="utf-8"))["promotion_blockers"] == [
        "operator_signoff_missing"
    ]
