"""Grouped split and leakage checks for Astrometrics model promotion.

The A4 production gate requires model/eval splits to be audited by correlated
astronomical context, not just random rows. This module keeps that audit small
and data-format agnostic so CSV-producing Skills can reuse it.
"""

from __future__ import annotations

import csv
import json
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_SPLITS = ("train", "validation", "test")
DEFAULT_HARD_GROUPS = ("object_id", "night_key", "sky_cell")
DEFAULT_CONTEXT_GROUPS = ("source_key",)


@dataclass(frozen=True)
class SplitRecord:
    """One candidate, observation, or derived sample with split context."""

    sample_id: str
    split: str
    label: str
    object_id: str
    night_key: str
    sky_cell: str
    source_key: str


def _first_non_empty(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    """Return the first populated field from a row, or an empty string."""
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _night_key(row: dict[str, Any]) -> str:
    """Derive a stable observing-night key from JD/MJD/night fields."""
    explicit = _first_non_empty(row, ("night_key", "night", "obs_night"))
    if explicit:
        return explicit
    jd_raw = _first_non_empty(row, ("jd", "obsjd", "mjd"))
    if not jd_raw:
        return ""
    jd = float(jd_raw)
    if "mjd" in row and not _first_non_empty(row, ("jd", "obsjd")):
        jd += 2400000.5
    return f"jdnight:{int(math.floor(jd + 0.5))}"


def _sky_cell(row: dict[str, Any], cell_degrees: float) -> str:
    """Quantize RA/Dec into a leakage-relevant sky-region cell."""
    explicit = _first_non_empty(row, ("sky_cell", "field_id", "field"))
    if explicit:
        return explicit
    ra_raw = _first_non_empty(row, ("ra_deg", "ra", "raMean"))
    dec_raw = _first_non_empty(row, ("dec_deg", "dec", "decMean"))
    if not ra_raw or not dec_raw:
        return ""
    if cell_degrees <= 0:
        raise ValueError("cell_degrees must be positive")
    ra_bin = int(math.floor((float(ra_raw) % 360.0) / cell_degrees))
    dec_bin = int(math.floor((float(dec_raw) + 90.0) / cell_degrees))
    return f"sky:{cell_degrees:g}:{ra_bin}:{dec_bin}"


def _source_key(row: dict[str, Any]) -> str:
    """Build the survey/instrument context key required by A4."""
    explicit = _first_non_empty(row, ("source_key", "source_id"))
    if explicit:
        return explicit
    survey = _first_non_empty(row, ("survey", "mission", "source_name"))
    instrument = _first_non_empty(row, ("instrument", "camera", "detector"))
    if survey and instrument:
        return f"{survey}:{instrument}"
    return survey or instrument


def record_from_row(row: dict[str, Any], *, cell_degrees: float = 1.0) -> SplitRecord:
    """Normalize one CSV/JSON row into the grouped-split audit contract."""
    sample_id = _first_non_empty(row, ("sample_id", "candidate_id", "obs_id", "designation"))
    object_id = _first_non_empty(row, ("object_id", "designation", "target_id"))
    split = _first_non_empty(row, ("split", "split_name", "partition")).lower()
    label = _first_non_empty(row, ("label", "class_name", "class"))
    record = SplitRecord(
        sample_id=sample_id,
        split=split,
        label=label,
        object_id=object_id,
        night_key=_night_key(row),
        sky_cell=_sky_cell(row, cell_degrees),
        source_key=_source_key(row),
    )
    missing = [
        field
        for field in ("sample_id", "split", "label", "object_id", "night_key", "sky_cell")
        if not getattr(record, field)
    ]
    if missing:
        raise ValueError(f"split row missing required grouped fields: {', '.join(missing)}")
    return record


def records_from_csv(path: Path, *, cell_degrees: float = 1.0) -> list[SplitRecord]:
    """Load a CSV split table and normalize each row for leakage checks."""
    with path.open(newline="", encoding="utf-8") as handle:
        return [record_from_row(row, cell_degrees=cell_degrees) for row in csv.DictReader(handle)]


def _group_overlap(records: list[SplitRecord], field: str) -> dict[str, list[str]]:
    """Map each group value that appears in more than one split."""
    split_by_value: dict[str, set[str]] = defaultdict(set)
    for record in records:
        split_by_value[str(getattr(record, field))].add(record.split)
    return {
        value: sorted(splits)
        for value, splits in sorted(split_by_value.items())
        if len(splits) > 1
    }


def leakage_report(
    records: list[SplitRecord],
    *,
    hard_groups: tuple[str, ...] = DEFAULT_HARD_GROUPS,
    context_groups: tuple[str, ...] = DEFAULT_CONTEXT_GROUPS,
) -> dict[str, Any]:
    """Return a fail-closed grouped-split leakage report."""
    if not records:
        raise ValueError("at least one split record is required")

    split_counts: dict[str, int] = defaultdict(int)
    label_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for record in records:
        split_counts[record.split] += 1
        label_counts[record.split][record.label] += 1

    missing_splits = [split for split in REQUIRED_SPLITS if split_counts.get(split, 0) == 0]
    hard_violations = {
        field: overlap for field in hard_groups if (overlap := _group_overlap(records, field))
    }
    context_overlaps = {
        field: overlap
        for field in context_groups
        if (overlap := _group_overlap(records, field))
    }
    context_unique_counts = {
        field: len({str(getattr(record, field)) for record in records if getattr(record, field)})
        for field in context_groups
    }
    warnings = [
        f"{field}: only one value present; source-diversity split is not testable"
        for field, count in context_unique_counts.items()
        if count <= 1
    ]
    passed = not missing_splits and not hard_violations
    return {
        "schema_version": "grouped-split-leakage-v1",
        "passed": passed,
        "n_records": len(records),
        "split_counts": dict(sorted(split_counts.items())),
        "label_counts": {
            split: dict(sorted(counts.items()))
            for split, counts in label_counts.items()
        },
        "hard_groups": list(hard_groups),
        "context_groups": list(context_groups),
        "missing_required_splits": missing_splits,
        "hard_leakage": hard_violations,
        "context_overlap": context_overlaps,
        "warnings": warnings,
    }


def assert_no_leakage(records: list[SplitRecord]) -> dict[str, Any]:
    """Raise ValueError when hard grouped split leakage is present."""
    report = leakage_report(records)
    if not report["passed"]:
        raise ValueError(json.dumps(report, sort_keys=True))
    return report


def assign_grouped_splits(
    rows: list[dict[str, Any]],
    *,
    seed: int = 42,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
    group_field: str = "object_id",
) -> list[dict[str, Any]]:
    """Assign rows to train/validation/test by one stable hard group field."""
    if train_fraction <= 0 or validation_fraction <= 0:
        raise ValueError("split fractions must be positive")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("train and validation fractions must leave a test split")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = str(row.get(group_field, "")).strip()
        if not key:
            raise ValueError(f"missing grouping field: {group_field}")
        grouped[key].append(dict(row))
    if len(grouped) < 3:
        raise ValueError("at least three groups are required for train/validation/test")

    groups = sorted(grouped)
    random.Random(seed).shuffle(groups)
    train_end = max(1, int(len(groups) * train_fraction))
    validation_count = max(1, int(len(groups) * validation_fraction))
    validation_end = min(len(groups) - 1, train_end + validation_count)
    split_by_group = {
        group: "train"
        for group in groups[:train_end]
    } | {
        group: "validation"
        for group in groups[train_end:validation_end]
    } | {
        group: "test"
        for group in groups[validation_end:]
    }

    assigned: list[dict[str, Any]] = []
    for group in groups:
        for row in grouped[group]:
            row["split"] = split_by_group[group]
            assigned.append(row)
    return assigned
