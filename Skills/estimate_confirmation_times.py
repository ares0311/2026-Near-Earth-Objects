"""Estimate confirmation times for scored NEO candidates from a JSON file."""

import sys

sys.path.insert(0, "src")

import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Estimate confirmation times for scored NEO candidates from JSON."
    )
    parser.add_argument(
        "--input",
        default="data/sample_tracklets.json",
        help="Path to scored NEO JSON file (default: data/sample_tracklets.json)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    from alert import estimate_confirmation_time
    from score import compute_followup_urgency

    with open(args.input) as fh:
        data = json.load(fh)

    candidates = data if isinstance(data, list) else data.get("candidates", [data])

    results = []
    for c in candidates:
        tracklet = c.get("tracklet", c)
        object_id = tracklet.get("object_id", c.get("object_id", "unknown"))

        class _Features:
            def __init__(self, d: dict) -> None:
                feat = d.get("features", {}) or {}
                self.arc_coverage_score = feat.get("arc_coverage_score")
                self.nights_observed_score = feat.get("nights_observed_score")
                self.moid_score = feat.get("moid_score")
                self.orbit_quality_score = feat.get("orbit_quality_score")

        class _Hazard:
            def __init__(self, d: dict) -> None:
                hazard = d.get("hazard", {}) or {}
                self.hazard_flag = hazard.get("hazard_flag", "unknown")
                self.moid_au = hazard.get("moid_au")

        class _Meta:
            def __init__(self, d: dict) -> None:
                meta = d.get("metadata", {}) or {}
                self.discovery_priority = meta.get("discovery_priority", 0.0)

        class _Neo:
            def __init__(self, d: dict) -> None:
                self.hazard = _Hazard(d)
                self.metadata = _Meta(d)
                self.features = _Features(d)

        neo = _Neo(c)
        urgency = compute_followup_urgency(neo)
        hours = estimate_confirmation_time(neo)
        results.append(
            {
                "object_id": object_id,
                "urgency": urgency,
                "confirmation_hours": hours,
            }
        )

    if args.json:
        print(json.dumps(results, indent=2))
        return

    header = f"{'object_id':<24} {'urgency':<10} {'confirmation_hours':>20}"
    print(header)
    print("-" * len(header))
    for row in results:
        print(
            f"{row['object_id']:<24} {row['urgency']:<10} {row['confirmation_hours']:>20.1f}"
        )


if __name__ == "__main__":
    main()
