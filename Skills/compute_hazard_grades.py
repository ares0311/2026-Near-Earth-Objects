"""Batch hazard grade computation from scored NEO JSON."""

from __future__ import annotations

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute hazard grades (A/B/C/D) for scored NEO candidates."
    )
    parser.add_argument("input", help="Path to JSON file (list of ScoredNEO dicts).")
    parser.add_argument(
        "--threshold",
        type=str,
        default=None,
        choices=["A", "B", "C", "D"],
        help="Only show candidates with grade ≤ threshold (A is highest risk).",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON instead of a table.")
    args = parser.parse_args()

    try:
        with open(args.input) as fh:
            data = json.load(fh)
    except Exception as exc:
        print(f"ERROR: could not read {args.input}: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, list):
        data = [data]

    sys.path.insert(0, "src")
    try:
        from score import compute_hazard_grade, compute_weighted_hazard_score
    except ImportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    from types import SimpleNamespace

    _GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}
    threshold_rank = _GRADE_ORDER.get(args.threshold, 3) if args.threshold else 3

    rows = []
    for item in data:
        object_id = (
            item.get("tracklet", {}).get("object_id")
            or item.get("object_id", "unknown")
        )
        hazard = item.get("hazard", {})
        features = item.get("features", {})
        metadata = item.get("metadata", {})

        hazard_ns = SimpleNamespace(
            hazard_flag=hazard.get("hazard_flag", "unknown"),
            moid_au=hazard.get("moid_au"),
            neo_class=hazard.get("neo_class", "unknown"),
            alert_pathway=hazard.get("alert_pathway", "internal_candidate"),
            estimated_diameter_m=hazard.get("estimated_diameter_m"),
            absolute_magnitude_h=hazard.get("absolute_magnitude_h"),
        )
        features_ns = SimpleNamespace(
            orbit_quality_score=features.get("orbit_quality_score"),
            moid_score=features.get("moid_score"),
        )
        metadata_ns = SimpleNamespace(
            discovery_priority=metadata.get("discovery_priority", 0.0),
            followup_value=metadata.get("followup_value", 0.0),
            scientific_interest=metadata.get("scientific_interest", 0.0),
        )

        neo_ns = SimpleNamespace(
            hazard=hazard_ns,
            features=features_ns,
            metadata=metadata_ns,
        )

        try:
            score = compute_weighted_hazard_score(neo_ns)
            grade = compute_hazard_grade(neo_ns)
        except Exception as exc:
            print(f"WARNING: could not grade {object_id}: {exc}", file=sys.stderr)
            score = None
            grade = "D"

        if _GRADE_ORDER.get(grade, 3) <= threshold_rank:
            rows.append({
                "object_id": object_id,
                "grade": grade,
                "weighted_hazard_score": round(score, 4) if score is not None else None,
                "hazard_flag": hazard.get("hazard_flag", "unknown"),
                "moid_au": hazard.get("moid_au"),
            })

    rows.sort(key=lambda r: (_GRADE_ORDER.get(r["grade"], 3), -(r["weighted_hazard_score"] or 0.0)))

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        if not rows:
            print("No candidates matching criteria.")
        else:
            print(
                f"{'Object':<24s} {'Grade':>5s} {'W.Hazard':>10s}"
                f" {'MOID (AU)':>10s}  Hazard Flag"
            )
            print("-" * 72)
            for r in rows:
                score_str = (
                    f"{r['weighted_hazard_score']:.4f}"
                    if r["weighted_hazard_score"] is not None else "N/A"
                )
                moid_str = f"{r['moid_au']:.4f}" if r["moid_au"] is not None else "N/A"
                print(
                    f"{r['object_id']:<24s} {r['grade']:>5s} {score_str:>10s}"
                    f" {moid_str:>10s}  {r['hazard_flag']}"
                )
        print(f"\n{len(rows)} item(s).")

    sys.exit(0)


if __name__ == "__main__":
    main()
