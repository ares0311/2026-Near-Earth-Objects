"""Behavioral tests for the searched-field null-outcome evidence gate."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "Skills"))

import validate_field_null_outcomes as validator  # noqa: E402


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode()).hexdigest()


def _manifest(tmp_path: Path) -> dict[str, object]:
    queue_hash = _write(tmp_path / "data_selection/queue.csv", "rank,score\n1,0.9\n")
    evidence_hash = _write(tmp_path / "docs/evidence/run.md", "real bounded null\n")
    return {
        "schema_version": validator.SCHEMA_VERSION,
        "dataset_id": "fixture-nulls-v1",
        "source_queue": {
            "path": "data_selection/queue.csv",
            "sha256": queue_hash,
        },
        "eligibility": {
            "minimum_populated_nights": 3,
            "required_outcome": "null_result",
        },
        "entries": [
            {
                "outcome_id": "fixture-null-1",
                "ra_deg": 10.0,
                "dec_deg": -5.0,
                "field_radius_deg": 3.5,
                "observation_nights_yyyymmdd": ["20240101", "20240102", "20240103"],
                "outcome": "null_result",
                "recorded_rank": 1,
                "recorded_score": 0.9,
                "ranking_mode": "aten",
                "ranking_jd": 2460310.5,
                "execution_ids": ["run-1"],
                "production_tracklet_count": 2,
                "surviving_review_count": 0,
                "evidence_path": "docs/evidence/run.md",
                "evidence_sha256": evidence_hash,
            }
        ],
        "excluded_searches": [
            {
                "ra_deg": 20.0,
                "dec_deg": 5.0,
                "status": "insufficient_coverage",
                "evidence_path": "docs/evidence/run.md",
            }
        ],
    }


def _validate(tmp_path: Path, payload: dict[str, object]) -> dict[str, object]:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return validator.validate_null_outcomes(path, repo_root=tmp_path)


def test_validator_accepts_evidence_bound_eligible_null(tmp_path: Path) -> None:
    assert _validate(tmp_path, _manifest(tmp_path)) == {
        "dataset_id": "fixture-nulls-v1",
        "entry_count": 1,
        "evidence_file_count": 1,
        "excluded_count": 1,
        "minimum_populated_nights": 3,
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload["entries"][0].update(outcome="not_searched"), "not a null_result"),
        (
            lambda payload: payload["entries"][0].update(
                observation_nights_yyyymmdd=["20240101", "20240102"]
            ),
            "at least 3 unique valid nights",
        ),
        (lambda payload: payload["entries"][0].update(evidence_sha256="0" * 64), "hash mismatch"),
        (
            lambda payload: payload["entries"].append(
                copy.deepcopy(payload["entries"][0])
            ),
            "duplicate outcome_id",
        ),
    ],
)
def test_validator_rejects_false_or_unverifiable_nulls(
    tmp_path: Path, mutation: object, message: str
) -> None:
    payload = _manifest(tmp_path)
    mutation(payload)
    with pytest.raises(ValueError, match=message):
        _validate(tmp_path, payload)


def test_validator_rejects_source_queue_drift(tmp_path: Path) -> None:
    payload = _manifest(tmp_path)
    (tmp_path / "data_selection/queue.csv").write_text("changed\n", encoding="utf-8")

    with pytest.raises(ValueError, match="source queue hash"):
        _validate(tmp_path, payload)


def test_validator_rejects_repository_path_escape(tmp_path: Path) -> None:
    payload = _manifest(tmp_path)
    payload["entries"][0]["evidence_path"] = "../outside.md"

    with pytest.raises(ValueError, match="escapes the repository root"):
        _validate(tmp_path, payload)
