"""Find and display the longest tracklet (by arc_days) from a JSON file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from link import find_longest_tracklet


def _load_tracklets(path: str) -> list:
    data = json.loads(Path(path).read_text())
    if isinstance(data, list):
        return [SimpleNamespace(**t) for t in data]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Find the longest tracklet in a JSON file")
    parser.add_argument("input", nargs="?", help="Path to tracklet JSON file")
    parser.add_argument("--input", dest="input_flag", help="Path to tracklet JSON file (flag form)")
    parser.add_argument("--json", action="store_true", dest="json_out", help="Print JSON")
    args = parser.parse_args()

    path = args.input or args.input_flag
    if not path:
        print("Error: provide a JSON file path.", file=sys.stderr)
        sys.exit(1)

    tracklets = _load_tracklets(path)
    result = find_longest_tracklet(tracklets)

    if result is None:
        if args.json_out:
            print(json.dumps(None))
        else:
            print("No tracklets found.")
        return

    obj_id = getattr(result, "object_id", "unknown")
    arc = getattr(result, "arc_days", 0.0)
    obs = getattr(result, "observations", None)
    n_obs = len(obs) if obs is not None else 0
    rate = getattr(result, "motion_rate_arcsec_per_hour", None)

    if args.json_out:
        print(json.dumps({
            "object_id": obj_id,
            "arc_days": arc,
            "n_observations": n_obs,
            "motion_rate_arcsec_per_hour": rate,
        }, indent=2))
        return

    print(f"Longest tracklet: {obj_id}")
    print(f"  Arc (days):             {arc:.4f}")
    print(f"  Observations:           {n_obs}")
    print(f"  Motion rate (arcsec/h): {rate}")


if __name__ == "__main__":
    main()
