"""Fail-closed model promotion report assembly.

The Astrometrics A7 gate is intentionally evidence-centric: a model is not
production-promoted because one metric looks good. Promotion requires a compact
packet that cites every upstream control artifact and records exactly which
missing or failing item blocks the decision.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_MANIFEST_FIELDS = {
    "dataset_id",
    "project",
    "role",
    "source_name",
    "source_url",
    "instrument",
    "target_ids",
    "time_range",
    "cadence",
    "band_or_frequency",
    "data_product_type",
    "downloaded_at",
    "local_path",
    "checksum",
    "license",
    "label_source",
    "label_confidence",
    "preprocessing_version",
    "known_caveats",
}
PROJECT = "2026 Near Earth Objects"


@dataclass(frozen=True)
class PromotionInputs:
    """Input artifact paths and operator context for one promotion report."""

    model_id: str
    model_type: str
    model_version: str
    dataset_manifests: tuple[Path, ...]
    grouped_split_report: Path
    canonical_eval_report: Path
    injection_recovery_report: Path
    calibration_report: Path
    false_discovery_report: Path
    pretrained_audit: Path
    benchmark_model_card: Path
    operator_signoff_id: str | None = None
    max_false_discovery_rate: float = 0.05


def _load_json(path: Path) -> dict[str, Any]:
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(decoded, dict):
        raise ValueError(f"expected JSON object in {path}")
    return decoded


def _check(
    name: str,
    path: Path | None,
    passed: bool,
    blockers: list[str],
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "path": str(path) if path is not None else None,
        "passed": passed,
        "blockers": blockers,
        "details": details or {},
    }


def _json_presence_check(name: str, path: Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not path.exists():
        return None, _check(name, path, False, [f"{name}_missing"])
    try:
        payload = _load_json(path)
    except ValueError as exc:
        return None, _check(name, path, False, [f"{name}_invalid_json"], {"error": str(exc)})
    return payload, _check(name, path, True, [], {"keys": sorted(payload)})


def _dataset_manifest_check(path: Path) -> dict[str, Any]:
    payload, base = _json_presence_check("dataset_manifest", path)
    if payload is None:
        return base

    blockers: list[str] = []
    missing = sorted(REQUIRED_MANIFEST_FIELDS.difference(payload))
    if missing:
        blockers.append("dataset_manifest_missing_required_fields")
    if payload.get("project") != PROJECT:
        blockers.append("dataset_manifest_wrong_project")
    details = {
        "dataset_id": payload.get("dataset_id"),
        "role": payload.get("role"),
        "missing_fields": missing,
    }
    return _check("dataset_manifest", path, not blockers, blockers, details)


def _schema_pass_check(
    name: str,
    path: Path,
    *,
    expected_schema: str,
    pass_key: str = "passed",
) -> dict[str, Any]:
    payload, base = _json_presence_check(name, path)
    if payload is None:
        return base

    blockers: list[str] = []
    if payload.get("schema_version") != expected_schema:
        blockers.append(f"{name}_schema_mismatch")
    if payload.get(pass_key) is not True:
        blockers.append(f"{name}_not_passing")
    return _check(
        name,
        path,
        not blockers,
        blockers,
        {
            "schema_version": payload.get("schema_version"),
            pass_key: payload.get(pass_key),
        },
    )


def _calibration_check(path: Path) -> dict[str, Any]:
    payload, base = _json_presence_check("calibration_report", path)
    if payload is None:
        return base

    blockers: list[str] = []
    if payload.get("promotion_gate_passed") is not True:
        blockers.append("calibration_gate_not_passed")
    if "thresholds" not in payload:
        blockers.append("calibration_thresholds_missing")
    if "tiers" not in payload:
        blockers.append("calibration_tiers_missing")
    return _check(
        "calibration_report",
        path,
        not blockers,
        blockers,
        {
            "promotion_gate_passed": payload.get("promotion_gate_passed"),
            "tier_count": (
                len(payload.get("tiers", [])) if isinstance(payload.get("tiers"), list) else 0
            ),
        },
    )


def _false_discovery_check(path: Path, max_rate: float) -> dict[str, Any]:
    payload, base = _json_presence_check("false_discovery_report", path)
    if payload is None:
        return base

    blockers: list[str] = []
    rate = payload.get("false_discovery_rate", payload.get("fdr"))
    try:
        rate_f = float(rate)
    except (TypeError, ValueError):
        rate_f = None
        blockers.append("false_discovery_rate_missing")
    if rate_f is not None and rate_f > max_rate:
        blockers.append("false_discovery_rate_above_limit")
    return _check(
        "false_discovery_report",
        path,
        not blockers,
        blockers,
        {"false_discovery_rate": rate_f, "max_false_discovery_rate": max_rate},
    )


def _text_file_check(name: str, path: Path) -> dict[str, Any]:
    if not path.exists():
        return _check(name, path, False, [f"{name}_missing"])
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return _check(name, path, False, [f"{name}_empty"])
    return _check(name, path, True, [], {"n_chars": len(text)})


def build_promotion_report(inputs: PromotionInputs) -> dict[str, Any]:
    """Build a fail-closed promotion report from local evidence artifacts."""
    evidence: list[dict[str, Any]] = [
        _dataset_manifest_check(path) for path in inputs.dataset_manifests
    ]
    if not inputs.dataset_manifests:
        evidence.append(_check("dataset_manifest", None, False, ["dataset_manifest_missing"]))

    evidence.extend(
        [
            _schema_pass_check(
                "grouped_split_report",
                inputs.grouped_split_report,
                expected_schema="grouped-split-leakage-v1",
            ),
            _schema_pass_check(
                "canonical_eval_report",
                inputs.canonical_eval_report,
                expected_schema="canonical-eval-report-v1",
            ),
            _schema_pass_check(
                "injection_recovery_report",
                inputs.injection_recovery_report,
                expected_schema="injection-recovery-curves-v1",
            ),
            _calibration_check(inputs.calibration_report),
            _false_discovery_check(
                inputs.false_discovery_report,
                inputs.max_false_discovery_rate,
            ),
            _text_file_check("pretrained_audit", inputs.pretrained_audit),
            _text_file_check("benchmark_model_card", inputs.benchmark_model_card),
        ]
    )

    blockers = [
        blocker
        for check in evidence
        for blocker in check["blockers"]
    ]
    if not inputs.operator_signoff_id:
        blockers.append("operator_signoff_missing")

    return {
        "schema_version": "model-promotion-report-v1",
        "model": {
            "model_id": inputs.model_id,
            "model_type": inputs.model_type,
            "model_version": inputs.model_version,
        },
        "safety": {
            "no_external_submission": True,
            "no_impact_probability_claim": True,
            "mpc_submission_authorized": False,
        },
        "operator_signoff_id": inputs.operator_signoff_id,
        "promotion_allowed": not blockers,
        "promotion_blockers": blockers,
        "evidence": evidence,
        "limitations": [
            "This report authorizes only internal model promotion when all evidence passes.",
            "It does not authorize MPC submission, NASA/PDCO contact, "
            "or impact-probability claims.",
        ],
    }
