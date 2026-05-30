"""Batch along-track error computation for tracklets from a JSON file."""

import sys

sys.path.insert(0, "src")

import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute along-track RMS error for tracklets from JSON."
    )
    parser.add_argument(
        "--input",
        default="data/sample_tracklets.json",
        help="Path to tracklet JSON file (default: data/sample_tracklets.json)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    from link import compute_along_track_error

    with open(args.input) as fh:
        data = json.load(fh)

    tracklets = data if isinstance(data, list) else data.get("tracklets", [data])

    results = []
    for t in tracklets:
        object_id = t.get("object_id", "unknown")
        observations = t.get("observations", [])
        n_obs = len(observations)

        class _Obs:
            def __init__(self, d: dict) -> None:
                self.ra = float(d.get("ra_deg", d.get("ra", 0.0)))
                self.dec = float(d.get("dec_deg", d.get("dec", 0.0)))
                self.jd = float(d.get("jd", 0.0))

        class _Tracklet:
            def __init__(self, obs: list, pa: float) -> None:
                self.observations = tuple(_Obs(o) for o in obs)
                self.motion_pa_degrees = pa

        pa = float(t.get("motion_pa_degrees", 0.0))
        tracklet_obj = _Tracklet(observations, pa)
        error = compute_along_track_error(tracklet_obj)
        results.append(
            {
                "object_id": object_id,
                "n_obs": n_obs,
                "along_track_error_arcsec": error,
            }
        )

    if args.json:
        print(json.dumps(results, indent=2))
        return

    # Table output
    header = f"{'object_id':<24} {'n_obs':>5} {'along_track_error_arcsec':>26}"
    print(header)
    print("-" * len(header))
    for row in results:
        print(
            f"{row['object_id']:<24} {row['n_obs']:>5} {row['along_track_error_arcsec']:>26.6f}"
        )


if __name__ == "__main__":
    main()
