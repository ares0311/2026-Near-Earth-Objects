#!/usr/bin/env python3
"""Validate durable, evidence-bound ZTF searched-field null outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "ztf-field-null-outcomes-v1"
DEFAULT_MANIFEST = ROOT / "data_selection/calibration/ztf_field_null_outcomes_v1.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_file(repo_root: Path, relative: Any, *, field: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"{field} must be a nonempty repository-relative path")
    root = repo_root.resolve()
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{field} escapes the repository root: {relative}") from exc
    if not path.is_file():
        raise ValueError(f"{field} does not exist: {relative}")
    return path


def _valid_night(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 8:
        return False
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return False
    return True


def validate_null_outcomes(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Validate schema, eligibility, uniqueness, and bound evidence hashes."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported null-outcome schema: {manifest_path}")

    source_queue = payload.get("source_queue")
    if not isinstance(source_queue, dict):
        raise ValueError("source_queue must be an object")
    queue_path = _repo_file(repo_root, source_queue.get("path"), field="source_queue.path")
    if _sha256(queue_path) != source_queue.get("sha256"):
        raise ValueError("source queue hash does not match the manifest")

    eligibility = payload.get("eligibility")
    if not isinstance(eligibility, dict):
        raise ValueError("eligibility must be an object")
    minimum_nights = eligibility.get("minimum_populated_nights")
    if not isinstance(minimum_nights, int) or minimum_nights < 3:
        raise ValueError("minimum_populated_nights must be an integer of at least 3")
    required_outcome = eligibility.get("required_outcome")
    if required_outcome != "null_result":
        raise ValueError("required_outcome must be null_result")

    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("entries must be a nonempty list")
    outcome_ids: set[str] = set()
    coordinates: set[tuple[float, float]] = set()
    evidence_files: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"entries[{index}] must be an object")
        outcome_id = entry.get("outcome_id")
        if not isinstance(outcome_id, str) or not outcome_id:
            raise ValueError(f"entries[{index}].outcome_id must be nonempty")
        if outcome_id in outcome_ids:
            raise ValueError(f"duplicate outcome_id: {outcome_id}")
        outcome_ids.add(outcome_id)

        try:
            ra_deg = float(entry["ra_deg"])
            dec_deg = float(entry["dec_deg"])
            radius_deg = float(entry["field_radius_deg"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{outcome_id} has invalid field coordinates") from exc
        if not (
            math.isfinite(ra_deg)
            and math.isfinite(dec_deg)
            and math.isfinite(radius_deg)
            and 0.0 <= ra_deg < 360.0
            and -90.0 <= dec_deg <= 90.0
            and radius_deg > 0.0
        ):
            raise ValueError(f"{outcome_id} has out-of-range field coordinates")
        coordinate = (ra_deg, dec_deg)
        if coordinate in coordinates:
            raise ValueError(f"duplicate searched field: {coordinate}")
        coordinates.add(coordinate)

        nights = entry.get("observation_nights_yyyymmdd")
        if (
            not isinstance(nights, list)
            or len(nights) < minimum_nights
            or len(set(nights)) != len(nights)
            or not all(_valid_night(night) for night in nights)
        ):
            raise ValueError(
                f"{outcome_id} must contain at least {minimum_nights} unique valid nights"
            )
        if entry.get("outcome") != required_outcome:
            raise ValueError(f"{outcome_id} is not a null_result")
        rank = entry.get("recorded_rank")
        score = entry.get("recorded_score")
        if not isinstance(rank, int) or rank < 1:
            raise ValueError(f"{outcome_id} has invalid recorded_rank")
        if not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError(f"{outcome_id} has invalid recorded_score")
        if entry.get("ranking_mode") not in {"aten", "ieo"}:
            raise ValueError(f"{outcome_id} has invalid ranking_mode")
        ranking_jd = entry.get("ranking_jd")
        if (
            not isinstance(ranking_jd, (int, float))
            or not math.isfinite(ranking_jd)
            or ranking_jd < 2_400_000
        ):
            raise ValueError(f"{outcome_id} has invalid ranking_jd")
        execution_ids = entry.get("execution_ids")
        if (
            not isinstance(execution_ids, list)
            or not execution_ids
            or not all(isinstance(value, str) and value for value in execution_ids)
        ):
            raise ValueError(f"{outcome_id} must identify its execution")
        tracklets = entry.get("production_tracklet_count")
        survivors = entry.get("surviving_review_count")
        if not isinstance(tracklets, int) or tracklets < 0:
            raise ValueError(f"{outcome_id} has invalid production_tracklet_count")
        if survivors != 0:
            raise ValueError(f"{outcome_id} cannot be null with surviving reviews")

        evidence_relative = entry.get("evidence_path")
        evidence_path = _repo_file(repo_root, evidence_relative, field="evidence_path")
        if _sha256(evidence_path) != entry.get("evidence_sha256"):
            raise ValueError(f"evidence hash mismatch for {outcome_id}")
        evidence_files.add(str(evidence_relative))

    exclusions = payload.get("excluded_searches")
    if not isinstance(exclusions, list):
        raise ValueError("excluded_searches must be a list")
    for index, exclusion in enumerate(exclusions):
        if not isinstance(exclusion, dict):
            raise ValueError(f"excluded_searches[{index}] must be an object")
        if exclusion.get("status") == required_outcome:
            raise ValueError("excluded searches cannot be labeled null_result")
        evidence_relative = exclusion.get("evidence_path")
        _repo_file(repo_root, evidence_relative, field="excluded evidence_path")
        coordinate = (float(exclusion["ra_deg"]), float(exclusion["dec_deg"]))
        if coordinate in coordinates:
            raise ValueError(f"excluded search duplicates a null outcome: {coordinate}")

    return {
        "dataset_id": payload.get("dataset_id"),
        "entry_count": len(entries),
        "excluded_count": len(exclusions),
        "evidence_file_count": len(evidence_files),
        "minimum_populated_nights": minimum_nights,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate evidence-bound ZTF searched-field null outcomes"
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    summary = validate_null_outcomes(args.manifest, repo_root=args.repo_root)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
