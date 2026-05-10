#!/usr/bin/env python
"""Deprecated wrapper; use `Skills/background.py record-signoff`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from background import DEFAULT_DB_PATH, record_human_signoff


def main() -> None:
    parser = argparse.ArgumentParser(description="Record background human signoff")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument(
        "--decision",
        required=True,
        choices=["approved_for_internal_review", "needs_more_work", "rejected"],
    )
    parser.add_argument("--scope", required=True)
    parser.add_argument("--notes", default="")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()

    entry = record_human_signoff(
        run_id=args.run_id,
        target_id=args.target_id,
        reviewer=args.reviewer,
        decision=args.decision,
        scope=args.scope,
        notes=args.notes,
        db_path=args.db,
    )
    print(entry.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
