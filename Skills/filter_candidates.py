"""Filter ScoredNEO candidates from a JSON file by hazard flag or pathway.

Usage:
    python Skills/filter_candidates.py data/sample_tracklets.json \\
        [--hazard pha_candidate] [--pathway mpc_submission] [--min-priority 0.5] \\
        [--out filtered.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def filter_candidates(
    neos: list[dict],
    hazard_flag: str | None = None,
    alert_pathway: str | None = None,
    min_priority: float = 0.0,
) -> list[dict]:
    """Return subset of serialised ScoredNEO dicts matching the given criteria."""
    results: list[dict] = []
    for neo in neos:
        hazard = neo.get("hazard", {})
        metadata = neo.get("metadata", {})
        if hazard_flag and hazard.get("hazard_flag") != hazard_flag:
            continue
        if alert_pathway and hazard.get("alert_pathway") != alert_pathway:
            continue
        priority = float(metadata.get("discovery_priority", 0.0))
        if priority < min_priority:
            continue
        results.append(neo)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter ScoredNEO candidates")
    parser.add_argument("input", help="JSON file with list of ScoredNEO dicts")
    parser.add_argument("--hazard", help="hazard_flag to keep")
    parser.add_argument("--pathway", help="alert_pathway to keep")
    parser.add_argument("--min-priority", type=float, default=0.0,
                        help="minimum discovery_priority (default: 0.0)")
    parser.add_argument("--out", help="output JSON file (default: stdout)")
    args = parser.parse_args()

    data_path = Path(args.input)
    if not data_path.exists():
        print(f"ERROR: {data_path} not found", file=sys.stderr)
        sys.exit(1)

    with data_path.open() as f:
        neos = json.load(f)

    if not isinstance(neos, list):
        print("ERROR: JSON file must contain a list of ScoredNEO dicts", file=sys.stderr)
        sys.exit(1)

    filtered = filter_candidates(
        neos,
        hazard_flag=args.hazard,
        alert_pathway=args.pathway,
        min_priority=args.min_priority,
    )

    output = json.dumps(filtered, indent=2)
    if args.out:
        Path(args.out).write_text(output)
        print(f"Wrote {len(filtered)} candidates to {args.out}")
    else:
        print(output)


if __name__ == "__main__":
    main()
