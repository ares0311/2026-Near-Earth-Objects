"""Batch priority rank table from scored NEO JSON."""

from __future__ import annotations

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rank scored NEO candidates by discovery priority."
    )
    parser.add_argument("input", help="Path to JSON file (list of ScoredNEO dicts).")
    parser.add_argument(
        "--top-n",
        type=int,
        default=None,
        metavar="N",
        help="Show only the top N candidates (default: all).",
    )
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
        from score import compute_priority_rank
    except ImportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    from types import SimpleNamespace

    neos = []
    for item in data:
        tracklet_ns = SimpleNamespace(
            object_id=(
                item.get("tracklet", {}).get("object_id")
                or item.get("object_id", "unknown")
            )
        )
        hazard = item.get("hazard", {})
        hazard_ns = SimpleNamespace(
            hazard_flag=hazard.get("hazard_flag", "unknown"),
        )
        metadata = item.get("metadata", {})
        metadata_ns = SimpleNamespace(
            discovery_priority=float(metadata.get("discovery_priority", 0.0) or 0.0),
        )
        neos.append(SimpleNamespace(
            tracklet=tracklet_ns,
            hazard=hazard_ns,
            metadata=metadata_ns,
        ))

    ranked = compute_priority_rank(neos)
    if args.top_n is not None:
        ranked = ranked[: args.top_n]

    if args.json:
        print(json.dumps(ranked, indent=2))
    else:
        if not ranked:
            print("No candidates.")
        else:
            print(
                f"{'Rank':>4s}  {'Object':<24s}  {'Priority':>10s}  Hazard Flag"
            )
            print("-" * 60)
            for r in ranked:
                print(
                    f"{r['rank']:>4d}  {r['object_id']:<24s}"
                    f"  {r['discovery_priority']:>10.4f}  {r['hazard_flag']}"
                )
        print(f"\n{len(ranked)} item(s).")

    sys.exit(0)


if __name__ == "__main__":
    main()
