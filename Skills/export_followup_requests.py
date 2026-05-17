"""Generate NEOCP follow-up request files for scored NEO candidates.

Reads a scored NEO JSON file, filters to candidates above a priority threshold,
and writes one plain-text NEOCP follow-up request file per candidate using
`format_neocp_report` from alert.py.

Usage:
    python Skills/export_followup_requests.py data/sample_tracklets.json
    python Skills/export_followup_requests.py data/sample_tracklets.json \\
        --min-priority 0.5 --out-dir requests/ --obs-code F51
    python Skills/export_followup_requests.py data/sample_tracklets.json --summary
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _load_scored_neo(d: dict) -> object:
    """Deserialise a ScoredNEO from a plain dict."""
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

    tracklet_d = d["tracklet"]
    obs_list = tuple(
        Observation(**o) for o in tracklet_d.get("observations", [])
    )
    tracklet = Tracklet(
        object_id=tracklet_d["object_id"],
        observations=obs_list,
        arc_days=float(tracklet_d.get("arc_days", 0.0)),
        motion_rate_arcsec_per_hour=float(tracklet_d.get("motion_rate_arcsec_per_hour", 0.0)),
        motion_pa_degrees=float(tracklet_d.get("motion_pa_degrees", 0.0)),
    )

    h = d.get("hazard", {})
    explanation_d = h.get("explanation", {})
    explanation = CandidateExplanation(
        summary=explanation_d.get("summary", ""),
        supporting_evidence=tuple(explanation_d.get("supporting_evidence", [])),
        contra_evidence=tuple(explanation_d.get("contra_evidence", [])),
        model_version=explanation_d.get("model_version", "?"),
    )

    orbital_d = h.get("orbital_elements")
    orbital = OrbitalElements(**orbital_d) if orbital_d else None

    hazard = HazardAssessment(
        hazard_flag=h.get("hazard_flag", "unknown"),
        moid_au=h.get("moid_au"),
        estimated_diameter_m=h.get("estimated_diameter_m"),
        absolute_magnitude_h=h.get("absolute_magnitude_h"),
        neo_class=h.get("neo_class", "unknown"),
        alert_pathway=h.get("alert_pathway", "internal_candidate"),
        explanation=explanation,
        orbital_elements=orbital,
    )

    features = CandidateFeatures(**(d.get("features") or {}))
    post_d = d.get("posterior", {})
    posterior = NEOPosterior(
        neo_candidate=float(post_d.get("neo_candidate", 0.0)),
        known_object=float(post_d.get("known_object", 0.0)),
        main_belt_asteroid=float(post_d.get("main_belt_asteroid", 0.0)),
        stellar_artifact=float(post_d.get("stellar_artifact", 0.0)),
        other_solar_system=float(post_d.get("other_solar_system", 0.0)),
    )
    meta_d = d.get("metadata", {})
    metadata = ScoringMetadata(
        scorer_version=meta_d.get("scorer_version", "?"),
        scored_at_jd=float(meta_d.get("scored_at_jd", 0.0)),
        pipeline_run_id=meta_d.get("pipeline_run_id", "?"),
        discovery_priority=float(meta_d.get("discovery_priority", 0.0)),
        followup_value=float(meta_d.get("followup_value", 0.0)),
        scientific_interest=float(meta_d.get("scientific_interest", 0.0)),
    )
    return ScoredNEO(
        tracklet=tracklet,
        features=features,
        posterior=posterior,
        hazard=hazard,
        metadata=metadata,
    )


def export_followup_requests(
    neos: list,
    min_priority: float = 0.0,
    out_dir: Path | None = None,
    obs_code: str = "Xnn",
) -> list[dict]:
    """Generate NEOCP follow-up request strings for candidates above min_priority.

    Returns a list of dicts with keys ``object_id``, ``priority``, ``report``.
    When *out_dir* is provided, writes one ``.txt`` file per candidate.
    """
    from alert import format_neocp_report

    results = []
    for neo in neos:
        priority = neo.metadata.discovery_priority
        if priority < min_priority:
            continue
        text = format_neocp_report(neo, obs_code=obs_code)
        obj_id = neo.tracklet.object_id
        results.append({"object_id": obj_id, "priority": priority, "report": text})

        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
            safe = obj_id.replace("/", "_").replace(" ", "_")
            (out_dir / f"{safe}_neocp.txt").write_text(text)

    results.sort(key=lambda r: r["priority"], reverse=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export NEOCP follow-up requests for scored NEO candidates"
    )
    parser.add_argument("input", help="JSON file with list of ScoredNEO dicts")
    parser.add_argument(
        "--min-priority", type=float, default=0.0,
        help="minimum discovery_priority to include (default 0.0)"
    )
    parser.add_argument("--out-dir", default=None,
                        help="directory for output .txt files")
    parser.add_argument("--obs-code", default="Xnn",
                        help="MPC observatory code (default Xnn)")
    parser.add_argument("--summary", action="store_true",
                        help="print only a summary table, not full reports")
    args = parser.parse_args()

    data_path = Path(args.input)
    if not data_path.exists():
        print(f"ERROR: {data_path} not found", file=sys.stderr)
        sys.exit(1)

    with data_path.open() as f:
        raw_neos = json.load(f)

    if not isinstance(raw_neos, list):
        print("ERROR: JSON file must contain a list of ScoredNEO dicts", file=sys.stderr)
        sys.exit(1)

    neos = []
    for d in raw_neos:
        try:
            neos.append(_load_scored_neo(d))
        except Exception as exc:
            print(f"WARNING: skipping record — {exc}", file=sys.stderr)

    out_dir = Path(args.out_dir) if args.out_dir else None
    results = export_followup_requests(
        neos,
        min_priority=args.min_priority,
        out_dir=out_dir,
        obs_code=args.obs_code,
    )

    if args.summary:
        print(f"{'#':<4} {'Object ID':<20} {'Priority':>10}")
        print("-" * 38)
        for i, r in enumerate(results, 1):
            print(f"{i:<4} {r['object_id']:<20} {r['priority']:10.4f}")
        print(f"\nTotal requests generated: {len(results)}")
    else:
        for r in results:
            print(r["report"])
            print("=" * 60)

    if out_dir:
        print(f"Wrote {len(results)} request(s) to {out_dir}/", file=sys.stderr)


if __name__ == "__main__":
    main()
