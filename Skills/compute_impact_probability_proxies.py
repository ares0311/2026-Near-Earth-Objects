"""Compute impact probability proxy scores for scored NEO candidates.

NOTE: These values are NOT real impact probabilities.  They are conservative
internal ranking proxies only.  All hazard assessments must defer to
MPC/CNEOS for authoritative impact probability estimates.

Usage:
    python Skills/compute_impact_probability_proxies.py --input data/sample_tracklets.json
    python Skills/compute_impact_probability_proxies.py --input data/sample_tracklets.json --json
"""

import argparse
import json
import sys

sys.path.insert(0, "src")

from score import compute_impact_probability_proxy


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute impact probability proxy scores for scored NEO candidates."
    )
    parser.add_argument("--input", required=True, help="Path to scored NEO JSON file.")
    parser.add_argument("--json", action="store_true", help="Output as JSON.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    with open(args.input) as f:
        data = json.load(f)

    neos = data if isinstance(data, list) else data.get("neos", [])

    results = []
    for item in neos:
        # Support both raw dicts and ScoredNEO-like structures
        if isinstance(item, dict):
            object_id = item.get("object_id", item.get("tracklet", {}).get("object_id", "unknown"))
            features_raw = item.get("features", {}) or {}

            class _Features:
                def __init__(self, d: dict) -> None:
                    self.moid_score = d.get("moid_score")
                    self.pha_flag_confidence = d.get("pha_flag_confidence")
                    self.orbit_quality_score = d.get("orbit_quality_score")

            class _Neo:
                def __init__(self, f: _Features) -> None:
                    self.features = f

            neo = _Neo(_Features(features_raw))
        else:
            object_id = str(getattr(getattr(item, "tracklet", None), "object_id", "unknown"))
            neo = item  # type: ignore[assignment]

        proxy = compute_impact_probability_proxy(neo)
        results.append({"object_id": object_id, "proxy_score": proxy})

    note = "NOTE: These values are NOT real impact probabilities."

    if args.json:
        print(json.dumps({"note": note, "results": results}, indent=2))
        return

    print(note)
    print()
    print(f"{'object_id':<24}  {'proxy_score':>12}")
    print("-" * 40)
    for row in results:
        print(f"{row['object_id']:<24}  {row['proxy_score']:>12.6f}")


if __name__ == "__main__":
    main()
