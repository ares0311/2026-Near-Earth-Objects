"""Batch Tier-1 real/bogus score distribution report from scored NEO JSON."""

from __future__ import annotations

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute Tier-1 real/bogus score distribution from scored NEO JSON."
    )
    parser.add_argument("input", help="Path to JSON file (list of ScoredNEO dicts).")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of a table.")
    args = parser.parse_args()

    try:
        with open(args.input) as fh:
            data = json.load(fh)
    except Exception as exc:
        print(f"ERROR: could not read {args.input}: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, list):
        data = [data]

    sys.path.insert(0, "src")
    try:
        from classify import compute_tier1_score_distribution
    except ImportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    from types import SimpleNamespace

    neos = []
    for item in data:
        features_dict = item.get("features", {})
        rb = features_dict.get("real_bogus_score") if isinstance(features_dict, dict) else None
        features = SimpleNamespace(real_bogus_score=rb)
        neos.append(SimpleNamespace(features=features))

    result = compute_tier1_score_distribution(neos)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{'Metric':<12s} {'Value':>10s}")
        print("-" * 24)
        for key, val in result.items():
            if isinstance(val, float):
                print(f"{key:<12s} {val:>10.4f}")
            else:
                print(f"{key:<12s} {val:>10}")
        print(f"\n{result['n_valid']} valid score(s) out of {result['n_total']} item(s).")

    sys.exit(0)


if __name__ == "__main__":
    main()
