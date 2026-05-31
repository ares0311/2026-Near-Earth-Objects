"""Batch aperture-flux computation for pipeline candidates.

Usage:
    python Skills/compute_source_fluxes.py data/sample_tracklets.json
    python Skills/compute_source_fluxes.py data/sample_tracklets.json --aperture 7.0
    python Skills/compute_source_fluxes.py data/sample_tracklets.json --json
"""

from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "src")

from detect import compute_source_flux


def _load_tracklets(path: str) -> list[dict]:
    with open(path) as fh:
        data = json.load(fh)
    if isinstance(data, list):
        return data
    return data.get("tracklets", [])


class _Obs:
    def __init__(self, d: dict) -> None:
        for k, v in d.items():
            setattr(self, k, v)


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch source flux computation")
    parser.add_argument("input", help="Path to tracklet JSON file")
    parser.add_argument("--aperture", type=float, default=5.0, help="Aperture radius in pixels")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    tracklets = _load_tracklets(args.input)
    rows = []
    for trk in tracklets:
        oid = trk.get("object_id", "unknown")
        observations = trk.get("observations", [])
        fluxes = []
        for obs_dict in observations:
            obs = _Obs(obs_dict)
            flux = compute_source_flux(obs, aperture_radius_px=args.aperture)
            fluxes.append(flux)
        valid = [f for f in fluxes if f is not None]
        mean_flux = sum(valid) / max(1, len(valid))
        rows.append({
            "object_id": oid,
            "n_obs": len(observations),
            "mean_flux": round(mean_flux, 4) if fluxes else None,
            "fluxes": fluxes,
        })

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"{'Object ID':<40} {'N obs':>6} {'Mean flux':>12}")
        print("-" * 62)
        for row in rows:
            mf = f"{row['mean_flux']:.4f}" if row["mean_flux"] is not None else "N/A"
            print(f"{row['object_id']:<40} {row['n_obs']:>6} {mf:>12}")


if __name__ == "__main__":
    main()
