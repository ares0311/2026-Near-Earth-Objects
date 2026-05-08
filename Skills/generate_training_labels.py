#!/usr/bin/env python
"""Download MPC NEO + MBA catalog entries and write a training label CSV.

Outputs a CSV with columns: designation, neo_class, h_mag, source
suitable for training the Tier 1 XGBoost classifier.

Usage:
    PYTHONPATH=src python Skills/generate_training_labels.py [--output labels.csv] [--limit 500]
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def fetch_neo_labels(limit: int = 500) -> list[dict]:
    """Fetch confirmed NEO designations from astroquery.mpc."""
    try:
        from astroquery.mpc import MPC  # type: ignore[import]

        result = MPC.query_objects(object_type="N", limit=limit, return_astropy_table=True)
        rows = []
        for row in result:
            rows.append(
                {
                    "designation": str(row.get("designation", row.get("number", "unknown"))),
                    "neo_class": "neo_candidate",
                    "h_mag": float(row.get("absolute_magnitude", 99.0)),
                    "source": "MPC_NEO",
                }
            )
        return rows
    except Exception as e:
        print(f"Warning: could not fetch NEO labels from MPC: {e}", file=sys.stderr)
        return []


def fetch_mba_labels(limit: int = 500) -> list[dict]:
    """Fetch MBA designations from astroquery.mpc as negative labels."""
    try:
        from astroquery.mpc import MPC  # type: ignore[import]

        result = MPC.query_objects(object_type="A", limit=limit, return_astropy_table=True)
        rows = []
        for row in result:
            h = float(row.get("absolute_magnitude", 99.0))
            # Only include MBAs with H > 15 (avoids overlap with large NEOs)
            if h < 15:
                continue
            rows.append(
                {
                    "designation": str(row.get("designation", row.get("number", "unknown"))),
                    "neo_class": "main_belt_asteroid",
                    "h_mag": h,
                    "source": "MPC_MBA",
                }
            )
        return rows
    except Exception as e:
        print(f"Warning: could not fetch MBA labels from MPC: {e}", file=sys.stderr)
        return []


def write_csv(rows: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["designation", "neo_class", "h_mag", "source"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download MPC training labels")
    parser.add_argument("--output", type=Path, default=Path("data/training_labels.csv"))
    parser.add_argument("--limit", type=int, default=500, help="Max objects per class")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print counts without writing file"
    )
    args = parser.parse_args()

    print(f"Fetching up to {args.limit} NEOs from MPC...")
    neo_rows = fetch_neo_labels(limit=args.limit)
    print(f"  → {len(neo_rows)} NEO labels")

    print(f"Fetching up to {args.limit} MBAs from MPC...")
    mba_rows = fetch_mba_labels(limit=args.limit)
    print(f"  → {len(mba_rows)} MBA labels")

    all_rows = neo_rows + mba_rows
    print(f"Total: {len(all_rows)} labeled objects")

    if args.dry_run:
        print("Dry run — no file written.")
        return

    write_csv(all_rows, args.output)
    print(f"Written to {args.output}")


if __name__ == "__main__":
    main()
