#!/usr/bin/env python
"""Deprecated wrapper; use `Skills/background.py human-signoff-summary`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from background import DEFAULT_DB_PATH, human_signoff_summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize background human signoffs")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()
    print(json.dumps(human_signoff_summary(args.db), indent=2))


if __name__ == "__main__":
    main()
