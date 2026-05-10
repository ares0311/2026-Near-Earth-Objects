#!/usr/bin/env python
"""Deprecated wrapper; use `Skills/background.py ledger-summary`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from background import DEFAULT_DB_PATH, ledger_summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize background run ledger")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()
    print(json.dumps(ledger_summary(args.db), indent=2))


if __name__ == "__main__":
    main()
