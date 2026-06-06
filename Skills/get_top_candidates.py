"""Return the top-N scored NEO candidates by discovery priority.

Usage:
    python Skills/get_top_candidates.py scored_neos.json [--n 10] [--json]

Reads a scored NEO JSON file and prints the top N candidates ranked by
discovery_priority descending.
"""
import json
import sys
from types import SimpleNamespace

sys.path.insert(0, "src")

from score import get_top_candidates


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
    n = 10
    paths = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--n" and i + 1 < len(argv):
            n = int(argv[i + 1])
            i += 2
        elif arg.startswith("--"):
            i += 1
        else:
            paths.append(arg)
            i += 1

    if not paths:
        print("Usage: get_top_candidates.py <scored_neos.json> [--n N] [--json]",
              file=sys.stderr)
        sys.exit(1)

    with open(paths[0]) as fh:
        data = json.load(fh)
    records = data if isinstance(data, list) else [data]
    neos = [_load_neo(r) for r in records]

    top = get_top_candidates(neos, n=n)

    if as_json:
        print(json.dumps([t._raw for t in top], indent=2))
    else:
        print(f"Top {n} candidates (showing {len(top)}):")
        print(f"{'Object ID':<20}  Priority")
        print("-" * 32)
        for neo in top:
            obj_id = getattr(neo.tracklet, "object_id", "unknown")
            p = getattr(neo.metadata, "discovery_priority", None)
            print(f"{obj_id:<20}  {p:.4f}" if p is not None else f"{obj_id:<20}  N/A")


if __name__ == "__main__":
    main(sys.argv[1:])
