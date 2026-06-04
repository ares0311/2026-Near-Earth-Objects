"""Batch discovery-priority histogram from scored NEO JSON.

Usage:
    python Skills/compute_priority_histograms.py scored_neos.json [--bins N] [--json]

Reads a JSON file containing a list of ScoredNEO-like dicts and prints a
histogram of discovery_priority values in N equal-width bins across [0, 1].
"""
import json
import sys
from types import SimpleNamespace

sys.path.insert(0, "src")

from score import compute_priority_histogram


def _load_neo(d: dict) -> SimpleNamespace:
    """Lightly wrap a dict as a namespace so score helpers can read attributes."""
    meta = d.get("metadata", {})
    meta_ns = SimpleNamespace(**meta) if isinstance(meta, dict) else SimpleNamespace()
    return SimpleNamespace(metadata=meta_ns)


def main(argv: list[str]) -> None:
    as_json = "--json" in argv
    n_bins = 5
    paths = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--bins" and i + 1 < len(argv):
            n_bins = int(argv[i + 1])
            i += 2
        elif arg.startswith("--"):
            i += 1
        else:
            paths.append(arg)
            i += 1

    if not paths:
        print("Usage: compute_priority_histograms.py <scored_neos.json> [--bins N] [--json]",
              file=sys.stderr)
        sys.exit(1)

    with open(paths[0]) as fh:
        data = json.load(fh)
    records = data if isinstance(data, list) else [data]
    neos = [_load_neo(r) for r in records]

    hist = compute_priority_histogram(neos, n_bins=n_bins)

    if as_json:
        print(json.dumps(hist, indent=2))
    else:
        edges = hist["bin_edges"]
        counts = hist["counts"]
        print(f"Priority histogram (n_total={hist['n_total']}, bins={n_bins})")
        print(f"{'Bin range':<22}  Count")
        print("-" * 32)
        for i, cnt in enumerate(counts):
            lo = edges[i]
            hi = edges[i + 1]
            print(f"[{lo:.2f}, {hi:.2f})           {cnt:>5}")


if __name__ == "__main__":
    main(sys.argv[1:])
