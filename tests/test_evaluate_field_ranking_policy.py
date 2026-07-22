"""Behavioral tests for the Phase 2 retrospective ranking-policy audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "Skills"))

import evaluate_field_ranking_policy as audit  # noqa: E402


def test_pairwise_auc_uses_independent_pair_ordering() -> None:
    assert audit._pairwise_auc([3.0, 1.0], [2.0, 1.0]) == 0.625
    assert audit._pairwise_auc([], [1.0]) is None


def test_real_audit_reproduces_scores_and_blocks_unsupported_fit() -> None:
    result = audit.build_policy_audit(
        audit.DEFAULT_POSITIVES,
        audit.DEFAULT_NULLS,
        audit.DEFAULT_POLICY,
    )

    assert result["status"] == "audit_complete_not_calibrated"
    assert result["score_reproduction"]["searched_null_count"] == 9
    assert result["score_reproduction"]["maximum_absolute_drift"] <= 0.0002
    gate = result["coefficient_promotion_gate"]
    assert gate["coefficient_update_authorized"] is False
    assert gate["observed_counts"] == {
        "aten": {"positive": 1, "searched_null": 6},
        "ieo": {"positive": 7, "searched_null": 3},
    }
    assert result["all_source_metrics"]["aten"]["all"]["positive_count"] == 56
    assert result["all_source_metrics"]["ieo"]["all"]["positive_count"] == 19


def test_audit_rejects_recorded_score_drift(tmp_path: Path) -> None:
    payload = json.loads(audit.DEFAULT_NULLS.read_text(encoding="utf-8"))
    payload["entries"][0]["recorded_score"] = 0.1
    path = tmp_path / "drifted_nulls.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="recorded score drift"):
        audit.build_policy_audit(
            audit.DEFAULT_POSITIVES,
            path,
            audit.DEFAULT_POLICY,
        )


def test_positive_envelope_must_be_complete(tmp_path: Path) -> None:
    path = tmp_path / "partial.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": audit.POSITIVE_SCHEMA_VERSION,
                "status": "running",
                "summary": {"complete": False},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not complete"):
        audit._load_positive_envelope(path)
