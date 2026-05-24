"""Generate a NightSummary from a pipeline run or scored NEO JSON file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate NightSummary from scored NEO JSON."
    )
    parser.add_argument("input", help="Path to JSON with list of ScoredNEOs")
    parser.add_argument("--night-jd", type=float, default=None,
                        help="Override night JD (default: median of observations)")
    parser.add_argument("--survey", default="ZTF",
                        choices=["ZTF", "ATLAS", "PanSTARRS", "CSS", "MPC"],
                        help="Survey mission label")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text())
    if not isinstance(data, list):
        data = [data]

    n_tracklets = len(data)
    n_new = 0
    n_known = 0
    n_pha = 0
    field_ids: set[str] = set()
    all_jds: list[float] = []

    for item in data:
        hazard = item.get("hazard") or {}
        pathway = hazard.get("alert_pathway", "internal_candidate")
        if pathway == "known_object":
            n_known += 1
        else:
            n_new += 1
        if hazard.get("hazard_flag") == "pha_candidate":
            n_pha += 1
        tracklet = item.get("tracklet") or {}
        for obs in tracklet.get("observations") or []:
            jd = obs.get("jd")
            if jd:
                all_jds.append(float(jd))
            fid = (obs.get("obs_id") or "").split("_")[0]
            if fid:
                field_ids.add(fid)

    night_jd = args.night_jd
    if night_jd is None and all_jds:
        night_jd = float(sorted(all_jds)[len(all_jds) // 2])
    night_jd = night_jd or 0.0

    summary = {
        "night_jd": night_jd,
        "survey": args.survey,
        "n_tracklets": n_tracklets,
        "n_new": n_new,
        "n_known": n_known,
        "n_pha_candidates": n_pha,
        "fields_covered": sorted(field_ids),
        "limiting_mag": None,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Night JD       : {summary['night_jd']:.2f}")
        print(f"Survey         : {summary['survey']}")
        print(f"Tracklets      : {summary['n_tracklets']}")
        print(f"New            : {summary['n_new']}")
        print(f"Known          : {summary['n_known']}")
        print(f"PHA candidates : {summary['n_pha_candidates']}")
        fields = ", ".join(summary["fields_covered"]) if summary["fields_covered"] else "—"
        print(f"Fields covered : {fields}")


if __name__ == "__main__":
    main()
