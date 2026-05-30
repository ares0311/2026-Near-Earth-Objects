"""Compute the discovery-priority-weighted mean MOID from a scored NEO JSON file.

Usage
-----
    python Skills/compute_priority_weighted_moid.py --input data/scored_neos.json

    python Skills/compute_priority_weighted_moid.py --input data/scored_neos.json --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Compute discovery-priority-weighted mean MOID from scored NEO JSON."
    )
    parser.add_argument("--input", required=True, help="Path to scored NEO JSON file")
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output result as JSON",
    )
    args = parser.parse_args(argv)

    from schemas import ScoredNEO
    from score import compute_priority_weighted_moid

    with open(args.input) as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        raw = [raw]

    neos = []
    for item in raw:
        try:
            neos.append(ScoredNEO(**item))
        except Exception:
            continue

    result = compute_priority_weighted_moid(neos)

    if args.as_json:
        print(json.dumps({"priority_weighted_moid_au": result}))
        return

    if result is None:
        print("Priority-weighted mean MOID: N/A (no valid candidates)")
    else:
        print(f"Priority-weighted mean MOID: {result:.6f} AU")


if __name__ == "__main__":
    main()
