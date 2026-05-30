"""Compute combined hazard scores for scored NEO candidates from a JSON file.

Reads a scored NEO JSON file, calls ``compute_combined_hazard_score`` for
each candidate, and prints a table of object IDs with their combined hazard
scores.

Usage
-----
    python Skills/compute_combined_hazard_scores.py data/scored_neos.json
    python Skills/compute_combined_hazard_scores.py data/scored_neos.json --json
"""

from __future__ import annotations

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
from score import compute_combined_hazard_score


def _load_scored_neos(path: str) -> list[ScoredNEO]:
    with open(path) as fh:
        raw = json.load(fh)
    if isinstance(raw, dict):
        raw = [raw]
    neos: list[ScoredNEO] = []
    for item in raw:
        try:
            obs_raw = item.get("tracklet", {}).get("observations", [])
            obs = tuple(
                Observation(
                    obs_id=o.get("obs_id", f"obs_{j}"),
                    jd=float(o["jd"]),
                    ra_deg=float(o["ra_deg"]),
                    dec_deg=float(o["dec_deg"]),
                    mag=float(o.get("mag", 19.0)),
                    mag_err=float(o.get("mag_err", 0.05)),
                    filter_band=o.get("filter_band", "r"),
                    mission=o.get("mission", "ZTF"),
                )
                for j, o in enumerate(obs_raw)
            )
            t_raw = item.get("tracklet", {})
            tracklet = Tracklet(
                object_id=t_raw.get("object_id", "unknown"),
                observations=obs,
                arc_days=float(t_raw.get("arc_days", 0.0)),
                motion_rate_arcsec_per_hour=float(
                    t_raw.get("motion_rate_arcsec_per_hour", 0.0)
                ),
                motion_pa_degrees=float(t_raw.get("motion_pa_degrees", 0.0)),
            )
            f_raw = item.get("features", {})
            features = CandidateFeatures(
                real_bogus_score=f_raw.get("real_bogus_score"),
                moid_score=f_raw.get("moid_score"),
                pha_flag_confidence=f_raw.get("pha_flag_confidence"),
                orbit_quality_score=f_raw.get("orbit_quality_score"),
            )
            p_raw = item.get("posterior", {})
            posterior = NEOPosterior(
                neo_candidate=float(p_raw.get("neo_candidate", 0.05)),
                known_object=float(p_raw.get("known_object", 0.30)),
                main_belt_asteroid=float(p_raw.get("main_belt_asteroid", 0.35)),
                stellar_artifact=float(p_raw.get("stellar_artifact", 0.25)),
                other_solar_system=float(p_raw.get("other_solar_system", 0.05)),
            )
            h_raw = item.get("hazard", {})
            o_raw = h_raw.get("orbital_elements", {})
            orbital = OrbitalElements(
                semi_major_axis_au=float(o_raw.get("semi_major_axis_au", 1.5)),
                eccentricity=float(o_raw.get("eccentricity", 0.3)),
                inclination_deg=float(o_raw.get("inclination_deg", 10.0)),
                longitude_ascending_node_deg=float(
                    o_raw.get("longitude_ascending_node_deg", 0.0)
                ),
                argument_perihelion_deg=float(
                    o_raw.get("argument_perihelion_deg", 0.0)
                ),
                mean_anomaly_deg=float(o_raw.get("mean_anomaly_deg", 0.0)),
                epoch_jd=float(o_raw.get("epoch_jd", 2460000.5)),
                perihelion_au=float(o_raw.get("perihelion_au", 1.0)),
                aphelion_au=float(o_raw.get("aphelion_au", 2.0)),
                quality_code=int(o_raw.get("quality_code", 2)),
            )
            explanation = CandidateExplanation(
                summary=h_raw.get("explanation", {}).get("summary", ""),
                supporting_evidence=tuple(
                    h_raw.get("explanation", {}).get("supporting_evidence", [])
                ),
                contra_evidence=tuple(
                    h_raw.get("explanation", {}).get("contra_evidence", [])
                ),
                model_version=h_raw.get("explanation", {}).get("model_version", "0.1.0"),
            )
            hazard = HazardAssessment(
                hazard_flag=h_raw.get("hazard_flag", "unknown"),
                moid_au=h_raw.get("moid_au"),
                estimated_diameter_m=h_raw.get("estimated_diameter_m"),
                absolute_magnitude_h=h_raw.get("absolute_magnitude_h"),
                neo_class=h_raw.get("neo_class", "unknown"),
                alert_pathway=h_raw.get("alert_pathway", "internal_candidate"),
                explanation=explanation,
                orbital_elements=orbital,
            )
            m_raw = item.get("metadata", {})
            metadata = ScoringMetadata(
                scorer_version=m_raw.get("scorer_version", "0.1.0"),
                scored_at_jd=float(m_raw.get("scored_at_jd", 2460000.5)),
                pipeline_run_id=m_raw.get("pipeline_run_id", "unknown"),
                discovery_priority=float(m_raw.get("discovery_priority", 0.0)),
                followup_value=float(m_raw.get("followup_value", 0.0)),
                scientific_interest=float(m_raw.get("scientific_interest", 0.0)),
            )
            neos.append(
                ScoredNEO(
                    tracklet=tracklet,
                    features=features,
                    posterior=posterior,
                    hazard=hazard,
                    metadata=metadata,
                )
            )
        except Exception as exc:
            print(f"Warning: skipping item due to error: {exc}", file=sys.stderr)
    return neos


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute combined hazard scores for scored NEO candidates."
    )
    parser.add_argument("input", help="Path to scored NEO JSON file")
    parser.add_argument(
        "--json", action="store_true", dest="as_json", help="Output JSON instead of table"
    )
    args = parser.parse_args()

    neos = _load_scored_neos(args.input)
    rows: list[dict] = []
    for neo in neos:
        rows.append(
            {
                "object_id": neo.tracklet.object_id,
                "combined_hazard_score": compute_combined_hazard_score(neo),
            }
        )

    rows.sort(key=lambda r: r["combined_hazard_score"], reverse=True)

    if args.as_json:
        print(json.dumps(rows, indent=2))
    else:
        if not rows:
            print("No candidates found.")
            return
        print(f"{'object_id':<30s}  combined_hazard_score")
        print("-" * 55)
        for row in rows:
            print(f"{row['object_id']:<30s}  {row['combined_hazard_score']:.4f}")


if __name__ == "__main__":
    main()
