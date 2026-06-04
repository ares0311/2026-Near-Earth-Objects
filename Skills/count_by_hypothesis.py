"""Count scored NEOs by dominant posterior hypothesis.

Usage:
    python Skills/count_by_hypothesis.py scored_neos.json [--json]

Reads a scored NEO JSON file and prints a table of dominant-hypothesis
counts using count_by_dominant_hypothesis from classify.py.
"""
import json
import sys
from types import SimpleNamespace

sys.path.insert(0, "src")

from classify import count_by_dominant_hypothesis


def _load_neo(d: dict) -> SimpleNamespace:
    posterior_d = d.get("posterior", {})
    posterior = SimpleNamespace(**posterior_d) if isinstance(posterior_d, dict) else None
    tracklet_d = d.get("tracklet", {})
    tracklet = SimpleNamespace(**tracklet_d) if isinstance(tracklet_d, dict) else SimpleNamespace()
    return SimpleNamespace(tracklet=tracklet, posterior=posterior, _raw=d)


def main(argv: list[str]) -> None:
    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("--")]

    if not paths:
        print("Usage: count_by_hypothesis.py <scored_neos.json> [--json]",
              file=sys.stderr)
        sys.exit(1)

    with open(paths[0]) as fh:
        data = json.load(fh)
    records = data if isinstance(data, list) else [data]
    neos = [_load_neo(r) for r in records]

    counts = count_by_dominant_hypothesis(neos)

    if as_json:
        print(json.dumps(counts, indent=2))
    else:
        total = sum(counts.values())
        print(f"Total candidates: {total}")
        print(f"{'Hypothesis':<30}  {'Count':>6}  {'Fraction':>8}")
        print("-" * 48)
        for hyp, count in sorted(counts.items(), key=lambda x: -x[1]):
            frac = count / total if total > 0 else 0.0
            print(f"{hyp:<30}  {count:>6}  {frac:>8.3f}")


if __name__ == "__main__":
    main(sys.argv[1:])
