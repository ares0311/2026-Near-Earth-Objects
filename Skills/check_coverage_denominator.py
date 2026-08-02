#!/usr/bin/env python3
"""Assert the coverage denominator is what it claims to be (contract CLAIM-02).

Two separate guarantees, deliberately not collapsed into one number:

1. **Every ``src/`` module stays at 100% statement coverage.** This is the
   guarantee the repository has always carried. It must survive the move to a
   larger production denominator rather than being diluted by it.

2. **The production runtime denominator is reported honestly.** The aggregate
   percentage is printed alongside the exact statement counts and an itemised
   list of every production module below 100%, so no reader has to infer what
   "production coverage" meant.

Field blocker NEO-FIELD-02 was the absence of exactly this: coverage was measured
against ``src/`` alone while the canonical orchestrator (``Skills/hunter_cli.py``)
and the operator shell (``Skills/hunter_shell.py``) ran unmeasured, and the
result was presented as full production coverage.

Usage::

    uv run python Skills/check_coverage_denominator.py coverage-production.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "report",
        type=Path,
        help="coverage.py JSON report covering the production denominator",
    )
    args = parser.parse_args(argv)

    if not args.report.is_file():
        print(f"[coverage-denominator] FAIL -- report not found: {args.report}")
        return 1

    data = json.loads(args.report.read_text())
    files = data.get("files", {})
    if not files:
        # An empty report is not a pass. It means the measurement did not happen,
        # which contract rule CLAIM-03 classifies as NOT EXECUTED.
        print("[coverage-denominator] FAIL -- report contains no measured files (NOT EXECUTED)")
        return 1

    src_below: list[tuple[str, float, int]] = []
    production_below: list[tuple[str, float, int]] = []
    total_statements = 0
    total_missing = 0

    for name, record in sorted(files.items()):
        summary = record["summary"]
        statements = summary["num_statements"]
        missing = summary["missing_lines"]
        percent = summary["percent_covered"]
        total_statements += statements
        total_missing += missing

        normalized = name.replace("\\", "/")
        if missing:
            entry = (normalized, percent, missing)
            production_below.append(entry)
            if normalized.startswith("src/"):
                src_below.append(entry)

    covered = total_statements - total_missing
    aggregate = 100.0 * covered / total_statements if total_statements else 0.0

    print("[coverage-denominator] production runtime denominator")
    print(f"  measured files      {len(files)}")
    print(f"  statements          {total_statements}")
    print(f"  covered             {covered}")
    print(f"  missing             {total_missing}")
    print(f"  aggregate           {aggregate:.2f}%")

    if production_below:
        print("  below 100%:")
        for name, percent, missing in production_below:
            print(f"    {name:<34} {percent:6.2f}%  {missing} uncovered statement(s)")

    if src_below:
        print()
        print(f"[coverage-denominator] FAIL -- {len(src_below)} src/ module(s) below 100%:")
        for name, percent, missing in src_below:
            print(f"  - {name} at {percent:.2f}% ({missing} uncovered)")
        return 1

    print()
    print(
        "[coverage-denominator] PASS -- every src/ module is at 100%; the aggregate "
        f"above is {aggregate:.2f}% of the full production runtime, not of src/ alone."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
