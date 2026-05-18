"""Validate a pipeline run JSON for completeness and consistency.

Checks all required fields are present, MOID values are physically
plausible, no impact probability claims are made, and all alert pathways
are valid.  Exits 0 on success, 1 on any validation failure.

Usage
-----
    python Skills/validate_pipeline_run.py data/pipeline_run.json

    python Skills/validate_pipeline_run.py data/pipeline_run.json --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

_VALID_PATHWAYS = {
    "mpc_submission", "neocp_followup", "nasa_pdco_notify",
    "internal_candidate", "known_object",
}
_VALID_HAZARD_FLAGS = {"pha_candidate", "close_approach", "nominal", "unknown"}
_MOID_MAX_PHYSICAL = 10.0
_FORBIDDEN_PHRASES = [
    "impact probability", "probability of impact", "chance of impact",
    "% chance", "percent chance",
]


def _validate_candidate(obj: dict) -> list[str]:
    issues: list[str] = []

    for key in ("tracklet", "features", "posterior", "hazard", "metadata"):
        if key not in obj:
            issues.append(f"missing required key: '{key}'")

    hazard = obj.get("hazard", {})
    pathway = hazard.get("alert_pathway")
    if pathway and pathway not in _VALID_PATHWAYS:
        issues.append(f"invalid alert_pathway: '{pathway}'")

    flag = hazard.get("hazard_flag")
    if flag and flag not in _VALID_HAZARD_FLAGS:
        issues.append(f"invalid hazard_flag: '{flag}'")

    moid = hazard.get("moid_au")
    if moid is not None:
        try:
            moid_f = float(moid)
            if moid_f < 0.0:
                issues.append(f"moid_au is negative: {moid_f}")
            elif moid_f > _MOID_MAX_PHYSICAL:
                issues.append(f"moid_au implausibly large: {moid_f} AU (>{_MOID_MAX_PHYSICAL})")
        except (TypeError, ValueError):
            issues.append(f"moid_au is not a number: {moid!r}")

    text_blob = json.dumps(obj).lower()
    for phrase in _FORBIDDEN_PHRASES:
        if phrase in text_blob:
            issues.append(f"forbidden impact-probability phrase detected: '{phrase}'")

    tracklet = obj.get("tracklet", {})
    obs = tracklet.get("observations", [])
    if isinstance(obs, list) and len(obs) < 2:
        issues.append(f"tracklet has fewer than 2 observations ({len(obs)} found)")

    return issues


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Validate a pipeline run JSON for completeness and consistency."
    )
    parser.add_argument("input", help="Path to pipeline run JSON (list of ScoredNEO dicts)")
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output validation results as JSON",
    )
    args = parser.parse_args(argv)

    with open(args.input) as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        raw = [raw]

    all_results = []
    any_failure = False
    for i, item in enumerate(raw):
        object_id = item.get("tracklet", {}).get("object_id", f"item[{i}]")
        issues = _validate_candidate(item)
        status = "PASS" if not issues else "FAIL"
        if issues:
            any_failure = True
        all_results.append({
            "object_id": object_id,
            "status": status,
            "issues": issues,
        })

    if args.as_json:
        print(json.dumps(all_results, indent=2))
    else:
        for entry in all_results:
            mark = "✓" if entry["status"] == "PASS" else "✗"
            print(f"[{mark}] {entry['object_id']}: {entry['status']}")
            for issue in entry["issues"]:
                print(f"      - {issue}")
        passed = sum(1 for r in all_results if r["status"] == "PASS")
        print(f"\n{passed}/{len(all_results)} candidates passed validation.")

    sys.exit(1 if any_failure else 0)


if __name__ == "__main__":
    main()
