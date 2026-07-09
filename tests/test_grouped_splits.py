from __future__ import annotations

import csv
import json
import os
import subprocess
from pathlib import Path

import pytest

from grouped_splits import (
    assert_no_leakage,
    assign_grouped_splits,
    leakage_report,
    record_from_row,
    records_from_csv,
)


def _row(
    sample_id: str,
    split: str,
    object_id: str,
    jd: float,
    ra: float,
    dec: float,
) -> dict[str, object]:
    """Build one policy-complete split row."""
    return {
        "sample_id": sample_id,
        "split": split,
        "label": "neo_candidate",
        "object_id": object_id,
        "jd": jd,
        "ra_deg": ra,
        "dec_deg": dec,
        "survey": "ZTF",
        "instrument": "ZTF",
    }


def test_record_from_row_derives_group_keys() -> None:
    record = record_from_row(_row("s1", "train", "obj-a", 2460000.5, 11.2, -3.4))

    assert record.sample_id == "s1"
    assert record.night_key == "jdnight:2460001"
    assert record.sky_cell == "sky:1:11:86"
    assert record.source_key == "ZTF:ZTF"


def test_record_from_row_accepts_explicit_group_keys_and_mjd() -> None:
    explicit = record_from_row({
        "candidate_id": "s-explicit",
        "split_name": "TRAIN",
        "class_name": "artifact",
        "target_id": "obj-explicit",
        "night": "night-a",
        "field_id": "field-a",
        "source_id": "source-a",
    })
    mjd = record_from_row({
        "obs_id": "s-mjd",
        "partition": "validation",
        "class": "neo_candidate",
        "designation": "obj-mjd",
        "mjd": 60000.0,
        "ra": 359.9,
        "dec": -89.9,
        "mission": "WISE",
    })

    assert explicit.split == "train"
    assert explicit.night_key == "night-a"
    assert explicit.sky_cell == "field-a"
    assert explicit.source_key == "source-a"
    assert mjd.night_key == "jdnight:2460001"
    assert mjd.sky_cell == "sky:1:359:0"
    assert mjd.source_key == "WISE"


def test_record_from_row_fails_missing_or_invalid_group_fields() -> None:
    with pytest.raises(ValueError, match="night_key"):
        record_from_row({
            "sample_id": "s-missing-night",
            "split": "train",
            "label": "neo_candidate",
            "object_id": "obj-a",
            "ra_deg": 1.0,
            "dec_deg": 2.0,
        })
    with pytest.raises(ValueError, match="sky_cell"):
        record_from_row({
            "sample_id": "s-missing-sky",
            "split": "train",
            "label": "neo_candidate",
            "object_id": "obj-a",
            "jd": 2460000.5,
        })
    with pytest.raises(ValueError, match="cell_degrees must be positive"):
        record_from_row(_row("s1", "train", "obj-a", 2460000.5, 1.0, 2.0), cell_degrees=0)


def test_leakage_report_passes_isolated_hard_groups() -> None:
    records = [
        record_from_row(_row("s1", "train", "obj-a", 2460000.5, 11.2, -3.4)),
        record_from_row(_row("s2", "validation", "obj-b", 2460001.5, 13.2, -1.4)),
        record_from_row(_row("s3", "test", "obj-c", 2460002.5, 15.2, 1.4)),
    ]

    report = leakage_report(records)

    assert report["passed"] is True
    assert report["hard_leakage"] == {}
    assert report["context_overlap"]["source_key"] == {"ZTF:ZTF": ["test", "train", "validation"]}
    assert assert_no_leakage(records)["passed"] is True


def test_leakage_report_fails_object_overlap() -> None:
    records = [
        record_from_row(_row("s1", "train", "obj-a", 2460000.5, 11.2, -3.4)),
        record_from_row(_row("s2", "validation", "obj-a", 2460001.5, 13.2, -1.4)),
        record_from_row(_row("s3", "test", "obj-c", 2460002.5, 15.2, 1.4)),
    ]

    report = leakage_report(records)

    assert report["passed"] is False
    assert report["hard_leakage"]["object_id"] == {"obj-a": ["train", "validation"]}


def test_leakage_report_fails_night_overlap() -> None:
    records = [
        record_from_row(_row("s1", "train", "obj-a", 2460000.5, 11.2, -3.4)),
        record_from_row(_row("s2", "validation", "obj-b", 2460000.6, 13.2, -1.4)),
        record_from_row(_row("s3", "test", "obj-c", 2460002.5, 15.2, 1.4)),
    ]

    with pytest.raises(ValueError, match="night_key"):
        assert_no_leakage(records)


def test_leakage_report_fails_empty_and_missing_required_split() -> None:
    with pytest.raises(ValueError, match="at least one split record"):
        leakage_report([])

    records = [
        record_from_row(_row("s1", "train", "obj-a", 2460000.5, 11.2, -3.4)),
        record_from_row(_row("s2", "validation", "obj-b", 2460001.5, 13.2, -1.4)),
    ]

    report = leakage_report(records)

    assert report["passed"] is False
    assert report["missing_required_splits"] == ["test"]


def test_records_from_csv_and_cli_report(tmp_path: Path) -> None:
    csv_path = tmp_path / "splits.csv"
    rows = [
        _row("s1", "train", "obj-a", 2460000.5, 11.2, -3.4),
        _row("s2", "validation", "obj-b", 2460001.5, 13.2, -1.4),
        _row("s3", "test", "obj-c", 2460002.5, 15.2, 1.4),
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    assert len(records_from_csv(csv_path)) == 3

    result = subprocess.run(
        [
            "uv",
            "run",
            "--no-sync",
            "--python",
            "3.14",
            "python",
            "Skills/validate_grouped_splits.py",
            str(csv_path),
        ],
        check=True,
        capture_output=True,
        env={**os.environ, "UV_CACHE_DIR": ".uv-cache"},
        text=True,
    )

    report = json.loads(result.stdout)
    assert report["passed"] is True


def test_assign_grouped_splits_keeps_objects_together() -> None:
    rows = [
        {"sample_id": f"{object_id}-{index}", "object_id": object_id, "label": "x"}
        for object_id in ("a", "b", "c", "d", "e", "f")
        for index in range(2)
    ]

    assigned = assign_grouped_splits(rows, seed=7, train_fraction=0.5, validation_fraction=0.25)

    splits_by_object: dict[str, set[str]] = {}
    for row in assigned:
        splits_by_object.setdefault(str(row["object_id"]), set()).add(str(row["split"]))
    assert all(len(splits) == 1 for splits in splits_by_object.values())
    assert {row["split"] for row in assigned} == {"train", "validation", "test"}


def test_assign_grouped_splits_rejects_invalid_inputs() -> None:
    rows = [{"sample_id": "s1", "object_id": "a"}]

    with pytest.raises(ValueError, match="split fractions must be positive"):
        assign_grouped_splits(rows, train_fraction=0, validation_fraction=0.2)
    with pytest.raises(ValueError, match="leave a test split"):
        assign_grouped_splits(rows, train_fraction=0.8, validation_fraction=0.2)
    with pytest.raises(ValueError, match="missing grouping field"):
        assign_grouped_splits([{"sample_id": "s1"}])
    with pytest.raises(ValueError, match="at least three groups"):
        assign_grouped_splits(rows)
