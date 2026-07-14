"""Offline tests for the native sharded ZTF portfolio downloader."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "Skills"
sys.path.insert(0, str(SKILLS))
SPEC = importlib.util.spec_from_file_location(
    "ztf_alert_archive_portfolio", SKILLS / "ztf_alert_archive_portfolio.py"
)
assert SPEC and SPEC.loader
portfolio = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = portfolio
SPEC.loader.exec_module(portfolio)


def _manifest(tmp_path: Path) -> Path:
    path = tmp_path / "batch.json"
    path.write_text(
        json.dumps(
            {
                "batch_id": "batch_v1",
                "nights": ["20240101", "20240102", "20240103"],
                "portfolio_role_mix": {"new": 6, "followup": 3, "control": 1},
                "fields": [
                    {
                        "field_id": "new_a",
                        "role": "live_search",
                        "ra_deg": 10.0,
                        "dec_deg": 20.0,
                        "radius_deg": 2.0,
                    },
                    {
                        "field_id": "follow_b",
                        "role": "followup_live_search",
                        "ra_deg": 30.0,
                        "dec_deg": -10.0,
                        "radius_deg": 1.0,
                    },
                ],
                "controls": [{"control_id": "injection"}],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_load_manifest_and_assign_disjoint_nights(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(portfolio, "REPO_ROOT", tmp_path)
    batch = portfolio.load_batch_manifest(_manifest(tmp_path))
    assert batch.batch_id == "batch_v1"
    assert portfolio.assigned_nights(batch.nights, 0, 2) == ("20240101", "20240103")
    assert portfolio.assigned_nights(batch.nights, 1, 2) == ("20240102",)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data.update(batch_id="bad id"), "batch_id"),
        (lambda data: data.update(nights=["bad"]), "YYYYMMDD"),
        (
            lambda data: data.update(portfolio_role_mix={"new": 9}),
            "60/30/10",
        ),
    ],
)
def test_manifest_validation_fails_closed(
    tmp_path: Path, monkeypatch, mutation, message: str
) -> None:
    monkeypatch.setattr(portfolio, "REPO_ROOT", tmp_path)
    path = _manifest(tmp_path)
    data = json.loads(path.read_text())
    mutation(data)
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match=message):
        portfolio.load_batch_manifest(path)


def test_matching_fields_uses_spherical_cones() -> None:
    fields = (
        portfolio.SearchField("a", "live_search", 10.0, 20.0, 2.0),
        portfolio.SearchField("b", "live_search", 100.0, -20.0, 2.0),
    )
    assert portfolio.matching_field_ids(fields, 10.5, 20.2) == ("a",)
    assert portfolio.matching_field_ids(fields, 50.0, 0.0) == ()


def test_checkpoint_binding_rejects_changed_query(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(portfolio, "REPO_ROOT", tmp_path)
    batch = portfolio.load_batch_manifest(_manifest(tmp_path))
    path = tmp_path / "checkpoint.json"
    state = {
        "batch_id": batch.batch_id,
        "batch_manifest_sha256": batch.manifest_sha256,
        "min_rb": 0.5,
        "max_per_field_night": 50,
    }
    portfolio._write_checkpoint(path, state)
    assert portfolio._read_checkpoint(path, batch, 0.5, 50) == state
    with pytest.raises(RuntimeError, match="does not match"):
        portfolio._read_checkpoint(path, batch, 0.6, 50)


def test_output_dir_must_stay_in_repository(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(portfolio, "REPO_ROOT", repo)
    assert portfolio.resolve_output_dir(repo / "Logs") == repo / "Logs"
    with pytest.raises(ValueError, match="inside the repository"):
        portfolio.resolve_output_dir(tmp_path / "outside")


def test_run_shard_passes_only_owned_nights(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(portfolio, "REPO_ROOT", tmp_path)
    batch = portfolio.load_batch_manifest(_manifest(tmp_path))
    seen: list[str] = []

    def fake_ingest(night, *_args, **_kwargs):
        seen.append(night)
        return {"scanned_count": 10, "kept_count": 2}

    monkeypatch.setattr(portfolio, "ingest_portfolio_night", fake_ingest)
    summary = portfolio.run_shard(batch, tmp_path / "out", 1, 2, 2, 0.5, 50)
    assert seen == ["20240102"]
    assert summary["kept_count"] == 2
    assert summary["status"] == "succeeded"


def test_committed_coverage_selected_batch_is_query_bound_and_bounded() -> None:
    path = (
        ROOT
        / "data_selection/batch_manifests/ztf_dr24_coverage_selected_2024_v1.json"
    )
    batch = portfolio.load_batch_manifest(path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert batch.nights == ("20240321", "20240422", "20240504", "20240603")
    assert len(batch.fields) == 9
    assert payload["coverage_preflight_query_key"] == "807efb0e5ef7d55d"
    assert sum(payload["verified_remote_bytes"].values()) == 26_670_482_707
    assert payload["estimated_persistent_output_gb"] == 1.0
    assert payload["safety"]["raw_archive_persisted"] is False
    assert payload["safety"]["external_submission"] is False

    selected_nights = set(batch.nights)
    coverage = payload["new_field_coverage_nights"]
    new_field_ids = {
        field.field_id for field in batch.fields if field.role == "live_search"
    }
    assert set(coverage) == new_field_ids
    assert all(len(set(nights)) == 3 for nights in coverage.values())
    assert all(set(nights) <= selected_nights for nights in coverage.values())
