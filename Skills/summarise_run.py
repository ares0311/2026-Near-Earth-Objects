"""Summarise a pipeline run from a scored NEO JSON file.

Prints a concise table of detection counts, hazard flags, alert pathways,
and top-ranked candidates.

Usage:
    python Skills/summarise_run.py data/sample_tracklets.json [--top 5] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def summarise_run(neos: list[dict]) -> dict:
    """Return a summary dict from a list of serialised ScoredNEO dicts."""
    hazard_counts: Counter = Counter()
    pathway_counts: Counter = Counter()
    neo_class_counts: Counter = Counter()
    priorities: list[float] = []

    for neo in neos:
        hazard = neo.get("hazard", {})
        metadata = neo.get("metadata", {})
        hazard_counts[hazard.get("hazard_flag", "unknown")] += 1
        pathway_counts[hazard.get("alert_pathway", "unknown")] += 1
        neo_class_counts[hazard.get("neo_class", "unknown")] += 1
        priorities.append(float(metadata.get("discovery_priority", 0.0)))

    top_candidates = sorted(
        neos,
        key=lambda n: float(n.get("metadata", {}).get("discovery_priority", 0.0)),
        reverse=True,
    )[:5]

    return {
        "n_candidates": len(neos),
        "hazard_flag_counts": dict(hazard_counts),
        "alert_pathway_counts": dict(pathway_counts),
        "neo_class_counts": dict(neo_class_counts),
        "mean_priority": sum(priorities) / len(priorities) if priorities else 0.0,
        "max_priority": max(priorities) if priorities else 0.0,
        "top_candidates": [
            {
                "object_id": n.get("tracklet", {}).get("object_id", "?"),
                "hazard_flag": n.get("hazard", {}).get("hazard_flag", "?"),
                "alert_pathway": n.get("hazard", {}).get("alert_pathway", "?"),
                "discovery_priority": float(
                    n.get("metadata", {}).get("discovery_priority", 0.0)
                ),
            }
            for n in top_candidates
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarise a scored NEO pipeline run")
    parser.add_argument("input", help="JSON file with list of ScoredNEO dicts")
    parser.add_argument("--top", type=int, default=5, help="number of top candidates to show")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="output as JSON instead of human-readable text")
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

    summary = summarise_run(neos)
    summary["top_candidates"] = summary["top_candidates"][: args.top]

    if args.as_json:
        print(json.dumps(summary, indent=2))
    else:
        print("Pipeline Run Summary")
        print("====================")
        print(f"Total candidates  : {summary['n_candidates']}")
        print(f"Mean priority     : {summary['mean_priority']:.3f}")
        print(f"Max priority      : {summary['max_priority']:.3f}")
        print()
        print("Hazard flags:")
        for flag, cnt in summary["hazard_flag_counts"].items():
            print(f"  {flag:<25} {cnt}")
        print()
        print("Alert pathways:")
        for pathway, cnt in summary["alert_pathway_counts"].items():
            print(f"  {pathway:<30} {cnt}")
        print()
        print(f"Top {len(summary['top_candidates'])} candidates:")
        for i, c in enumerate(summary["top_candidates"], 1):
            print(
                f"  {i}. {c['object_id']:<20} "
                f"hazard={c['hazard_flag']:<18} "
                f"pathway={c['alert_pathway']:<20} "
                f"priority={c['discovery_priority']:.3f}"
            )


if __name__ == "__main__":
    main()
