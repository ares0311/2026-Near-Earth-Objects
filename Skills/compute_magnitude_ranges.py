"""Batch magnitude range computation for a list of observations from a tracklet JSON file."""
import argparse
import json
import sys

sys.path.insert(0, "src")

from detect import compute_magnitude_range
from schemas import Observation


def _obs_from_dict(d: dict) -> Observation:
    return Observation(**{k: v for k, v in d.items() if k in Observation.model_fields})


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute magnitude range per tracklet")
    parser.add_argument("input", help="Path to tracklet JSON file")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    with open(args.input) as fh:
        data = json.load(fh)

    tracklets = data if isinstance(data, list) else data.get("tracklets", [data])

    results = []
    for t in tracklets:
        obs_list = [_obs_from_dict(o) for o in t.get("observations", [])]
        mag_range = compute_magnitude_range(obs_list)
        results.append(
            {
                "object_id": t.get("object_id", "unknown"),
                "magnitude_range": mag_range,
                "n_observations": len(obs_list),
            }
        )

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"{'Object ID':<30} {'Mag Range':>12} {'N Obs':>6}")
        print("-" * 52)
        for r in results:
            mag_str = f"{r['magnitude_range']:.3f}" if r["magnitude_range"] is not None else "N/A"
            print(f"{r['object_id']:<30} {mag_str:>12} {r['n_observations']:>6}")


if __name__ == "__main__":
    main()
