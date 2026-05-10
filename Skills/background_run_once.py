#!/usr/bin/env python
"""Deprecated wrapper; use `Skills/background.py run-once`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from background import DEFAULT_CONFIG_PATH, background_run_once


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one bounded background search")
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args()

    result = background_run_once(
        input_path=args.input,
        db_path=args.db,
        report_dir=args.report_dir,
        config_path=args.config,
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
