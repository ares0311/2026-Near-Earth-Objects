#!/usr/bin/env python
"""Deprecated wrapper; use `Skills/background.py needs-follow-up-summary`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from background import DEFAULT_DB_PATH, needs_follow_up_summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize background needs-follow-up log")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()
    print(json.dumps(needs_follow_up_summary(args.db), indent=2))


if __name__ == "__main__":
    main()
