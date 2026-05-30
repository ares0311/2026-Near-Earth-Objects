"""Compute detection completeness score for each scored NEO candidate.

Usage::

    python Skills/compute_detection_completeness.py --input data/sample_scored_neos.json
    python Skills/compute_detection_completeness.py --input data/sample_scored_neos.json --json
"""

import argparse
import json
import sys

sys.path.insert(0, "src")

from schemas import (
    CandidateExplanation,
    CandidateFeatures,
    HazardAssessment,
    NEOPosterior,
    Observation,
    OrbitalElements,
    ScoredNEO,
    ScoringMetadata,
    Tracklet,
)
from score import compute_detection_completeness_score


def _load_scored_neos(path: str) -> list[ScoredNEO]:
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    neos = []
    for item in data:
        try:
            # Build Tracklet
            obs_raw = item.get("tracklet", {}).get("observations", [])
            obs = tuple(Observation(**o) for o in obs_raw)
            t_data = item.get("tracklet", {})
            tracklet = Tracklet(
                object_id=t_data.get("object_id", "UNKNOWN"),
                observations=obs,
                arc_days=float(t_data.get("arc_days", 0.0)),
                motion_rate_arcsec_per_hour=float(t_data.get("motion_rate_arcsec_per_hour", 0.0)),
                motion_pa_degrees=float(t_data.get("motion_pa_degrees", 0.0)),
            )
            # Build features
            feat_data = item.get("features", {})
            features = CandidateFeatures(**{k: v for k, v in feat_data.items()})
            # Build posterior
            post_data = item.get("posterior", {})
            posterior = NEOPosterior(**post_data)
            # Build hazard
            haz_data = item.get("hazard", {})
            orb_data = haz_data.pop("orbital_elements", None)
            orbital = OrbitalElements(**orb_data) if orb_data else None
            expl_data = haz_data.pop("explanation", {})
            explanation = CandidateExplanation(**expl_data)
            hazard = HazardAssessment(
                **haz_data,
                explanation=explanation,
                orbital_elements=orbital,
            )
            # Build metadata
            meta_data = item.get("metadata", {})
            metadata = ScoringMetadata(**meta_data)
            neos.append(ScoredNEO(
                tracklet=tracklet,
                features=features,
                posterior=posterior,
                hazard=hazard,
                metadata=metadata,
            ))
        except Exception:
            continue
    return neos


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute detection completeness score for scored NEO candidates."
    )
    parser.add_argument("--input", required=True, help="Path to scored NEO JSON file")
    parser.add_argument(
        "--json", action="store_true", dest="as_json", help="Output as JSON"
    )
    args = parser.parse_args()

    neos = _load_scored_neos(args.input)
    rows = []
    for neo in neos:
        score_val = compute_detection_completeness_score(neo)
        rows.append(
            {
                "object_id": neo.tracklet.object_id,
                "completeness_score": score_val,
            }
        )

    # Sort by descending completeness score
    rows.sort(key=lambda r: r["completeness_score"], reverse=True)

    if args.as_json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"{'object_id':<20} {'completeness_score':>18}")
        print("-" * 40)
        for row in rows:
            print(f"{row['object_id']:<20} {row['completeness_score']:>18.4f}")


if __name__ == "__main__":
    main()
