"""
generate_followup_lists.py — Generate follow-up priority lists for NEO candidates.

Reads scored NEO JSON from --input, calls generate_followup_priority_list from
alert, and prints the result as a table or JSON.

Usage:
    python Skills/generate_followup_lists.py --input data/scored_neos.json
    python Skills/generate_followup_lists.py --input data/scored_neos.json --max-items 5
    python Skills/generate_followup_lists.py --input data/scored_neos.json --json

Exit 0 on success.
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "src"))

from alert import generate_followup_priority_list  # noqa: E402
from schemas import ScoredNEO  # noqa: E402


def _load_neos(path: str) -> list[ScoredNEO]:
    with open(path) as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = [data]
    neos = []
    for item in data:
        try:
            neos.append(ScoredNEO(**item))
        except Exception:
            pass
    return neos


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate follow-up priority list for NEO candidates"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to scored NEO JSON file",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=10,
        help="Maximum number of items to include (default 10)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of table",
    )
    args = parser.parse_args()

    neos = _load_neos(args.input)
    priority_list = generate_followup_priority_list(neos, max_items=args.max_items)

    if args.json:
        print(json.dumps(priority_list, indent=2))
    else:
        header = (
            f"{'object_id':<20} {'urgency':<10} {'pathway':<22} "
            f"{'moid_au':>10} {'priority':>10}"
        )
        print(header)
        print("-" * len(header))
        for row in priority_list:
            moid = row["moid_au"]
            moid_str = f"{moid:.4f}" if moid is not None else "N/A"
            print(
                f"{row['object_id']:<20} {row['urgency']:<10} {row['alert_pathway']:<22} "
                f"{moid_str:>10} {row['discovery_priority']:>10.4f}"
            )
        if priority_list:
            print(f"\nGuardrail: {priority_list[0]['guardrail']}")


if __name__ == "__main__":
    main()
