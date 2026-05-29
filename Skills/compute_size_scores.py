"""Batch size score computation for scored NEO candidates.

Reads a scored NEO JSON file (list of dicts) and prints the object_id and
size score for each candidate using ``compute_size_score`` from the score
module.  Supports ``--json`` for machine-readable output.

Usage
-----
    python Skills/compute_size_scores.py data/scored_neos.json
    python Skills/compute_size_scores.py data/scored_neos.json --json
"""

from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "src")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch size score from scored NEO JSON"
    )
    parser.add_argument("input", help="Path to scored NEO JSON file")
    parser.add_argument(
        "--json", action="store_true", help="Output as JSON instead of table"
    )
    args = parser.parse_args()

    from score import compute_size_score

    with open(args.input) as f:
        raw = json.load(f)

    results = []
    for item in raw:
        object_id = item.get("object_id") or (
            item.get("tracklet", {}).get("object_id", "UNKNOWN")
        )
        # Build a minimal proxy object
        hazard_dict = item.get("hazard", {})
        diameter = hazard_dict.get("estimated_diameter_m", None)

        class _Hazard:
            def __init__(self, d: float | None) -> None:
                self.estimated_diameter_m = d

        class _Neo:
            def __init__(self, d: float | None) -> None:
                self.hazard = _Hazard(d)

        neo_proxy = _Neo(diameter)
        size_score = compute_size_score(neo_proxy)
        results.append({"object_id": object_id, "size_score": size_score})

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        header = f"{'object_id':<30} {'size_score':>12}"
        print(header)
        print("-" * len(header))
        for r in results:
            print(f"{r['object_id']:<30} {r['size_score']:>12.4f}")
        if not results:
            print("No candidates found.")


if __name__ == "__main__":
    main()
