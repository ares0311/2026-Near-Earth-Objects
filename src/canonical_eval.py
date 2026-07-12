"""Canonical sample-level regression evals for Astrometrics promotion gates."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPPORTED_CASE_TYPES = (
    "known_neo_recovery",
    "false_link",
    "injection_recovery",
    "review_packet",
    # Added 2026-07-12: validates a real, model-specific injection-recovery
    # report (Skills/injection_recovery.py --cnn-model), as opposed to the
    # generic "injection_recovery" type above, whose existing cases all cite
    # pipeline-level artifacts that never invoke any CNN's inference. See
    # docs/evidence/a7/2026-07-12-real-cnn-injection-recovery.md.
    "cnn_injection_recovery",
)
SUPPORTED_OPERATORS = ("eq", "ne", "gte", "lte", "gt", "lt", "contains")


@dataclass(frozen=True)
class CheckResult:
    """One assertion result within a canonical eval case."""

    path: str
    operator: str
    expected: Any
    actual: Any
    passed: bool
    message: str


@dataclass(frozen=True)
class CaseResult:
    """Sample-level canonical eval result."""

    case_id: str
    case_type: str
    dataset_id: str
    passed: bool
    checks: tuple[CheckResult, ...]


def load_json(path: Path) -> Any:
    """Load a JSON document with a concise, typed error on invalid data."""
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def _get_path(payload: Any, path: str) -> Any:
    """Read a dot-separated path from nested dict/list JSON data."""
    current = payload
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(path)
            current = current[part]
        elif isinstance(current, list):
            try:
                index = int(part)
                current = current[index]
            except (ValueError, IndexError) as exc:
                raise KeyError(path) from exc
        else:
            raise KeyError(path)
    return current


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    """Apply one supported comparison operator."""
    if operator == "eq":
        return actual == expected
    if operator == "ne":
        return actual != expected
    if operator == "contains":
        return expected in actual
    if operator in {"gte", "lte", "gt", "lt"}:
        actual_f = float(actual)
        expected_f = float(expected)
        if not math.isfinite(actual_f) or not math.isfinite(expected_f):
            return False
        if operator == "gte":
            return actual_f >= expected_f
        if operator == "lte":
            return actual_f <= expected_f
        if operator == "gt":
            return actual_f > expected_f
        return actual_f < expected_f
    raise ValueError(f"unsupported canonical eval operator: {operator}")


def evaluate_check(payload: Any, check: dict[str, Any]) -> CheckResult:
    """Evaluate one canonical check against one observed payload."""
    path = str(check.get("path", "")).strip()
    operator = str(check.get("operator", "")).strip()
    expected = check.get("expected")
    if not path:
        raise ValueError("canonical eval check missing path")
    if operator not in SUPPORTED_OPERATORS:
        raise ValueError(f"unsupported canonical eval operator: {operator}")

    try:
        actual = _get_path(payload, path)
    except KeyError:
        return CheckResult(
            path=path,
            operator=operator,
            expected=expected,
            actual=None,
            passed=False,
            message=f"missing observed path: {path}",
        )
    try:
        passed = _compare(actual, operator, expected)
    except (TypeError, ValueError) as exc:
        return CheckResult(
            path=path,
            operator=operator,
            expected=expected,
            actual=actual,
            passed=False,
            message=f"comparison failed: {exc}",
        )
    return CheckResult(
        path=path,
        operator=operator,
        expected=expected,
        actual=actual,
        passed=passed,
        message="passed" if passed else f"{actual!r} {operator} {expected!r} failed",
    )


def _case_payload(case: dict[str, Any], suite_dir: Path) -> Any:
    if "observed" in case:
        return case["observed"]
    observed_path = str(case.get("observed_path", "")).strip()
    if not observed_path:
        raise ValueError(f"canonical eval case {case.get('case_id')} has no observed data")
    path = Path(observed_path)
    if not path.is_absolute():
        path = suite_dir / path
    return load_json(path)


def evaluate_case(case: dict[str, Any], *, suite_dir: Path) -> CaseResult:
    """Evaluate one canonical eval case."""
    case_id = str(case.get("case_id", "")).strip()
    case_type = str(case.get("case_type", "")).strip()
    dataset_id = str(case.get("dataset_id", "")).strip()
    checks = case.get("checks", [])
    if not case_id:
        raise ValueError("canonical eval case missing case_id")
    if case_type not in SUPPORTED_CASE_TYPES:
        raise ValueError(f"unsupported canonical eval case_type: {case_type}")
    if not dataset_id:
        raise ValueError(f"canonical eval case {case_id} missing dataset_id")
    if not isinstance(checks, list) or not checks:
        raise ValueError(f"canonical eval case {case_id} must define at least one check")

    payload = _case_payload(case, suite_dir)
    results = tuple(evaluate_check(payload, check) for check in checks)
    return CaseResult(
        case_id=case_id,
        case_type=case_type,
        dataset_id=dataset_id,
        passed=all(result.passed for result in results),
        checks=results,
    )


def evaluate_suite(suite: dict[str, Any], *, suite_dir: Path = Path(".")) -> dict[str, Any]:
    """Evaluate a canonical eval suite and return a JSON-serializable report."""
    if suite.get("schema_version") != "canonical-eval-suite-v1":
        raise ValueError("schema_version must be canonical-eval-suite-v1")
    suite_id = str(suite.get("suite_id", "")).strip()
    cases = suite.get("cases")
    if not suite_id:
        raise ValueError("canonical eval suite missing suite_id")
    if not isinstance(cases, list) or not cases:
        raise ValueError("canonical eval suite must include at least one case")

    case_results = tuple(evaluate_case(case, suite_dir=suite_dir) for case in cases)
    n_checks = sum(len(case.checks) for case in case_results)
    n_passed_checks = sum(
        1 for case in case_results for check in case.checks if check.passed
    )
    failures = [
        {
            "case_id": case.case_id,
            "path": check.path,
            "operator": check.operator,
            "expected": check.expected,
            "actual": check.actual,
            "message": check.message,
        }
        for case in case_results
        for check in case.checks
        if not check.passed
    ]
    return {
        "schema_version": "canonical-eval-report-v1",
        "suite_id": suite_id,
        "passed": not failures,
        "n_cases": len(case_results),
        "n_cases_passed": sum(1 for case in case_results if case.passed),
        "n_checks": n_checks,
        "n_checks_passed": n_passed_checks,
        "case_results": [
            {
                "case_id": case.case_id,
                "case_type": case.case_type,
                "dataset_id": case.dataset_id,
                "passed": case.passed,
                "checks": [
                    {
                        "path": check.path,
                        "operator": check.operator,
                        "expected": check.expected,
                        "actual": check.actual,
                        "passed": check.passed,
                        "message": check.message,
                    }
                    for check in case.checks
                ],
            }
            for case in case_results
        ],
        "failures": failures,
    }
