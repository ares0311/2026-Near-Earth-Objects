#!/usr/bin/env python
"""Deprecated wrapper; use `Skills/background.py target-priority-summary`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from background import DEFAULT_DB_PATH, DEFAULT_INPUT_PATH, target_priority_summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize background target priorities")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()
    print(json.dumps(target_priority_summary(args.input, args.db), indent=2))


if __name__ == "__main__":
    main()
