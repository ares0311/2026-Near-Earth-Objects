"""Validate Astrometrics dataset manifest files.

This intentionally implements the repository's current schema subset with the
standard library so manifest validation does not add a runtime dependency.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PROJECT = "2026 Near Earth Objects"
VALID_ROLES = {
    "training",
    "validation",
    "calibration",
    "frozen_eval",
    "live_search",
    "followup_live_search",
    "positive_control",
    "negative_control",
    "submission_package_evidence",
}
VALID_TIME_SCALES = {"JD", "MJD", "UTC", "TAI", "TDB"}
VALID_CHECKSUM_ALGORITHMS = {"sha256", "sha512", "none"}
VALID_LABEL_CONFIDENCE = {
    "confirmed",
    "catalog",
    "operator_reviewed",
    "synthetic",
    "unlabeled",
    "mixed",
}
REQUIRED_FIELDS = {
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


class ManifestValidationError(ValueError):
    """Raised when a dataset manifest violates the policy schema."""


def _require_string(data: dict[str, Any], key: str, errors: list[str]) -> None:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{key}: expected a non-empty string")


def validate_manifest(data: dict[str, Any]) -> None:
    """Validate one decoded dataset manifest.

    Raises:
        ManifestValidationError: if the manifest is invalid.
    """

    errors: list[str] = []
    missing = sorted(REQUIRED_FIELDS.difference(data))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")

    extra = sorted(set(data).difference(REQUIRED_FIELDS))
    if extra:
        errors.append(f"unexpected fields: {', '.join(extra)}")

    for key in (
        "dataset_id",
        "source_name",
        "source_url",
        "instrument",
        "cadence",
        "band_or_frequency",
        "data_product_type",
        "downloaded_at",
        "local_path",
        "license",
        "label_source",
        "preprocessing_version",
    ):
        _require_string(data, key, errors)

    if data.get("project") != PROJECT:
        errors.append(f"project: expected {PROJECT!r}")

    if data.get("role") not in VALID_ROLES:
        errors.append(f"role: expected one of {sorted(VALID_ROLES)}")

    target_ids = data.get("target_ids")
    if not isinstance(target_ids, list) or any(
        not isinstance(item, str) or not item.strip() for item in target_ids
    ):
        errors.append("target_ids: expected a list of non-empty strings")
    elif len(target_ids) != len(set(target_ids)):
        errors.append("target_ids: values must be unique")

    time_range = data.get("time_range")
    if not isinstance(time_range, dict):
        errors.append("time_range: expected an object")
    else:
        for key in ("start", "end"):
            if not isinstance(time_range.get(key), str) or not time_range.get(key, "").strip():
                errors.append(f"time_range.{key}: expected a non-empty string")
        if time_range.get("scale") not in VALID_TIME_SCALES:
            errors.append(f"time_range.scale: expected one of {sorted(VALID_TIME_SCALES)}")
        extra_time = sorted(set(time_range).difference({"start", "end", "scale"}))
        if extra_time:
            errors.append(f"time_range: unexpected fields: {', '.join(extra_time)}")

    checksum = data.get("checksum")
    if not isinstance(checksum, dict):
        errors.append("checksum: expected an object")
    else:
        if checksum.get("algorithm") not in VALID_CHECKSUM_ALGORITHMS:
            errors.append(
                f"checksum.algorithm: expected one of {sorted(VALID_CHECKSUM_ALGORITHMS)}"
            )
        if not isinstance(checksum.get("value"), str) or not checksum.get("value", "").strip():
            errors.append("checksum.value: expected a non-empty string")
        extra_checksum = sorted(set(checksum).difference({"algorithm", "value"}))
        if extra_checksum:
            errors.append(f"checksum: unexpected fields: {', '.join(extra_checksum)}")

    if data.get("label_confidence") not in VALID_LABEL_CONFIDENCE:
        errors.append(f"label_confidence: expected one of {sorted(VALID_LABEL_CONFIDENCE)}")

    caveats = data.get("known_caveats")
    if not isinstance(caveats, list) or any(
        not isinstance(item, str) or not item.strip() for item in caveats
    ):
        errors.append("known_caveats: expected a list of non-empty strings")

    if errors:
        raise ManifestValidationError("; ".join(errors))


def load_manifest(path: Path) -> dict[str, Any]:
    decoded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ManifestValidationError("manifest root must be a JSON object")
    return decoded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="+", type=Path)
    args = parser.parse_args()

    for manifest_path in args.manifest:
        validate_manifest(load_manifest(manifest_path))
        print(f"OK {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
