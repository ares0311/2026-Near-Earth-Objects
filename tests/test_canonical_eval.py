from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from canonical_eval import _compare, evaluate_check, evaluate_suite, load_json


def _suite() -> dict:
    return {
        "schema_version": "canonical-eval-suite-v1",
        "suite_id": "test-suite",
        "cases": [
            {
                "case_id": "known-neo-pass",
                "case_type": "known_neo_recovery",
                "dataset_id": "test:known",
                "observed": {"metrics": {"recovered": 5, "rate": 1.0}},
                "checks": [
                    {"path": "metrics.recovered", "operator": "eq", "expected": 5},
                    {"path": "metrics.rate", "operator": "gte", "expected": 0.9},
                ],
            },
            {
                "case_id": "review-packet-pass",
                "case_type": "review_packet",
                "dataset_id": "test:review",
                "observed": {"decision": "SURVIVE", "challenges": ["orbit", "artifact"]},
                "checks": [
                    {"path": "decision", "operator": "ne", "expected": "REJECT"},
                    {"path": "challenges", "operator": "contains", "expected": "artifact"},
                ],
            },
        ],
    }


def test_evaluate_suite_passes_sample_level_cases() -> None:
    report = evaluate_suite(_suite())

    assert report["passed"] is True
    assert report["n_cases"] == 2
    assert report["n_checks"] == 4
    assert report["failures"] == []


def test_evaluate_suite_reports_failed_check() -> None:
    suite = _suite()
    suite["cases"][0]["checks"][1]["expected"] = 1.1

    report = evaluate_suite(suite)

    assert report["passed"] is False
    assert report["failures"][0]["case_id"] == "known-neo-pass"
    assert report["failures"][0]["path"] == "metrics.rate"


def test_evaluate_suite_loads_observed_path(tmp_path: Path) -> None:
    observed = tmp_path / "observed.json"
    observed.write_text(json.dumps({"nested": [{"score": 0.8}]}))
    suite = {
        "schema_version": "canonical-eval-suite-v1",
        "suite_id": "path-suite",
        "cases": [
            {
                "case_id": "path-case",
                "case_type": "injection_recovery",
                "dataset_id": "test:path",
                "observed_path": "observed.json",
                "checks": [{"path": "nested.0.score", "operator": "lte", "expected": 0.9}],
            }
        ],
    }

    report = evaluate_suite(suite, suite_dir=tmp_path)

    assert report["passed"] is True


def test_missing_path_fails_without_crashing() -> None:
    result = evaluate_check(
        {"a": {}},
        {"path": "a.missing", "operator": "eq", "expected": 1},
    )

    assert result.passed is False
    assert result.message == "missing observed path: a.missing"


def test_missing_list_index_and_non_container_paths_fail_without_crashing() -> None:
    list_result = evaluate_check(
        [{"score": 1}],
        {"path": "bad.score", "operator": "eq", "expected": 1},
    )
    scalar_result = evaluate_check(
        {"a": 1},
        {"path": "a.score", "operator": "eq", "expected": 1},
    )

    assert list_result.passed is False
    assert scalar_result.passed is False


def test_numeric_and_comparison_failure_branches() -> None:
    assert evaluate_check({"score": 2}, {"path": "score", "operator": "gt", "expected": 1}).passed
    assert evaluate_check({"score": 1}, {"path": "score", "operator": "lt", "expected": 2}).passed
    assert not evaluate_check(
        {"score": "nan"},
        {"path": "score", "operator": "gte", "expected": 1},
    ).passed
    result = evaluate_check(
        {"score": 1},
        {"path": "score", "operator": "contains", "expected": "x"},
    )

    assert result.passed is False
    assert result.message.startswith("comparison failed")


def test_check_shape_errors() -> None:
    with pytest.raises(ValueError, match="missing path"):
        evaluate_check({"score": 1}, {"operator": "eq", "expected": 1})
    with pytest.raises(ValueError, match="unsupported canonical eval operator"):
        evaluate_check({"score": 1}, {"path": "score", "operator": "bad", "expected": 1})
    with pytest.raises(ValueError, match="unsupported canonical eval operator"):
        _compare(1, "bad", 1)


@pytest.mark.parametrize(
    ("suite", "message"),
    [
        ({"schema_version": "bad", "suite_id": "x", "cases": [{}]}, "schema_version"),
        ({"schema_version": "canonical-eval-suite-v1", "cases": [{}]}, "suite_id"),
        (
            {"schema_version": "canonical-eval-suite-v1", "suite_id": "x", "cases": []},
            "at least one case",
        ),
        (
            {
                "schema_version": "canonical-eval-suite-v1",
                "suite_id": "x",
                "cases": [{"case_type": "known_neo_recovery", "dataset_id": "d", "checks": [{}]}],
            },
            "case_id",
        ),
        (
            {
                "schema_version": "canonical-eval-suite-v1",
                "suite_id": "x",
                "cases": [{"case_id": "c", "case_type": "bad", "dataset_id": "d", "checks": [{}]}],
            },
            "case_type",
        ),
        (
            {
                "schema_version": "canonical-eval-suite-v1",
                "suite_id": "x",
                "cases": [{"case_id": "c", "case_type": "false_link", "checks": [{}]}],
            },
            "dataset_id",
        ),
        (
            {
                "schema_version": "canonical-eval-suite-v1",
                "suite_id": "x",
                "cases": [
                    {
                        "case_id": "c",
                        "case_type": "false_link",
                        "dataset_id": "d",
                        "checks": {},
                    }
                ],
            },
            "at least one check",
        ),
        (
            {
                "schema_version": "canonical-eval-suite-v1",
                "suite_id": "x",
                "cases": [
                    {"case_id": "c", "case_type": "false_link", "dataset_id": "d", "checks": [{}]}
                ],
            },
            "no observed data",
        ),
    ],
)
def test_invalid_suite_shapes_fail_closed(suite: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        evaluate_suite(suite)


def test_load_json_reports_invalid_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{")

    with pytest.raises(ValueError, match="invalid JSON"):
        load_json(bad)


def test_cli_writes_report_and_fails_on_regression(tmp_path: Path) -> None:
    suite_path = tmp_path / "suite.json"
    suite = _suite()
    suite["cases"][0]["checks"][1]["expected"] = 1.1
    suite_path.write_text(json.dumps(suite))
    out_path = tmp_path / "report.json"

    result = subprocess.run(
        [
            "uv",
            "run",
            "--no-sync",
            "--python",
            "3.14",
            "python",
            "Skills/run_canonical_evals.py",
            str(suite_path),
            "--out",
            str(out_path),
        ],
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src", "UV_CACHE_DIR": ".uv-cache"},
        text=True,
    )

    assert result.returncode == 1
    assert json.loads(out_path.read_text())["passed"] is False
