"""Compute combined priority scores for scored NEO candidates.

Usage
-----
    python Skills/compute_combined_priority.py data/sample_tracklets.json

    python Skills/compute_combined_priority.py data/sample_tracklets.json \\
        --threshold 0.3 --sort --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Compute combined priority scores for scored NEO candidates."
    )
    parser.add_argument("input", help="Path to scored-NEO JSON file")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.0,
        help="Minimum combined priority to include in output (default: 0.0)",
    )
    parser.add_argument(
        "--sort",
        action="store_true",
        help="Sort output by combined priority descending",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output as JSON array",
    )
    args = parser.parse_args(argv)

    try:
        from schemas import ScoredNEO
        from score import compute_combined_priority

        with open(args.input) as f:
            raw = json.load(f)

        if isinstance(raw, dict):
            raw = [raw]

        rows = []
        for item in raw:
            try:
                neo = ScoredNEO(**item)
            except Exception:
                continue
            cp = compute_combined_priority(neo)
            if cp >= args.threshold:
                rows.append({
                    "object_id": neo.tracklet.object_id,
                    "combined_priority": cp,
                    "hazard_flag": neo.hazard.hazard_flag,
                    "alert_pathway": neo.hazard.alert_pathway,
                })

        if args.sort:
            rows.sort(key=lambda r: -r["combined_priority"])

        if args.as_json:
            print(json.dumps(rows, indent=2))
            sys.exit(0)

        if not rows:
            print("No candidates above threshold.")
            sys.exit(0)

        hdr = f"{'object_id':<20} {'combined':>8} {'flag':<16} {'pathway':<22}"
        print(hdr)
        print("-" * len(hdr))
        for row in rows:
            print(
                f"{row['object_id']:<20} {row['combined_priority']:>8.4f}"
                f" {row['hazard_flag']:<16} {row['alert_pathway']:<22}"
            )
        sys.exit(0)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
