"""Regression tests for Skills/build_cutout_dataset.py.

Covers the A4 grouped-split provenance columns added alongside
Skills/download_ztf_training_alerts.py's field-capturing fix, and confirms
the legacy no-provenance path (older labeled_alerts.json files without
object_id/jd/ra/dec) still produces a valid two-column CSV.
"""

from __future__ import annotations

import base64
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))

from build_cutout_dataset import build_cutout_dataset  # noqa: E402


def _cutout_b64() -> str:
    arr = np.zeros((63, 63), dtype=np.float32)
    return base64.b64encode(arr.tobytes()).decode("ascii")


def test_legacy_entries_without_provenance_produce_two_column_csv(tmp_path):
    input_json = tmp_path / "alerts.json"
    input_json.write_text(
        json.dumps(
            [
                {
                    "label": 0,
                    "observations": [
                        {
                            "cutout_science": _cutout_b64(),
                            "cutout_reference": _cutout_b64(),
                            "cutout_difference": _cutout_b64(),
                        }
                    ],
                }
            ]
        )
    )
    output_dir = tmp_path / "cutouts"
    csv_path = tmp_path / "index.csv"

    n = build_cutout_dataset(input_json, output_dir, csv_path)

    assert n == 1
    with csv_path.open() as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert reader.fieldnames == ["cutout_path", "label"]
    assert rows[0]["label"] == "0"


def test_entries_with_provenance_populate_grouped_split_columns(tmp_path):
    input_json = tmp_path / "alerts.json"
    input_json.write_text(
        json.dumps(
            [
                {
                    "label": 0,
                    "object_id": "ZTF20aaa",
                    "candid": 12345,
                    "jd": 2459123.75,
                    "ra": 232.6,
                    "dec": -8.4,
                    "observations": [
                        {
                            "cutout_science": _cutout_b64(),
                            "cutout_reference": _cutout_b64(),
                            "cutout_difference": _cutout_b64(),
                        }
                    ],
                }
            ]
        )
    )
    output_dir = tmp_path / "cutouts"
    csv_path = tmp_path / "index.csv"

    n = build_cutout_dataset(input_json, output_dir, csv_path)

    assert n == 1
    with csv_path.open() as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert set(reader.fieldnames) == {
        "cutout_path",
        "label",
        "candidate_id",
        "object_id",
        "jd",
        "ra_deg",
        "dec_deg",
        "source_key",
    }
    row = rows[0]
    assert row["object_id"] == "ZTF20aaa"
    assert row["candidate_id"] == "12345"
    assert row["jd"] == "2459123.75"
    assert row["ra_deg"] == "232.6"
    assert row["dec_deg"] == "-8.4"
    assert row["source_key"] == "ZTF:P48"


def test_invalid_cutouts_are_skipped(tmp_path):
    input_json = tmp_path / "alerts.json"
    input_json.write_text(
        json.dumps(
            [
                {
                    "label": 0,
                    "observations": [
                        {
                            "cutout_science": "not-valid-base64-data!!",
                            "cutout_reference": _cutout_b64(),
                            "cutout_difference": _cutout_b64(),
                        }
                    ],
                }
            ]
        )
    )
    output_dir = tmp_path / "cutouts"
    csv_path = tmp_path / "index.csv"

    n = build_cutout_dataset(input_json, output_dir, csv_path)

    assert n == 0
