"""Compute mean NEO candidate probability from scored NEO JSON.

Usage:
    python Skills/compute_mean_neo_probabilities.py scored_neos.json [--json]

Reads a scored NEO JSON file and prints the mean posterior neo_candidate
probability using compute_mean_neo_probability from classify.py.
"""
import json
import sys
from types import SimpleNamespace

sys.path.insert(0, "src")

from classify import compute_mean_neo_probability


def _load_neo(d: dict) -> SimpleNamespace:
    posterior_d = d.get("posterior", {}) or {}
    posterior = SimpleNamespace(**posterior_d) if isinstance(posterior_d, dict) else None
    tracklet_d = d.get("tracklet", {}) or {}
    tracklet = SimpleNamespace(**tracklet_d) if isinstance(tracklet_d, dict) else SimpleNamespace()
    return SimpleNamespace(posterior=posterior, tracklet=tracklet, _raw=d)


def main(argv: list[str]) -> None:
    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("--")]

    if not paths:
        print("Usage: compute_mean_neo_probabilities.py <scored_neos.json> [--json]",
              file=sys.stderr)
        sys.exit(1)

    with open(paths[0]) as fh:
        data = json.load(fh)
    records = data if isinstance(data, list) else [data]
    neos = [_load_neo(r) for r in records]

    mean_prob = compute_mean_neo_probability(neos)

    if as_json:
        print(json.dumps({"mean_neo_probability": mean_prob, "n_candidates": len(neos)}, indent=2))
    else:
        print(f"Candidates evaluated: {len(neos)}")
        if mean_prob is not None:
            print(f"Mean NEO probability:  {mean_prob:.4f}")
        else:
            print("Mean NEO probability:  N/A (no valid posteriors)")


if __name__ == "__main__":
    main(sys.argv[1:])
