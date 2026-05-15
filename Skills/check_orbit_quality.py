"""Check orbit quality for a list of tracklets from a JSON file.

Usage:
    python Skills/check_orbit_quality.py <tracklets.json> [--json]

For each tracklet, reports: object_id, arc_days, n_nights, quality_code,
arc_warning, recommended_action, and (if an orbit can be fit) semi-major axis,
eccentricity, inclination, and NEO class.

Exit code 0 always (informational tool only).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from orbit import arc_quality_report, classify_neo, fit_orbit  # noqa: E402
from schemas import Observation, Tracklet  # noqa: E402


def _load_tracklets(path: Path) -> list[Tracklet]:
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        data = [data]
    result: list[Tracklet] = []
    for item in data:
        obs = [Observation(**o) for o in item["observations"]]
        result.append(Tracklet(
            object_id=item["object_id"],
            observations=tuple(obs),
            arc_days=item["arc_days"],
            motion_rate_arcsec_per_hour=item["motion_rate_arcsec_per_hour"],
            motion_pa_degrees=item["motion_pa_degrees"],
        ))
    return result


def assess_tracklet(tracklet: Tracklet) -> dict:
    report = arc_quality_report(tracklet)
    result: dict = {
        "object_id": tracklet.object_id,
        **report,
        "orbit": None,
    }
    elements = fit_orbit(tracklet)
    if elements is not None:
        result["orbit"] = {
            "semi_major_axis_au": round(elements.semi_major_axis_au, 4),
            "eccentricity": round(elements.eccentricity, 4),
            "inclination_deg": round(elements.inclination_deg, 2),
            "perihelion_au": round(elements.perihelion_au, 4),
            "aphelion_au": round(elements.aphelion_au, 4),
            "neo_class": classify_neo(elements),
            "quality_code": elements.quality_code,
        }
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Check orbit quality for tracklets.")
    parser.add_argument("input", help="Path to tracklets JSON file")
    parser.add_argument("--json", action="store_true", dest="json_out",
                        help="Output results as JSON")
    args = parser.parse_args(argv)

    tracklets = _load_tracklets(Path(args.input))
    assessments = [assess_tracklet(t) for t in tracklets]

    if args.json_out:
        print(json.dumps(assessments, indent=2))
        return

    for a in assessments:
        print(f"\n{'='*60}")
        print(f"Object : {a['object_id']}")
        print(f"Arc    : {a['arc_days']:.3f} d  |  {a['n_nights']} nights  |  "
              f"{a['n_observations']} obs")
        print(f"Quality: code={a['quality_code']}")
        if a["arc_warning"]:
            print(f"Warning: {a['arc_warning']}")
        print(f"Action : {a['recommended_action']}")
        if a["orbit"]:
            o = a["orbit"]
            print(f"Orbit  : a={o['semi_major_axis_au']} AU  e={o['eccentricity']}  "
                  f"i={o['inclination_deg']}°  class={o['neo_class']}")
        else:
            print("Orbit  : not available (arc too short)")

    print(f"\n{len(assessments)} tracklet(s) assessed.")


if __name__ == "__main__":
    main()
