"""Summarize alert pathways across scored NEO JSON.

Usage:
    python Skills/summarize_alert_pathways.py scored_neos.json [--json]

Reads a scored NEO JSON file and prints a count table of alert pathways
using count_by_alert_pathway from score.py.
"""
import json
import sys
from types import SimpleNamespace

sys.path.insert(0, "src")

from score import count_by_alert_pathway


def _load_neo(d: dict) -> SimpleNamespace:
    hazard_d = d.get("hazard", {}) or {}
    hazard = SimpleNamespace(**hazard_d) if isinstance(hazard_d, dict) else SimpleNamespace()
    meta_d = d.get("metadata", {}) or {}
    metadata = SimpleNamespace(**meta_d) if isinstance(meta_d, dict) else SimpleNamespace()
    tracklet_d = d.get("tracklet", {}) or {}
    tracklet = SimpleNamespace(**tracklet_d) if isinstance(tracklet_d, dict) else SimpleNamespace()
    return SimpleNamespace(hazard=hazard, metadata=metadata, tracklet=tracklet, _raw=d)


def main(argv: list[str]) -> None:
    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("--")]

    if not paths:
        print("Usage: summarize_alert_pathways.py <scored_neos.json> [--json]",
              file=sys.stderr)
        sys.exit(1)

    with open(paths[0]) as fh:
        data = json.load(fh)
    records = data if isinstance(data, list) else [data]
    neos = [_load_neo(r) for r in records]

    counts = count_by_alert_pathway(neos)

    if as_json:
        print(json.dumps(counts, indent=2))
    else:
        total = sum(counts.values())
        print(f"Total candidates: {total}")
        print(f"{'Alert Pathway':<30}  {'Count':>6}  {'Fraction':>8}")
        print("-" * 50)
        for pathway, count in sorted(counts.items(), key=lambda x: -x[1]):
            frac = count / total if total > 0 else 0.0
            print(f"{pathway:<30}  {count:>6}  {frac:>8.3f}")


if __name__ == "__main__":
    main(sys.argv[1:])
