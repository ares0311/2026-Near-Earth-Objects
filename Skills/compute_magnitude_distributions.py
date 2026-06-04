"""Magnitude distribution histogram from a tracklet or fetch-result JSON file.

Usage:
    python Skills/compute_magnitude_distributions.py data/sample_tracklets.json [--bins N] [--json]

Reads a tracklet JSON file, extracts all observation magnitudes, and prints
an equal-width histogram across the observed magnitude range.
"""
import json
import sys

sys.path.insert(0, "src")

from fetch import compute_magnitude_distribution
from schemas import FetchProvenance, FetchResult, Observation


def _build_fetch_result(tracklets: list) -> FetchResult:
    observations = []
    for t in tracklets:
        for obs in t.get("observations", []):
            try:
                observations.append(
                    Observation(
                        obs_id=obs["obs_id"],
                        ra_deg=obs["ra_deg"],
                        dec_deg=obs["dec_deg"],
                        jd=obs["jd"],
                        mag=obs.get("mag", 99.0),
                        mag_err=obs.get("mag_err", 0.1),
                        filter_band=obs.get("filter_band", "r"),
                        mission=obs.get("mission", "ZTF"),
                    )
                )
            except Exception:
                continue
    provenance = FetchProvenance(
        surveys=["ZTF"],
        query_ra_deg=0.0,
        query_dec_deg=0.0,
        query_radius_deg=1.0,
        start_jd=0.0,
        end_jd=0.0,
    )
    return FetchResult(alerts=observations, provenance=provenance)


def main(argv: list[str]) -> None:
    as_json = "--json" in argv
    n_bins = 10
    paths = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--bins" and i + 1 < len(argv):
            n_bins = int(argv[i + 1])
            i += 2
        elif arg.startswith("--"):
            i += 1
        else:
            paths.append(arg)
            i += 1

    if not paths:
        print("Usage: compute_magnitude_distributions.py <tracklets.json> [--bins N] [--json]",
              file=sys.stderr)
        sys.exit(1)

    with open(paths[0]) as fh:
        data = json.load(fh)
    tracklets = data if isinstance(data, list) else [data]
    fetch_result = _build_fetch_result(tracklets)
    hist = compute_magnitude_distribution(fetch_result, n_bins=n_bins)

    if as_json:
        print(json.dumps(hist, indent=2))
    else:
        edges = hist["bin_edges"]
        counts = hist["counts"]
        print(f"Magnitude histogram (n_total={hist['n_total']}, bins={n_bins})")
        print(f"{'Bin range':<22}  Count")
        print("-" * 32)
        for i, cnt in enumerate(counts):
            print(f"[{edges[i]:.2f}, {edges[i+1]:.2f})      {cnt:>5}")


if __name__ == "__main__":
    main(sys.argv[1:])
