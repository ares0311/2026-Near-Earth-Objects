"""Export per-candidate plain-text reports from a scored NEO JSON file.

Each candidate gets its own section (or its own file with --split) containing
observation details, orbital elements, hazard assessment, and classification
posterior.

Usage:
    python Skills/export_candidate_report.py data/sample_tracklets.json
    python Skills/export_candidate_report.py data/sample_tracklets.json --split --out-dir reports/
    python Skills/export_candidate_report.py data/sample_tracklets.json --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _format_candidate(neo: dict) -> str:
    """Format a single ScoredNEO dict as a plain-text report string."""
    tracklet = neo.get("tracklet", {})
    hazard = neo.get("hazard", {})
    features = neo.get("features", {})
    posterior = neo.get("posterior", {})
    metadata = neo.get("metadata", {})

    obj_id = tracklet.get("object_id", "unknown")
    n_obs = len(tracklet.get("observations", []))
    arc_days = tracklet.get("arc_days", 0.0)
    rate = tracklet.get("motion_rate_arcsec_per_hour", 0.0)
    pa = tracklet.get("motion_pa_degrees", 0.0)

    neo_class = hazard.get("neo_class", "unknown")
    hazard_flag = hazard.get("hazard_flag", "unknown")
    alert_pathway = hazard.get("alert_pathway", "unknown")
    moid_au = hazard.get("moid_au")
    diam_m = hazard.get("estimated_diameter_m")
    abs_mag_h = hazard.get("absolute_magnitude_h")
    explanation = hazard.get("explanation", {})

    discovery_priority = metadata.get("discovery_priority", 0.0)
    followup_value = metadata.get("followup_value", 0.0)
    scientific_interest = metadata.get("scientific_interest", 0.0)
    model_version = metadata.get("model_version", "?")

    lines = [
        f"Candidate Report: {obj_id}",
        "=" * (19 + len(obj_id)),
        "",
        "NOTICE: No impact probability is asserted here.",
        "Consult MPC/CNEOS for authoritative hazard assessment.",
        "",
        "--- Tracklet ---",
        f"  Object ID            : {obj_id}",
        f"  Observations         : {n_obs}",
        f"  Arc length (days)    : {arc_days:.4f}",
        f"  Motion rate (as/hr)  : {rate:.2f}",
        f"  Motion PA (deg)      : {pa:.1f}",
        "",
        "--- Hazard Assessment ---",
        f"  NEO class            : {neo_class}",
        f"  Hazard flag          : {hazard_flag}",
        f"  Alert pathway        : {alert_pathway}",
        f"  MOID (AU)            : {moid_au if moid_au is not None else 'N/A'}",
        f"  Est. diameter (m)    : {diam_m if diam_m is not None else 'N/A'}",
        f"  Absolute magnitude H : {abs_mag_h if abs_mag_h is not None else 'N/A'}",
        "",
        "--- Classification Posterior ---",
        f"  neo_candidate        : {posterior.get('neo_candidate', 0.0):.4f}",
        f"  known_object         : {posterior.get('known_object', 0.0):.4f}",
        f"  main_belt_asteroid   : {posterior.get('main_belt_asteroid', 0.0):.4f}",
        f"  stellar_artifact     : {posterior.get('stellar_artifact', 0.0):.4f}",
        f"  other_solar_system   : {posterior.get('other_solar_system', 0.0):.4f}",
        "",
        "--- Candidate Features (selected) ---",
        f"  real_bogus_score     : {features.get('real_bogus_score')}",
        f"  motion_consistency   : {features.get('motion_consistency_score')}",
        f"  orbit_quality_score  : {features.get('orbit_quality_score')}",
        f"  moid_score           : {features.get('moid_score')}",
        f"  known_object_score   : {features.get('known_object_score')}",
        "",
        "--- Scoring Metadata ---",
        f"  Discovery priority   : {discovery_priority:.4f}",
        f"  Follow-up value      : {followup_value:.4f}",
        f"  Scientific interest  : {scientific_interest:.4f}",
        f"  Model version        : {model_version}",
    ]

    if explanation:
        lines += ["", "--- Explanation ---"]
        for k, v in explanation.items():
            lines.append(f"  {k:<22} : {v}")

    lines.append("")
    return "\n".join(lines)


def export_candidate_report(
    neos: list[dict], split: bool = False, out_dir: Path | None = None
) -> list[dict]:
    """Generate per-candidate report strings.

    Returns a list of dicts with keys ``object_id`` and ``report``.
    When *split* is True and *out_dir* is provided, also writes each report
    to ``<out_dir>/<object_id>.txt``.
    """
    reports = []
    for neo in neos:
        obj_id = neo.get("tracklet", {}).get("object_id", "unknown")
        text = _format_candidate(neo)
        reports.append({"object_id": obj_id, "report": text})
        if split and out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
            safe_name = obj_id.replace("/", "_").replace(" ", "_")
            (out_dir / f"{safe_name}.txt").write_text(text)
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export per-candidate reports from scored NEO JSON"
    )
    parser.add_argument("input", help="JSON file with list of ScoredNEO dicts")
    parser.add_argument("--split", action="store_true", help="write one file per candidate")
    parser.add_argument("--out-dir", default="reports", help="directory for split output files")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="output as JSON list instead of plain text")
    args = parser.parse_args()

    data_path = Path(args.input)
    if not data_path.exists():
        print(f"ERROR: {data_path} not found", file=sys.stderr)
        sys.exit(1)

    with data_path.open() as f:
        neos = json.load(f)

    if not isinstance(neos, list):
        print("ERROR: JSON file must contain a list of ScoredNEO dicts", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out_dir) if args.split else None
    reports = export_candidate_report(neos, split=args.split, out_dir=out_dir)

    if args.as_json:
        print(json.dumps([{"object_id": r["object_id"]} for r in reports], indent=2))
    else:
        for r in reports:
            print(r["report"])
            print("-" * 60)

    if args.split and out_dir:
        print(f"Wrote {len(reports)} report(s) to {out_dir}/", file=sys.stderr)


if __name__ == "__main__":
    main()
