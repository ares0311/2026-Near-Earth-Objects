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
    """Write a minimal portfolio manifest shared by analyzer tests."""
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
    """Build one serialized ZTF observation row."""
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
    """Write query-bound checkpoints for the first synthetic batch."""
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


def _supplement_manifest(tmp_path: Path, *, changed_ra: bool = False) -> Path:
    """Write a supplemental manifest, optionally with incompatible geometry."""
    payload = json.loads(_manifest(tmp_path).read_text(encoding="utf-8"))
    payload["batch_id"] = "batch_v2"
    payload["nights"] = ["20240102", "20240104"]
    if changed_ra:
        payload["fields"][0]["ra_deg"] = 181.0
    path = tmp_path / "supplement.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_supplement_states(root: Path, manifest: Path) -> None:
    """Write a supplement containing one duplicate night and one new night."""
    batch_dir = root / "batch_v2"
    batch_dir.mkdir(parents=True)
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    prior = json.loads((root / "batch_v1" / "20240102.json").read_text())
    duplicate_rows = prior["observations_by_field"]["field_a"]
    new_rows = [
        _obs("20240104_a", 2460313.5, 180.02, 0.0),
        _obs("20240104_b", 2460313.5 + 1 / 24, 180.0203, 0.0),
    ]
    for night, rows in (("20240102", duplicate_rows), ("20240104", new_rows)):
        state = {
            "batch_id": "batch_v2",
            "batch_manifest_sha256": digest,
            "observations_by_field": {"field_a": rows, "field_b": []},
        }
        (batch_dir / f"{night}.json").write_text(json.dumps(state), encoding="utf-8")


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


def test_analyze_batches_merges_prior_and_supplement_without_duplicate_observations(
    tmp_path: Path, monkeypatch
) -> None:
    first = _manifest(tmp_path)
    supplement = _supplement_manifest(tmp_path)
    root = _write_states(tmp_path, first)
    _write_supplement_states(root, supplement)
    monkeypatch.setattr(analyzer.portfolio, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(analyzer, "REPO_ROOT", tmp_path)

    report = analyzer.analyze_batches(
        (first, supplement), root, min_observations=2, field_ids=("field_a",)
    )

    assert report["schema_version"] == "ztf-portfolio-cross-batch-association-v1"
    assert report["batch_ids"] == ["batch_v1", "batch_v2"]
    assert report["n_input_batches"] == 2
    assert report["selected_field_ids"] == ["field_a"]
    assert report["eligible_fields"]["field_a"] == [
        "20240101",
        "20240102",
        "20240104",
    ]
    # The supplemental copy of 20240102 is identical and must not be counted twice.
    assert report["fields"][0]["n_observations_loaded"] == 6
    assert report["candidate_review_allowed"] is False


def test_analyze_batches_rejects_changed_field_definition(tmp_path: Path, monkeypatch) -> None:
    first = _manifest(tmp_path)
    supplement = _supplement_manifest(tmp_path, changed_ra=True)
    root = _write_states(tmp_path, first)
    _write_supplement_states(root, supplement)
    monkeypatch.setattr(analyzer.portfolio, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(analyzer, "REPO_ROOT", tmp_path)

    with pytest.raises(ValueError, match="field definition mismatch"):
        analyzer.analyze_batches((first, supplement), root)


def test_analyze_batches_rejects_unknown_field_and_duplicate_batch(
    tmp_path: Path, monkeypatch
) -> None:
    manifest = _manifest(tmp_path)
    root = _write_states(tmp_path, manifest)
    monkeypatch.setattr(analyzer.portfolio, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(analyzer, "REPO_ROOT", tmp_path)

    with pytest.raises(ValueError, match="unknown --field-id"):
        analyzer.analyze_batches((manifest,), root, field_ids=("missing",))
    with pytest.raises(ValueError, match="batch_id values must be unique"):
        analyzer.analyze_batches((manifest, manifest), root)


def test_analyze_batches_rejects_empty_inputs_and_duplicate_field_allowlist(
    tmp_path: Path, monkeypatch
) -> None:
    """Fail closed when callers provide no provenance or repeat field selectors."""
    manifest = _manifest(tmp_path)
    root = _write_states(tmp_path, manifest)
    monkeypatch.setattr(analyzer.portfolio, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(analyzer, "REPO_ROOT", tmp_path)

    with pytest.raises(ValueError, match="at least one batch manifest"):
        analyzer.analyze_batches((), root)
    with pytest.raises(ValueError, match="--field-id values must be unique"):
        analyzer.analyze_batches(
            (manifest,), root, field_ids=("field_a", "field_a")
        )


@pytest.mark.parametrize("failure", ["missing_id", "conflicting_duplicate"])
def test_analyze_batches_rejects_invalid_duplicate_rows(
    tmp_path: Path, monkeypatch, failure: str
) -> None:
    """Reject rows that cannot be safely deduplicated across source batches."""
    first = _manifest(tmp_path)
    supplement = _supplement_manifest(tmp_path)
    root = _write_states(tmp_path, first)
    _write_supplement_states(root, supplement)
    path = root / "batch_v2" / "20240102.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    rows = state["observations_by_field"]["field_a"]
    if failure == "missing_id":
        rows[0]["obs_id"] = ""
        expected = "observation without obs_id"
    else:
        rows[0]["ra_deg"] += 1.0
        expected = "conflicting duplicate observation"
    path.write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(analyzer.portfolio, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(analyzer, "REPO_ROOT", tmp_path)

    with pytest.raises(ValueError, match=expected):
        analyzer.analyze_batches((first, supplement), root)
