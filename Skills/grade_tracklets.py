"""
grade_tracklets.py — Batch-grade tracklets from a JSON file.

Usage:
    python Skills/grade_tracklets.py data/sample_tracklets.json
    python Skills/grade_tracklets.py data/sample_tracklets.json --json

Exit 0 on success; exit 1 if no tracklets found.
"""
from __future__ import annotations

import argparse
import json
import sys

PYTHONPATH_SRC = __import__("pathlib").Path(__file__).resolve().parents[1] / "src"
if str(PYTHONPATH_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHONPATH_SRC))

from link import compute_tracklet_grade  # noqa: E402
from schemas import Observation, Tracklet  # noqa: E402


def _load_tracklets(path: str) -> list[object]:
    with open(path) as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = [data]
    tracklets: list[object] = []
    for item in data:
        if "observations" not in item:
            continue
        obs_list = []
        for o in item["observations"]:
            obs_list.append(
                Observation(
                    obs_id=o.get("obs_id", "unk"),
                    ra_deg=float(o["ra_deg"]),
                    dec_deg=float(o["dec_deg"]),
                    jd=float(o["jd"]),
                    mag=float(o.get("mag", o.get("magnitude", 20.0))),
                    mag_err=float(o.get("mag_err", o.get("magnitude_error", 0.1))),
                    filter_band=o.get("filter_band", o.get("band", "r")),
                    mission=o.get("mission", o.get("survey", "ZTF")),  # type: ignore[arg-type]
                )
            )
        if len(obs_list) < 2:
            continue
        t = Tracklet(
            object_id=item.get("object_id", item.get("tracklet_id", "unknown")),
            observations=tuple(obs_list),
            arc_days=float(item.get("arc_days", 0.0)),
            motion_rate_arcsec_per_hour=float(
                item.get("motion_rate_arcsec_per_hour", 0.0)
            ),
            motion_pa_degrees=float(item.get("motion_pa_degrees", 0.0)),
        )
        tracklets.append(t)
    return tracklets


def grade_tracklets(path: str, as_json: bool = False) -> int:
    tracklets = _load_tracklets(path)
    if not tracklets:
        print("No valid tracklets found.", file=sys.stderr)
        return 1

    results = []
    for t in tracklets:
        grade = compute_tracklet_grade(t)
        results.append(
            {
                "object_id": getattr(t, "object_id", "unknown"),
                "grade": grade,
                "arc_days": getattr(t, "arc_days", None),
                "n_obs": len(getattr(t, "observations", [])),
            }
        )

    if as_json:
        print(json.dumps(results, indent=2))
    else:
        print(f"{'Object ID':<24} {'Grade':>5}  {'Arc (d)':>8}  {'N obs':>5}")
        print("-" * 48)
        for r in results:
            print(
                f"{r['object_id']:<24} {r['grade']:>5}  "
                f"{r['arc_days']:>8.3f}  {r['n_obs']:>5}"
            )
        print(f"\n{len(results)} tracklet(s) graded.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch-grade tracklets from a JSON file using arc, nights, and RMS."
    )
    parser.add_argument("input", help="Path to tracklet JSON file")
    parser.add_argument(
        "--json", action="store_true", dest="as_json", help="Output as JSON"
    )
    args = parser.parse_args()
    sys.exit(grade_tracklets(args.input, as_json=args.as_json))


if __name__ == "__main__":
    main()
