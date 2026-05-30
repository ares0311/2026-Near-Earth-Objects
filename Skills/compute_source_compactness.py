"""Compute source compactness for each observation in a tracklet JSON file.

Usage
-----
    python Skills/compute_source_compactness.py --input data/sample_tracklets.json

    python Skills/compute_source_compactness.py --input data/sample_tracklets.json --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Compute source compactness for observations in tracklet JSON."
    )
    parser.add_argument("--input", required=True, help="Path to tracklet JSON file")
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output as JSON array",
    )
    args = parser.parse_args(argv)

    from detect import compute_source_compactness
    from schemas import Tracklet

    with open(args.input) as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        raw = [raw]

    rows = []
    for item in raw:
        try:
            tracklet = Tracklet(**item)
        except Exception:
            continue
        object_id = tracklet.object_id
        for obs in tracklet.observations:
            compactness = compute_source_compactness(obs)
            rows.append({
                "object_id": object_id,
                "obs_id": obs.obs_id,
                "compactness": compactness,
            })

    if args.as_json:
        print(json.dumps(rows, indent=2))
        return

    if not rows:
        print("No observations found.")
        return

    hdr = f"{'object_id':<20} {'obs_id':<20} {'compactness':>12}"
    print(hdr)
    print("-" * len(hdr))
    for row in rows:
        cval = f"{row['compactness']:.6f}" if row["compactness"] is not None else "        N/A"
        print(f"{row['object_id']:<20} {row['obs_id']:<20} {cval:>12}")


if __name__ == "__main__":
    main()
