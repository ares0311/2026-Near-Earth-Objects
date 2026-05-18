#!/usr/bin/env python3
"""Batch-compute threat scores for ScoredNEOs from a JSON file."""

from __future__ import annotations

import argparse
import json
import sys


def _load_neos(path: str) -> list:
    import types

    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        data = [data]

    neos = []
    for d in data:
        hazard = d.get("hazard", {})
        metadata = d.get("metadata", {})
        features = d.get("features", {})
        tracklet = d.get("tracklet", {})

        neo = types.SimpleNamespace(
            hazard=types.SimpleNamespace(
                moid_au=hazard.get("moid_au"),
                absolute_magnitude_h=hazard.get("absolute_magnitude_h"),
            ),
            metadata=types.SimpleNamespace(
                quality_code=metadata.get("quality_code", metadata.get("orbit_quality_code", 0)),
            ),
            features=types.SimpleNamespace(
                moid_score=features.get("moid_score"),
                orbit_quality_score=features.get("orbit_quality_score"),
            ),
            tracklet=types.SimpleNamespace(
                object_id=tracklet.get("object_id", "unknown"),
            ),
        )
        neos.append(neo)
    return neos


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch-compute threat scores for ScoredNEOs from a JSON file."
    )
    parser.add_argument("input", help="Path to scored NEO JSON file (list or single object)")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.0,
        help="Only show candidates with threat score >= threshold (default: 0.0)",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON array")
    args = parser.parse_args()

    sys.path.insert(0, "src")
    from score import compute_threat_score  # type: ignore[import]

    neos = _load_neos(args.input)
    results = []
    for neo in neos:
        score = compute_threat_score(neo)
        if score >= args.threshold:
            results.append(
                {
                    "object_id": neo.tracklet.object_id,
                    "threat_score": round(score, 4),
                    "moid_au": neo.hazard.moid_au,
                    "absolute_magnitude_h": neo.hazard.absolute_magnitude_h,
                    "quality_code": neo.metadata.quality_code,
                }
            )

    results.sort(key=lambda r: r["threat_score"], reverse=True)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    if not results:
        print("No candidates above threshold.")
        return

    hdr = f"{'Object ID':<20} {'Threat Score':>12} {'MOID (AU)':>10} {'H':>6} {'Qual':>5}"
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        moid = f"{r['moid_au']:.4f}" if r["moid_au"] is not None else "  N/A"
        h_mag = r["absolute_magnitude_h"]
        h_val = f"{h_mag:.1f}" if h_mag is not None else " N/A"
        qual = r["quality_code"]
        print(
            f"{r['object_id']:<20} {r['threat_score']:>12.4f}"
            f" {moid:>10} {h_val:>6} {qual:>5}"
        )


if __name__ == "__main__":
    main()
