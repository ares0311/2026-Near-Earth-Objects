"""Estimate survey field completeness from a FetchResult JSON file."""

from __future__ import annotations

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Estimate survey field completeness from a FetchResult JSON file."
    )
    parser.add_argument("input", help="Path to JSON file containing a FetchResult dict.")
    parser.add_argument(
        "--limiting-mag",
        type=float,
        default=None,
        help="Explicit field limiting magnitude (default: derived from data).",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON instead of plain text.")
    args = parser.parse_args()

    try:
        with open(args.input) as fh:
            data = json.load(fh)
    except Exception as exc:
        print(f"ERROR: could not read {args.input}: {exc}", file=sys.stderr)
        sys.exit(1)

    sys.path.insert(0, "src")
    try:
        from fetch import estimate_field_completeness, estimate_survey_depth
        from schemas import FetchResult
    except ImportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        fr = FetchResult.model_validate(data)
    except Exception as exc:
        print(f"ERROR: could not parse FetchResult: {exc}", file=sys.stderr)
        sys.exit(1)

    completeness = estimate_field_completeness(fr, limiting_mag=args.limiting_mag)
    lim = args.limiting_mag if args.limiting_mag is not None else estimate_survey_depth(fr)
    n_alerts = len(fr.alerts)

    if args.json:
        print(json.dumps({
            "n_alerts": n_alerts,
            "limiting_mag": lim,
            "completeness": completeness,
        }, indent=2))
    else:
        print(f"Alerts        : {n_alerts}")
        print(f"Limiting mag  : {lim if lim is not None else 'unknown'}")
        print(f"Completeness  : {completeness:.4f}  ({completeness * 100:.1f}%)")

    sys.exit(0)


if __name__ == "__main__":
    main()
