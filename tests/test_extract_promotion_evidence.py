"""Tests for Skills/extract_promotion_evidence.py.

Verifies the two pure extraction/derivation functions against synthetic
fixtures shaped exactly like the real committed evidence files
(`data/injection_recovery_image_level_n200.json` and
`Logs/reports/ranking_baseline.json`), plus the CLI wiring.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Skills"))

_MODULE_PATH = Path(__file__).resolve().parents[1] / "Skills" / "extract_promotion_evidence.py"
_spec = importlib.util.spec_from_file_location("extract_promotion_evidence", _MODULE_PATH)
extract_promotion_evidence = importlib.util.module_from_spec(_spec)
sys.modules["extract_promotion_evidence"] = extract_promotion_evidence
_spec.loader.exec_module(extract_promotion_evidence)


def test_extract_injection_recovery_report_lifts_nested_object(tmp_path):
    source = tmp_path / "injection_recovery.json"
    source.write_text(
        json.dumps(
            {
                "n_injected": 200,
                "recovery_curves": {
                    "schema_version": "injection-recovery-curves-v1",
                    "passed": True,
                    "curves": {"magnitude": []},
                },
            }
        )
    )
    report = extract_promotion_evidence.extract_injection_recovery_report(source)
    assert report["schema_version"] == "injection-recovery-curves-v1"
    assert report["passed"] is True
    assert report["source_report"] == str(source)


def test_extract_injection_recovery_report_missing_key(tmp_path):
    source = tmp_path / "injection_recovery.json"
    source.write_text(json.dumps({"n_injected": 200}))
    with pytest.raises(ValueError, match="no nested 'recovery_curves'"):
        extract_promotion_evidence.extract_injection_recovery_report(source)


def test_extract_injection_recovery_report_wrong_schema(tmp_path):
    source = tmp_path / "injection_recovery.json"
    source.write_text(
        json.dumps({"recovery_curves": {"schema_version": "something-else"}})
    )
    with pytest.raises(ValueError, match="unexpected schema_version"):
        extract_promotion_evidence.extract_injection_recovery_report(source)


def test_extract_false_discovery_report_computes_rate(tmp_path):
    source = tmp_path / "ranking_baseline.json"
    source.write_text(
        json.dumps(
            {
                "n_positive": 200,
                "n_negative": 142,
                "false_positive_review_burden": {
                    "threshold": 0.5,
                    "n_flagged": 200,
                    "n_false_positive": 0,
                },
                "logistic_regression_handcrafted": {"name": "logreg"},
            }
        )
    )
    report = extract_promotion_evidence.extract_false_discovery_report(
        source, model_name="logistic_regression_handcrafted"
    )
    assert report["schema_version"] == "false-discovery-report-v1"
    assert report["false_discovery_rate"] == 0.0
    assert report["n_flagged"] == 200
    assert report["model_evaluated"] == "logistic_regression_handcrafted"


def test_extract_false_discovery_report_nonzero_rate(tmp_path):
    source = tmp_path / "ranking_baseline.json"
    source.write_text(
        json.dumps(
            {
                "false_positive_review_burden": {
                    "threshold": 0.5,
                    "n_flagged": 100,
                    "n_false_positive": 5,
                },
                "naive_real_bogus_only": {"name": "naive"},
            }
        )
    )
    report = extract_promotion_evidence.extract_false_discovery_report(
        source, model_name="naive_real_bogus_only"
    )
    assert report["false_discovery_rate"] == pytest.approx(0.05)


def test_extract_false_discovery_report_missing_burden(tmp_path):
    source = tmp_path / "ranking_baseline.json"
    source.write_text(json.dumps({}))
    with pytest.raises(ValueError, match="false_positive_review_burden"):
        extract_promotion_evidence.extract_false_discovery_report(
            source, model_name="logistic_regression_handcrafted"
        )


def test_extract_false_discovery_report_missing_model_block(tmp_path):
    source = tmp_path / "ranking_baseline.json"
    source.write_text(
        json.dumps(
            {
                "false_positive_review_burden": {
                    "threshold": 0.5,
                    "n_flagged": 10,
                    "n_false_positive": 0,
                }
            }
        )
    )
    with pytest.raises(ValueError, match="no 'logistic_regression_handcrafted'"):
        extract_promotion_evidence.extract_false_discovery_report(
            source, model_name="logistic_regression_handcrafted"
        )


def test_main_writes_both_reports(tmp_path):
    injection_source = tmp_path / "injection_recovery.json"
    injection_source.write_text(
        json.dumps(
            {"recovery_curves": {"schema_version": "injection-recovery-curves-v1", "passed": True}}
        )
    )
    ranking_source = tmp_path / "ranking_baseline.json"
    ranking_source.write_text(
        json.dumps(
            {
                "false_positive_review_burden": {
                    "threshold": 0.5,
                    "n_flagged": 50,
                    "n_false_positive": 0,
                },
                "logistic_regression_handcrafted": {"name": "logreg"},
            }
        )
    )
    injection_out = tmp_path / "out_injection.json"
    fdr_out = tmp_path / "out_fdr.json"

    rc = extract_promotion_evidence.main(
        [
            "--injection-recovery-source",
            str(injection_source),
            "--injection-recovery-out",
            str(injection_out),
            "--ranking-baseline-source",
            str(ranking_source),
            "--false-discovery-out",
            str(fdr_out),
        ]
    )
    assert rc == 0
    assert json.loads(injection_out.read_text())["schema_version"] == "injection-recovery-curves-v1"
    assert json.loads(fdr_out.read_text())["false_discovery_rate"] == 0.0


def test_main_no_args_returns_error():
    assert extract_promotion_evidence.main([]) == 1
