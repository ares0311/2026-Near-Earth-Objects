"""Batch image contrast computation from tracklet JSON.

Usage:
    python Skills/compute_image_contrasts.py data/sample_tracklets.json [--json]
"""

from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "src")

import preprocess


def _build_obs(obs_dict: dict) -> object:
    from types import SimpleNamespace

    return SimpleNamespace(**obs_dict)


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch image contrast per observation.")
    parser.add_argument("input", help="Path to tracklet JSON file")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)

    tracklets = data if isinstance(data, list) else data.get("tracklets", [])
    rows = []
    for t in tracklets:
        tid = t.get("object_id", "?")
        for obs_dict in t.get("observations", []):
            obs = _build_obs(obs_dict)
            contrast = preprocess.compute_image_contrast(obs)
            rows.append(
                {
                    "object_id": tid,
                    "obs_id": obs_dict.get("obs_id", "?"),
                    "contrast": contrast,
                }
            )

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"{'object_id':<20} {'obs_id':<20} {'contrast':>12}")
        print("-" * 54)
        for r in rows:
            c = f"{r['contrast']:.4f}" if r["contrast"] is not None else "N/A"
            print(f"{r['object_id']:<20} {r['obs_id']:<20} {c:>12}")


if __name__ == "__main__":
    main()
