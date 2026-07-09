from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from Skills.validate_dataset_manifest import ManifestValidationError, validate_manifest


def _valid_manifest() -> dict[str, object]:
    return {
        "dataset_id": "ztf-dr24-positive-control-72966-v1",
        "project": "2026 Near Earth Objects",
        "role": "positive_control",
        "source_name": "UW ZTF public alert archive",
        "source_url": "archive-uri-recorded-in-decision-log",
        "instrument": "ZTF",
        "target_ids": ["72966"],
        "time_range": {"start": "2459000.5", "end": "2459030.5", "scale": "JD"},
        "cadence": "archival alert replay",
        "band_or_frequency": "ZTF g/r/i",
        "data_product_type": "alert packets",
        "downloaded_at": "2026-07-08T00:00:00Z",
        "local_path": "external-cache://ztf-dr24-positive-control-72966-v1",
        "checksum": {"algorithm": "none", "value": "external-archive-replay"},
        "license": "public archive; cite upstream archive",
        "label_source": "MPC/JPL known-object designation",
        "label_confidence": "catalog",
        "preprocessing_version": "neo-detection-v0.90.60",
        "known_caveats": ["Positive-control manifest only; not a blind discovery dataset."],
    }


def test_valid_manifest_passes() -> None:
    validate_manifest(_valid_manifest())


def test_missing_required_field_fails() -> None:
    manifest = _valid_manifest()
    del manifest["source_url"]

    with pytest.raises(ManifestValidationError, match="missing required fields: source_url"):
        validate_manifest(manifest)


def test_live_search_manifest_cannot_have_duplicate_targets() -> None:
    manifest = _valid_manifest()
    manifest["role"] = "live_search"
    manifest["label_confidence"] = "unlabeled"
    manifest["target_ids"] = ["field-001", "field-001"]

    with pytest.raises(ManifestValidationError, match="target_ids: values must be unique"):
        validate_manifest(manifest)


def test_cli_validates_manifest_file(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_valid_manifest()), encoding="utf-8")

    result = subprocess.run(
        [
            "uv",
            "run",
            "--python",
            "3.14",
            "python",
            "Skills/validate_dataset_manifest.py",
            str(manifest_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert f"OK {manifest_path}" in result.stdout
