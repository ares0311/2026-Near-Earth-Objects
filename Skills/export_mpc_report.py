"""Export MPC 80-column observation reports for a list of ScoredNEO objects.

Reads a JSON file of scored NEO records, formats each as an MPC report,
and writes one .txt file per object to the output directory.

Usage:
    PYTHONPATH=src python Skills/export_mpc_report.py \
        --input scored_neos.json \
        --output-dir mpc_reports/
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from alert import format_mpc_report
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


def _parse_scored_neo(raw: dict) -> ScoredNEO:
    obs = tuple(Observation(**o) for o in raw["tracklet"]["observations"])
    tracklet = Tracklet(
        object_id=raw["tracklet"]["object_id"],
        observations=obs,
        arc_days=raw["tracklet"]["arc_days"],
        motion_rate_arcsec_per_hour=raw["tracklet"]["motion_rate_arcsec_per_hour"],
        motion_pa_degrees=raw["tracklet"]["motion_pa_degrees"],
    )
    features = CandidateFeatures(**raw.get("features", {}))
    posterior = NEOPosterior(**raw["posterior"])
    expl_raw = raw["hazard"]["explanation"]
    explanation = CandidateExplanation(
        summary=expl_raw["summary"],
        supporting_evidence=tuple(expl_raw.get("supporting_evidence", [])),
        contra_evidence=tuple(expl_raw.get("contra_evidence", [])),
        model_version=expl_raw.get("model_version", "0.1.0"),
    )
    orbital_raw = raw["hazard"].get("orbital_elements")
    orbital = OrbitalElements(**orbital_raw) if orbital_raw else None
    hazard = HazardAssessment(
        hazard_flag=raw["hazard"]["hazard_flag"],  # type: ignore[arg-type]
        moid_au=raw["hazard"].get("moid_au"),
        estimated_diameter_m=raw["hazard"].get("estimated_diameter_m"),
        absolute_magnitude_h=raw["hazard"].get("absolute_magnitude_h"),
        neo_class=raw["hazard"]["neo_class"],  # type: ignore[arg-type]
        alert_pathway=raw["hazard"]["alert_pathway"],  # type: ignore[arg-type]
        explanation=explanation,
        orbital_elements=orbital,
    )
    metadata = ScoringMetadata(**raw["metadata"])
    return ScoredNEO(
        tracklet=tracklet,
        features=features,
        posterior=posterior,
        hazard=hazard,
        metadata=metadata,
    )


def export(input_path: str, output_dir: str) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    with open(input_path) as f:
        records = json.load(f)

    if isinstance(records, dict):
        records = [records]

    exported = 0
    skipped = 0
    for raw in records:
        try:
            neo = _parse_scored_neo(raw)
        except Exception as e:
            print(f"SKIP (parse error): {e}")
            skipped += 1
            continue

        pathway = neo.hazard.alert_pathway
        if pathway not in ("mpc_submission", "neocp_followup", "nasa_pdco_notify"):
            print(f"SKIP {neo.tracklet.object_id}: pathway={pathway}")
            skipped += 1
            continue

        report = format_mpc_report(neo)
        fname = out / f"mpc_{neo.tracklet.object_id}.txt"
        fname.write_text(report)
        print(f"Wrote: {fname}")
        exported += 1

    print(f"\nExported {exported} report(s), skipped {skipped}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export MPC observation reports")
    parser.add_argument("--input", required=True, help="JSON file with scored NEO records")
    parser.add_argument("--output-dir", default="mpc_reports", help="Output directory")
    args = parser.parse_args()
    export(args.input, args.output_dir)


if __name__ == "__main__":
    main()
