#!/usr/bin/env python3
"""Validate, split, and tokenize real sequences for Tier 3 training.

Legacy mode converts one JSON input into one flat token CSV. Production mode
merges MPC and ALeRCE acquisition envelopes, validates the approved five-class
contract, performs designation-grouped stratified splits, and records a
machine-readable preparation report.

Usage:
    python Skills/build_sequence_dataset.py \
        --input data/sequences/mpc_pilot.json data/sequences/alerce_artifact_pilot.json \
        --output-dir data/sequences/pilot --min-per-class 50
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

LABEL_MAP = {
    "neo_candidate": 0,
    "known_object": 1,
    "main_belt_asteroid": 2,
    "stellar_artifact": 3,
    "other_solar_system": 4,
}
_FILTER_MAP = {"g": 0, "r": 1, "i": 2, "o": 3, "c": 4, "V": 5}
_N_FEATURES = 5
PREPARATION_SCHEMA_VERSION = "tier3-preparation-v1"


def _utc_now() -> str:
    """Return an ISO-8601 UTC timestamp for dataset provenance."""
    return datetime.now(UTC).isoformat()


def _sha256_file(path: Path) -> str:
    """Hash one raw input so every derived split can be reproduced."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _obs_to_token(obs: dict[str, Any], t0: float) -> list[float]:
    """Normalize one observation into the five Transformer token features."""
    ra = float(obs.get("ra_deg", 0.0)) / 360.0
    dec = (float(obs.get("dec_deg", 0.0)) + 90.0) / 180.0
    mag = float(obs.get("mag", 20.0)) / 30.0
    dt = (float(obs.get("jd", t0)) - t0) / 30.0
    filt = _FILTER_MAP.get(str(obs.get("filter_band", "r")), 1) / 5.0
    return [ra, dec, mag, dt, filt]


