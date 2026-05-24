"""Compute hazard summary statistics from a scored NEO JSON file.

Usage
-----
    python Skills/compute_hazard_summary.py data/sample_tracklets.json

    python Skills/compute_hazard_summary.py data/sample_tracklets.json --json
"""

from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _load_neos(path: str) -> list:
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        data = [data]
    neos = []
    for d in data:
        if not isinstance(d, dict):
            continue
        hazard = d.get("hazard", {})
        metadata = d.get("metadata", {})
        tracklet = d.get("tracklet", {})
        neo = types.SimpleNamespace(
            hazard=types.SimpleNamespace(
                hazard_flag=hazard.get("hazard_flag", "unknown"),
            ),
            metadata=types.SimpleNamespace(
                discovery_priority=float(metadata.get("discovery_priority", 0.0)),
            ),
            tracklet=types.SimpleNamespace(
                object_id=tracklet.get("object_id", "unknown"),
            ),
        )
        neos.append(neo)
    return neos


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Compute hazard summary statistics from scored NEO JSON."
    )
    parser.add_argument("input", help="Path to scored NEO JSON file (list or single object)")
    parser.add_argument("--json", dest="as_json", action="store_true",
                        help="Output as JSON object")
    args = parser.parse_args(argv)

    from score import compute_hazard_summary

    neos = _load_neos(args.input)
    summary = compute_hazard_summary(neos)

    if args.as_json:
        print(json.dumps(summary, indent=2))
        return

    print(f"Total candidates:          {summary['n_total']}")
    print(f"PHA candidates:            {summary['n_pha_candidates']}")
    print(f"Close approach:            {summary['n_close_approach']}")
    print(f"Nominal:                   {summary['n_nominal']}")
    print(f"Unknown hazard:            {summary['n_unknown']}")
    print(f"Mean discovery priority:   {summary['mean_discovery_priority']:.4f}")


if __name__ == "__main__":
    main()
