"""
compute_position_residuals.py — Batch position residuals for tracklets.

Reads tracklet JSON from --input, computes per-observation position residuals
(arcsec) from a linear motion fit, and prints a summary table.

Usage:
    python Skills/compute_position_residuals.py
    python Skills/compute_position_residuals.py --input data/sample_tracklets.json
    python Skills/compute_position_residuals.py --json

Exit 0 on success.
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "src"))

from link import compute_position_residuals  # noqa: E402
from schemas import Observation, Tracklet  # noqa: E402


def _load_tracklets(path: str) -> list[Tracklet]:
    with open(path) as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = [data]
    tracklets: list[Tracklet] = []
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
                    mag=float(o.get("mag", 20.0)),
                    mag_err=float(o.get("mag_err", 0.1)),
                    mission=o.get("mission", "ZTF"),
                    filter_band=o.get("filter_band", "r"),
                )
            )
        tracklets.append(
            Tracklet(
                object_id=item.get("object_id", "unknown"),
                observations=tuple(obs_list),
                arc_days=float(item.get("arc_days", 0.0)),
                motion_rate_arcsec_per_hour=float(item.get("motion_rate_arcsec_per_hour", 0.0)),
                motion_pa_degrees=float(item.get("motion_pa_degrees", 0.0)),
            )
        )
    return tracklets


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch position residuals for tracklets")
    parser.add_argument(
        "--input",
        default="data/sample_tracklets.json",
        help="Path to tracklet JSON file",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of table",
    )
    args = parser.parse_args()

    tracklets = _load_tracklets(args.input)
    rows = []
    for t in tracklets:
        residuals = compute_position_residuals(t)
        n_obs = len(residuals)
        mean_res = sum(residuals) / n_obs if n_obs > 0 else 0.0
        max_res = max(residuals) if n_obs > 0 else 0.0
        rows.append({
            "object_id": t.object_id,
            "n_obs": n_obs,
            "mean_residual_arcsec": round(mean_res, 4),
            "max_residual_arcsec": round(max_res, 4),
        })

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        header = f"{'object_id':<20} {'n_obs':>6} {'mean_res(arcsec)':>18} {'max_res(arcsec)':>17}"
        print(header)
        print("-" * len(header))
        for row in rows:
            print(
                f"{row['object_id']:<20} {row['n_obs']:>6} "
                f"{row['mean_residual_arcsec']:>18.4f} {row['max_residual_arcsec']:>17.4f}"
            )


if __name__ == "__main__":
    main()
