"""Batch-tag NEO class for tracklets using classify_neo_class from orbit.py.

Reads a JSON file of tracklets (or ScoredNEO dicts), fits a preliminary orbit
for each, derives the NEO class (amor/apollo/aten/ieo/unknown), and writes the
tagged results back as JSON.

Usage:
    python Skills/tag_neo_class.py data/sample_tracklets.json
    python Skills/tag_neo_class.py data/sample_tracklets.json --out tagged.json
    python Skills/tag_neo_class.py data/sample_tracklets.json --summary
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from orbit import classify_neo_class, fit_orbit


def _observations_from_dict(obs_list: list[dict]) -> list:
    """Convert raw dicts to Observation objects."""
    from schemas import Observation

    result = []
    for o in obs_list:
        try:
            result.append(Observation(**o))
        except Exception:
            pass
    return result


def _tag_tracklet(tracklet_dict: dict) -> dict:
    """Add 'neo_class' key to a tracklet dict by fitting an orbit."""
    obs_dicts = tracklet_dict.get("observations", [])
    observations = _observations_from_dict(obs_dicts)

    neo_class = "unknown"
    elements_dict: dict | None = None

    if len(observations) >= 2:
        try:
            orbit_result = fit_orbit(tuple(observations))
            if orbit_result.elements is not None:
                neo_class = classify_neo_class(orbit_result.elements)
                elements_dict = {
                    "semi_major_axis_au": orbit_result.elements.semi_major_axis_au,
                    "eccentricity": orbit_result.elements.eccentricity,
                    "inclination_deg": orbit_result.elements.inclination_deg,
                    "perihelion_au": orbit_result.elements.perihelion_au,
                    "aphelion_au": orbit_result.elements.aphelion_au,
                    "orbit_quality_code": orbit_result.elements.orbit_quality_code,
                }
        except Exception:
            pass

    tagged = dict(tracklet_dict)
    tagged["neo_class"] = neo_class
    if elements_dict is not None:
        tagged["orbital_elements"] = elements_dict
    return tagged


def tag_neo_class(records: list[dict]) -> list[dict]:
    """Tag each record (tracklet or ScoredNEO dict) with its NEO class.

    For ScoredNEO dicts, the tracklet sub-dict is tagged. For raw tracklet
    dicts (with an ``observations`` key at the top level), they are tagged
    directly.
    """
    tagged = []
    for rec in records:
        if "tracklet" in rec:
            # ScoredNEO dict — tag the nested tracklet
            inner = _tag_tracklet(rec["tracklet"])
            out = dict(rec)
            out["tracklet"] = inner
            # Also propagate neo_class to hazard if present
            if "hazard" in out and inner.get("neo_class") != "unknown":
                hazard = dict(out["hazard"])
                hazard["neo_class"] = inner["neo_class"]
                out["hazard"] = hazard
            tagged.append(out)
        elif "observations" in rec:
            # Raw tracklet dict
            tagged.append(_tag_tracklet(rec))
        else:
            tagged.append(dict(rec))
    return tagged


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch-tag NEO class from tracklet JSON")
    parser.add_argument("input", help="JSON file with tracklet or ScoredNEO dicts")
    parser.add_argument("--out", default=None, help="output JSON file (default: print to stdout)")
    parser.add_argument("--summary", action="store_true", help="print class distribution summary")
    args = parser.parse_args()

    data_path = Path(args.input)
    if not data_path.exists():
        print(f"ERROR: {data_path} not found", file=sys.stderr)
        sys.exit(1)

    with data_path.open() as f:
        records = json.load(f)

    if not isinstance(records, list):
        print("ERROR: JSON file must contain a list", file=sys.stderr)
        sys.exit(1)

    tagged = tag_neo_class(records)

    if args.summary:
        from collections import Counter

        def _get_class(r: dict) -> str:
            if "tracklet" in r:
                return r["tracklet"].get("neo_class", "unknown")
            return r.get("neo_class", "unknown")

        counts = Counter(_get_class(r) for r in tagged)
        print(f"Tagged {len(tagged)} records:")
        for cls, cnt in sorted(counts.items()):
            print(f"  {cls:<12} {cnt}")

    output = json.dumps(tagged, indent=2)
    if args.out:
        Path(args.out).write_text(output)
        print(f"Wrote {len(tagged)} tagged records to {args.out}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
