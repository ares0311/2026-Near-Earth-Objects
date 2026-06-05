"""Batch priority statistics from scored NEO JSON.

Usage:
    python Skills/compute_batch_priority_stats.py scored_neos.json [--json]

Reads a scored NEO JSON file and prints aggregate statistics
(mean, std, min, max) of discovery_priority values using
compute_batch_priority_stats from score.py.
"""
import json
import sys
from types import SimpleNamespace

sys.path.insert(0, "src")

from score import compute_batch_priority_stats


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
        print("Usage: compute_batch_priority_stats.py <scored_neos.json> [--json]",
              file=sys.stderr)
        sys.exit(1)

    with open(paths[0]) as fh:
        data = json.load(fh)
    records = data if isinstance(data, list) else [data]
    neos = [_load_neo(r) for r in records]

    stats = compute_batch_priority_stats(neos)

    if as_json:
        print(json.dumps({
            "n_candidates": len(neos),
            "priority_stats": stats,
        }, indent=2))
    else:
        print(f"Candidates evaluated: {len(neos)}")
        if not stats:
            print("No valid discovery_priority values found.")
        else:
            print(f"  Mean:  {stats['mean']:.4f}")
            print(f"  Std:   {stats['std']:.4f}")
            print(f"  Min:   {stats['min']:.4f}")
            print(f"  Max:   {stats['max']:.4f}")


if __name__ == "__main__":
    main(sys.argv[1:])
