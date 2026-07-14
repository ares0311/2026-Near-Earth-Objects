"""Offline tests for safe association of retained ZTF portfolio alerts."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "Skills"
sys.path.insert(0, str(SKILLS))
sys.path.insert(0, str(ROOT / "src"))
SPEC = importlib.util.spec_from_file_location(
    "analyze_ztf_alert_archive_portfolio",
    SKILLS / "analyze_ztf_alert_archive_portfolio.py",
)
assert SPEC and SPEC.loader
analyzer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = analyzer
SPEC.loader.exec_module(analyzer)


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
                        "field_id": "field_a",
                        "role": "followup_live_search",
                        "ra_deg": 180.0,
                        "dec_deg": 0.0,
                        "radius_deg": 2.0,
                    },
                    {
                        "field_id": "field_b",
                        "role": "live_search",
                        "ra_deg": 30.0,
                        "dec_deg": 10.0,
                        "radius_deg": 2.0,
                    },
                ],
                "controls": [{"control_id": "injection"}],
            }
        ),
        encoding="utf-8",
    )
    return path


def _obs(obs_id: str, jd: float, ra: float, dec: float) -> dict:
    return {
        "obs_id": obs_id,
        "ra_deg": ra,
        "dec_deg": dec,
        "jd": jd,
        "mag": 19.0,
        "mag_err": 0.05,
        "filter_band": "r",
        "mission": "ZTF",
        "real_bogus": 0.95,
        "field_id": "563",
        "limiting_mag": 20.5,
    }


def _write_states(tmp_path: Path, manifest: Path) -> Path:
    root = tmp_path / "checkpoints"
    batch_dir = root / "batch_v1"
    batch_dir.mkdir(parents=True)
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    rng = np.random.default_rng(7)
    for index, night in enumerate(("20240101", "20240102", "20240103")):
        rows: list[dict] = []
        if index < 2:
            jd = 2460310.5 + index
            base_ra = 180.0 + index * 24.0 / 3600.0
            rows = [
                _obs(
                    f"{night}_a",
                    jd,
                    base_ra + rng.normal(0.0, 0.05 / 3600.0),
                    rng.normal(0.0, 0.05 / 3600.0),
                ),
                _obs(
                    f"{night}_b",
                    jd + 1 / 24,
                    base_ra + 1.0 / 3600.0 + rng.normal(0.0, 0.05 / 3600.0),
                    rng.normal(0.0, 0.05 / 3600.0),
                ),
            ]
        state = {
            "batch_id": "batch_v1",
            "batch_manifest_sha256": digest,
            "observations_by_field": {"field_a": rows, "field_b": []},
        }
        (batch_dir / f"{night}.json").write_text(json.dumps(state), encoding="utf-8")
    return root


def test_eligible_fields_require_two_populated_nights(tmp_path: Path, monkeypatch) -> None:
    manifest = _manifest(tmp_path)
    monkeypatch.setattr(analyzer.portfolio, "REPO_ROOT", tmp_path)
    batch = analyzer.portfolio.load_batch_manifest(manifest)
    states = analyzer._load_states(batch, _write_states(tmp_path, manifest))
    assert analyzer.eligible_field_nights(batch, states) == {
        "field_a": ("20240101", "20240102")
    }


def test_manifest_hash_mismatch_fails_closed(tmp_path: Path, monkeypatch) -> None:
    manifest = _manifest(tmp_path)
    monkeypatch.setattr(analyzer.portfolio, "REPO_ROOT", tmp_path)
    batch = analyzer.portfolio.load_batch_manifest(manifest)
    root = _write_states(tmp_path, manifest)
    path = root / "batch_v1" / "20240101.json"
    state = json.loads(path.read_text())
    state["batch_manifest_sha256"] = "wrong"
    path.write_text(json.dumps(state))
    with pytest.raises(ValueError, match="SHA-256"):
        analyzer._load_states(batch, root)


def test_analyze_batch_links_motion_without_field_identity_grouping(
    tmp_path: Path, monkeypatch
) -> None:
    manifest = _manifest(tmp_path)
    monkeypatch.setattr(analyzer.portfolio, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(analyzer, "REPO_ROOT", tmp_path)
    report = analyzer.analyze_batch(
        manifest, _write_states(tmp_path, manifest), min_observations=2
    )
    assert report["n_eligible_fields"] == 1
    assert report["n_tracklets_linked"] >= 1
    assert report["candidate_review_allowed"] is False
    field = report["fields"][0]
    assert field["n_observations_loaded"] == 4
    assert field["known_object_exclusion_status"] == "pending_time_aware_audit"
