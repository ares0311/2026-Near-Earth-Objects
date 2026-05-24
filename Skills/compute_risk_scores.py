"""Batch compute weighted risk scores for ScoredNEOs from a JSON file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch weighted risk score (0.5×threat + 0.3×CA + 0.2×orbit_quality)."
    )
    parser.add_argument("input", help="Path to ScoredNEO JSON file")
    parser.add_argument("--threshold", type=float, default=0.0,
                        help="Minimum risk score to include (default: 0.0)")
    parser.add_argument("--sort", choices=["asc", "desc"], default="desc",
                        help="Sort order by risk score")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    from score import compute_weighted_risk_score

    data = json.loads(Path(args.input).read_text())
    if not isinstance(data, list):
        data = [data]

    from types import SimpleNamespace

    def _build(d: dict) -> SimpleNamespace:
        hazard_d = d.get("hazard") or {}
        features_d = d.get("features") or {}
        tracklet_d = d.get("tracklet") or {}

        hazard = SimpleNamespace(**{k: v for k, v in hazard_d.items()})
        features = SimpleNamespace(**{k: v for k, v in features_d.items()})
        tracklet = SimpleNamespace(**{k: v for k, v in tracklet_d.items()})
        return SimpleNamespace(hazard=hazard, features=features, tracklet=tracklet,
                               metadata=None, posterior=None)

    results = []
    for item in data:
        neo = _build(item)
        oid = getattr(neo.tracklet, "object_id", "unknown")
        risk = compute_weighted_risk_score(neo)
        if risk >= args.threshold:
            results.append({"object_id": oid, "risk_score": risk})

    results.sort(key=lambda r: r["risk_score"], reverse=(args.sort == "desc"))

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"{'Object ID':<30} {'Risk Score':>12}")
        print("-" * 44)
        for r in results:
            print(f"{r['object_id']:<30} {r['risk_score']:>12.6f}")


if __name__ == "__main__":
    main()
