#!/usr/bin/env python3
"""Validate Astrometrics grouped train/validation/test split leakage.

This checks A4 without acquiring data: rows must include enough context to
derive object, night, sky-cell, and source/instrument grouping evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from grouped_splits import leakage_report, records_from_csv


def main() -> int:
    """Parse CLI arguments, print a JSON report, and fail on hard leakage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="CSV with split and grouping columns")
    parser.add_argument("--cell-degrees", type=float, default=1.0, help="RA/Dec sky-cell size")
    args = parser.parse_args()

    records = records_from_csv(args.csv_path, cell_degrees=args.cell_degrees)
    report = leakage_report(records)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
