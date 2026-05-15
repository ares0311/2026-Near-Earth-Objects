#!/usr/bin/env python
"""Validate MPC 80-column observation reports for format correctness.

Reads an MPC-formatted report file and checks each observation line for:
  - Exactly 80 characters
  - Parseable date field (cols 15–32)
  - Parseable RA field (cols 33–44)
  - Parseable Dec field (cols 45–56)
  - Non-empty observatory code (cols 78–80)

Exits 0 if all checks pass, 1 if any line fails.

Usage:
    PYTHONPATH=src python Skills/validate_mpc_report.py report.txt
    PYTHONPATH=src python Skills/validate_mpc_report.py --json report.txt
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_DATE_RE = re.compile(r"^\d{4} \d{2} \d{2}\.\d+$")
_RA_RE = re.compile(r"^\d{2} \d{2} \d{2}\.\d+$")
_DEC_RE = re.compile(r"^[+-]\d{2} \d{2} \d{2}\.\d+$")


def _is_header(line: str) -> bool:
    """Return True for MPC report header/comment lines (non-observation)."""
    return len(line.strip()) == 0 or line[:3] in {"COD", "OBS", "MEA", "TEL", "ACK", "NET"}


def validate_observation_line(line: str) -> list[str]:
    """Return list of error strings for a single 80-column observation line.

    Empty list means the line is valid.
    """
    errors: list[str] = []

    if len(line) != 80:
        errors.append(f"Expected 80 chars, got {len(line)}")
        return errors  # further checks assume correct length

    date_field = line[14:32].strip()
    if not _DATE_RE.match(date_field):
        errors.append(f"Date field (cols 15-32) not parseable: {date_field!r}")

    ra_field = line[32:44].strip()
    if not _RA_RE.match(ra_field):
        errors.append(f"RA field (cols 33-44) not parseable: {ra_field!r}")

    dec_field = line[44:56].strip()
    if not _DEC_RE.match(dec_field):
        errors.append(f"Dec field (cols 45-56) not parseable: {dec_field!r}")

    obs_code = line[77:80].strip()
    if not obs_code:
        errors.append("Observatory code (cols 78-80) is blank")

    return errors


def validate_report(path: Path) -> dict:
    """Validate all observation lines in a report file.

    Returns a dict with keys:
      ``valid``          — bool, True iff all observation lines pass
      ``n_obs_lines``    — int, number of observation lines checked
      ``n_header_lines`` — int, number of header/blank lines skipped
      ``errors``         — list of dicts {line_number, line, errors}
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    results: list[dict] = []
    n_obs = 0
    n_header = 0

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.rstrip("\n")
        if _is_header(line):
            n_header += 1
            continue
        n_obs += 1
        errs = validate_observation_line(line)
        if errs:
            results.append({"line_number": lineno, "line": line, "errors": errs})

    return {
        "valid": len(results) == 0,
        "n_obs_lines": n_obs,
        "n_header_lines": n_header,
        "errors": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate MPC 80-column observation reports")
    parser.add_argument("report", type=Path, help="Path to MPC report file")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    if not args.report.exists():
        print(f"ERROR: File not found: {args.report}", file=sys.stderr)
        sys.exit(1)

    result = validate_report(args.report)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = "PASS" if result["valid"] else "FAIL"
        print(f"{status}  {args.report}  ({result['n_obs_lines']} obs lines, "
              f"{result['n_header_lines']} header lines)")
        for err_entry in result["errors"]:
            print(f"  Line {err_entry['line_number']}: {'; '.join(err_entry['errors'])}")
            print(f"    > {err_entry['line']!r}")

    sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
