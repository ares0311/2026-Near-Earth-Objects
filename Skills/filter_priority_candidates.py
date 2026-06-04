"""Filter scored NEO candidates by discovery priority threshold.

Usage:
    python Skills/filter_priority_candidates.py scored_neos.json [--min-priority 0.5] [--json]

Reads a scored NEO JSON file and prints only candidates with
discovery_priority >= the threshold, sorted by priority descending.
"""
import json
import sys
from types import SimpleNamespace

sys.path.insert(0, "src")

from score import filter_by_discovery_priority


def _load_neo(d: dict) -> SimpleNamespace:
    meta_d = d.get("metadata", {})
    meta = SimpleNamespace(**meta_d) if isinstance(meta_d, dict) else SimpleNamespace()
    tracklet_d = d.get("tracklet", {})
    tracklet = SimpleNamespace(**tracklet_d) if isinstance(tracklet_d, dict) else SimpleNamespace()
    hazard_d = d.get("hazard", {})
    hazard = SimpleNamespace(**hazard_d) if isinstance(hazard_d, dict) else SimpleNamespace()
    return SimpleNamespace(tracklet=tracklet, metadata=meta, hazard=hazard, _raw=d)


def main(argv: list[str]) -> None:
    as_json = "--json" in argv
    min_priority = 0.5
    paths = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--min-priority" and i + 1 < len(argv):
            min_priority = float(argv[i + 1])
            i += 2
        elif arg.startswith("--"):
            i += 1
        else:
            paths.append(arg)
            i += 1

    if not paths:
        print("Usage: filter_priority_candidates.py <scored_neos.json> "
              "[--min-priority T] [--json]", file=sys.stderr)
        sys.exit(1)

    with open(paths[0]) as fh:
        data = json.load(fh)
    records = data if isinstance(data, list) else [data]
    neos = [_load_neo(r) for r in records]

    filtered = filter_by_discovery_priority(neos, min_priority=min_priority)
    filtered.sort(
        key=lambda n: getattr(n.metadata, "discovery_priority", 0.0) or 0.0,
        reverse=True,
    )

    if as_json:
        output = [n._raw for n in filtered]
        print(json.dumps(output, indent=2))
    else:
        print(f"Candidates with priority >= {min_priority}: {len(filtered)}")
        print(f"{'Object ID':<20}  Priority")
        print("-" * 32)
        for n in filtered:
            obj_id = getattr(n.tracklet, "object_id", "unknown")
            p = getattr(n.metadata, "discovery_priority", None)
            print(f"{obj_id:<20}  {p:.4f}" if p is not None else f"{obj_id:<20}  N/A")


if __name__ == "__main__":
    main(sys.argv[1:])