def _load_envelope(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load either a legacy entry list or a versioned acquisition envelope."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload, {"schema_version": "legacy-list", "safety": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        raise ValueError(f"{path} does not contain a supported sequence dataset")
    return payload["entries"], {
        "schema_version": payload.get("schema_version", "unknown"),
        "source": payload.get("source", {}),
        "safety": payload.get("safety", {}),
    }


def _night_count(observations: list[dict[str, Any]]) -> int:
    """Count distinct UTC observing dates from Julian dates."""
    return len({int(float(observation["jd"]) + 0.5) for observation in observations})


def validate_entries(
    entries: list[dict[str, Any]],
    *,
    min_per_class: int,
    min_observations: int = 3,
    min_nights: int = 2,
) -> dict[str, Any]:
    """Validate five-class balance, schema integrity, and object-level isolation."""
    if min_per_class < 1:
        raise ValueError("min_per_class must be at least 1")

    counts: Counter[str] = Counter()
    designations: set[str] = set()
    for entry in entries:
        designation = str(entry.get("designation", "")).strip()
        class_name = str(entry.get("class_name", "")).strip()
        if not designation or designation in designations:
            raise ValueError(f"missing or duplicate designation: {designation!r}")
        if class_name not in LABEL_MAP:
            raise ValueError(f"unsupported class for {designation}: {class_name}")
        if int(entry.get("label", -1)) != LABEL_MAP[class_name]:
            raise ValueError(f"label/class mismatch for {designation}")

        observations = entry.get("observations")
        if not isinstance(observations, list) or len(observations) < min_observations:
            raise ValueError(f"insufficient observations for {designation}")
        observation_ids: set[str] = set()
        for observation in observations:
            if not isinstance(observation, dict):
                raise ValueError(f"invalid observation record for {designation}")
            obs_id = str(observation.get("obs_id", "")).strip()
            if not obs_id or obs_id in observation_ids:
                raise ValueError(f"missing or duplicate observation id for {designation}")
            observation_ids.add(obs_id)
            numeric_values = [
                float(observation["ra_deg"]),
                float(observation["dec_deg"]),
                float(observation["jd"]),
                float(observation["mag"]),
            ]
            if not all(math.isfinite(value) for value in numeric_values):
                raise ValueError(f"non-finite observation value for {designation}")
            if not 0.0 <= numeric_values[0] < 360.0 or not -90.0 <= numeric_values[1] <= 90.0:
                raise ValueError(f"invalid coordinates for {designation}")
        if _night_count(observations) < min_nights:
            raise ValueError(f"insufficient observing nights for {designation}")

        designations.add(designation)
        counts[class_name] += 1

    missing = {
        class_name: counts[class_name]
        for class_name in LABEL_MAP
        if counts[class_name] < min_per_class
    }
    if missing:
        raise ValueError(f"five-class minimum not met: {missing}")
    return {
        "entry_count": len(entries),
        "class_counts": dict(sorted(counts.items())),
        "unique_designations": len(designations),
        "min_per_class": min_per_class,
        "min_observations": min_observations,
        "min_nights": min_nights,
        "passed": True,
    }


def grouped_stratified_split(
    entries: list[dict[str, Any]],
    *,
    seed: int = 42,
    train_fraction: float = 0.70,
    calibration_fraction: float = 0.15,
) -> dict[str, list[dict[str, Any]]]:
    """Split each class by designation with deterministic stratification."""
    if train_fraction <= 0 or calibration_fraction <= 0:
        raise ValueError("split fractions must be positive")
    if train_fraction + calibration_fraction >= 1:
        raise ValueError("train and calibration fractions must leave a test split")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        grouped[entry["class_name"]].append(entry)

    rng = random.Random(seed)
    splits: dict[str, list[dict[str, Any]]] = {
        "train": [],
        "calibration": [],
        "test": [],
    }
    for class_name in LABEL_MAP:
        class_entries = sorted(grouped[class_name], key=lambda item: item["designation"])
        if len(class_entries) < 3:
            raise ValueError(f"at least three {class_name} entries are required for splitting")
        rng.shuffle(class_entries)
        count = len(class_entries)
        train_end = max(1, int(count * train_fraction))
        calibration_count = max(1, int(count * calibration_fraction))
        calibration_end = min(count - 1, train_end + calibration_count)
        splits["train"].extend(class_entries[:train_end])
        splits["calibration"].extend(class_entries[train_end:calibration_end])
        splits["test"].extend(class_entries[calibration_end:])

    # This explicit check makes object leakage a hard failure, not a report-only warning.
    designation_sets = {
        name: {entry["designation"] for entry in split_entries}
        for name, split_entries in splits.items()
    }
    if (
        designation_sets["train"] & designation_sets["calibration"]
        or designation_sets["train"] & designation_sets["test"]
        or designation_sets["calibration"] & designation_sets["test"]
    ):
        raise RuntimeError("designation leakage detected across Tier 3 splits")
    return splits


def write_sequence_csv(
    entries: list[dict[str, Any]],
    output_csv: Path,
    max_seq: int = 20,
) -> int:
    """Write validated entries as padded flat Transformer token rows."""
    if max_seq < 2:
        raise ValueError("max_seq must be at least 2")
    token_header = [
        f"tok_{index}_{feature}"
        for index in range(max_seq)
        for feature in range(_N_FEATURES)
    ]
    header = ["designation", "class_name", *token_header, "label"]
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for entry in entries:
            observations = sorted(
                entry.get("observations", []),
                key=lambda observation: observation.get("jd", 0.0),
            )
            t0 = float(observations[0].get("jd", 0.0)) if observations else 0.0
            row: dict[str, str] = {column: "0.0" for column in token_header}
            row.update(
                {
                    "designation": str(entry.get("designation", "")),
                    "class_name": str(entry.get("class_name", "")),
                    "label": str(int(entry.get("label", 0))),
                }
            )
            for index, observation in enumerate(observations[:max_seq]):
                for feature, value in enumerate(_obs_to_token(observation, t0)):
                    row[f"tok_{index}_{feature}"] = f"{value:.6f}"
            writer.writerow(row)
    return len(entries)


def build_sequence_dataset(input_json: Path, output_csv: Path, max_seq: int = 20) -> int:
    """Preserve the legacy one-input conversion API used by existing callers."""
    entries, _metadata = _load_envelope(input_json)
    return write_sequence_csv(entries, output_csv, max_seq)


def prepare_sequence_splits(
    input_paths: list[Path],
    output_dir: Path,
    *,
    min_per_class: int,
    max_seq: int = 20,
    seed: int = 42,
) -> dict[str, Any]:
    """Merge real acquisitions, validate policy, and emit grouped model splits."""
    entries: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for path in input_paths:
        loaded_entries, metadata = _load_envelope(path)
        safety = metadata.get("safety", {})
        if metadata.get("schema_version") == "legacy-list" or not metadata.get("source"):
            raise ValueError(f"missing acquisition provenance: {path}")
        if not safety or (
            safety.get("external_submission_enabled") is not False
            or safety.get("impact_probability_generated") is not False
            or safety.get("secret_values_recorded") is not False
        ):
            raise ValueError(f"unsafe acquisition envelope: {path}")
        entries.extend(loaded_entries)
        sources.append(
            {
                "path": str(path),
                "sha256": _sha256_file(path),
                **metadata,
            }
        )

    validation = validate_entries(entries, min_per_class=min_per_class)
    splits = grouped_stratified_split(entries, seed=seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    split_counts: dict[str, dict[str, int]] = {}
    for split_name, split_entries in splits.items():
        write_sequence_csv(split_entries, output_dir / f"{split_name}.csv", max_seq)
        split_counts[split_name] = dict(
            sorted(Counter(entry["class_name"] for entry in split_entries).items())
        )

    report = {
        "schema_version": PREPARATION_SCHEMA_VERSION,
        "created_at_utc": _utc_now(),
        "approved_policy": {
            "approved_by": "Jerome W. Lindsey III",
            "approved_at": "2026-06-10",
            "pilot_sequences_per_class": 50,
            "production_minimum_sequences_per_class": 200,
        },
        "validation": validation,
        "split_seed": seed,
        "max_sequence_length": max_seq,
        "split_class_counts": split_counts,
        "source_datasets": sources,
        "safety": {
            "external_submission_enabled": False,
            "impact_probability_generated": False,
            "secret_values_recorded": False,
        },
        "pilot_only": min_per_class < 200,
        "production_promotion_allowed": False,
    }
    (output_dir / "preparation_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return report


def main() -> None:
    """Parse legacy conversion or approved five-class preparation mode."""
    parser = argparse.ArgumentParser(
        description="Validate, split, and tokenize Tier 3 sequence datasets."
    )
    parser.add_argument("--input", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, help="Legacy single CSV output")
    parser.add_argument("--output-dir", type=Path, help="Validated split output directory")
    parser.add_argument("--max-seq", type=int, default=20)
    parser.add_argument("--min-per-class", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if bool(args.output) == bool(args.output_dir):
        parser.error("choose exactly one of --output or --output-dir")
    if args.output:
        if len(args.input) != 1:
            parser.error("legacy --output mode accepts exactly one input")
        count = build_sequence_dataset(args.input[0], args.output, args.max_seq)
        print(f"Wrote {count} sequences -> {args.output}")
        return

    report = prepare_sequence_splits(
        args.input,
        args.output_dir,
        min_per_class=args.min_per_class,
        max_seq=args.max_seq,
        seed=args.seed,
    )
    print(json.dumps(report["split_class_counts"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
