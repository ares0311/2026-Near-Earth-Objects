"""Compute composite NEO scores from scored NEO JSON.

Usage:
    python Skills/compute_composite_neo_scores.py scored_neos.json [--json]

Reads a scored NEO JSON file and prints composite NEO scores using
compute_composite_neo_score from classify.py.
"""
import json
import sys
from types import SimpleNamespace

sys.path.insert(0, "src")

from classify import compute_composite_neo_score


def _load_neo(d: dict) -> SimpleNamespace:
    features_d = d.get("features", {}) or {}
    features = SimpleNamespace(**features_d) if isinstance(features_d, dict) else SimpleNamespace()
    tracklet_d = d.get("tracklet", {}) or {}
    tracklet = SimpleNamespace(**tracklet_d) if isinstance(tracklet_d, dict) else SimpleNamespace()
    return SimpleNamespace(tracklet=tracklet, features=features, _raw=d)


def main(argv: list[str]) -> None:
    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("--")]

    if not paths:
        print("Usage: compute_composite_neo_scores.py <scored_neos.json> [--json]",
              file=sys.stderr)
        sys.exit(1)

    with open(paths[0]) as fh:
        data = json.load(fh)
    records = data if isinstance(data, list) else [data]
    neos = [_load_neo(r) for r in records]

    rows = []
    for neo in neos:
        obj_id = getattr(neo.tracklet, "object_id", "unknown") or "unknown"
        score = compute_composite_neo_score(neo.features)
        rows.append({"object_id": obj_id, "composite_neo_score": score})

    if as_json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"{'Object ID':<20}  {'Composite Score':>16}")
        print("-" * 38)
        for row in sorted(rows, key=lambda r: -r["composite_neo_score"]):
            print(f"{row['object_id']:<20}  {row['composite_neo_score']:>16.4f}")


if __name__ == "__main__":
    main(sys.argv[1:])
