"""Compute candidate priority spread from scored NEO JSON.

Usage:
    python Skills/compute_candidate_priority_spreads.py scored_neos.json [--json]

Reads a scored NEO JSON file and prints the standard deviation of discovery
priority values using compute_candidate_priority_spread from score.py.
"""
import json
import sys
from types import SimpleNamespace

sys.path.insert(0, "src")

from score import compute_candidate_priority_spread


def _load_neo(d: dict) -> SimpleNamespace:
    meta_d = d.get("metadata", {}) or {}
    metadata = SimpleNamespace(**meta_d) if isinstance(meta_d, dict) else SimpleNamespace()
    tracklet_d = d.get("tracklet", {}) or {}
    tracklet = SimpleNamespace(**tracklet_d) if isinstance(tracklet_d, dict) else SimpleNamespace()
    return SimpleNamespace(metadata=metadata, tracklet=tracklet, _raw=d)


def main(argv: list[str]) -> None:
    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("--")]

    if not paths:
        print("Usage: compute_candidate_priority_spreads.py <scored_neos.json> [--json]",
              file=sys.stderr)
        sys.exit(1)

    with open(paths[0]) as fh:
        data = json.load(fh)
    records = data if isinstance(data, list) else [data]
    neos = [_load_neo(r) for r in records]

    spread = compute_candidate_priority_spread(neos)

    if as_json:
        print(json.dumps({
            "n_candidates": len(neos),
            "priority_spread": spread,
        }, indent=2))
    else:
        print(f"Candidates evaluated: {len(neos)}")
        print(f"Priority spread (std dev): {spread:.4f}")


if __name__ == "__main__":
    main(sys.argv[1:])
