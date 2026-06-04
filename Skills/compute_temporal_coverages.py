"""Batch temporal coverage summary from a fetch result or tracklet JSON file.

Usage:
    python Skills/compute_temporal_coverages.py data/sample_tracklets.json [--json]

The script reads tracklet JSON and synthesises a mock FetchResult from each
tracklet's observations, then reports min/max JD, span, and night count.
"""
import json
import sys

sys.path.insert(0, "src")

from fetch import compute_temporal_coverage
from schemas import FetchProvenance, FetchResult, Observation


def _build_fetch_result(tracklets: list) -> FetchResult:
    """Flatten all observations from a list of tracklet dicts into a FetchResult."""
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
                        real_bogus_score=obs.get("real_bogus_score"),
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
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        print("Usage: compute_temporal_coverages.py <tracklets.json> [--json]", file=sys.stderr)
        sys.exit(1)

    with open(paths[0]) as fh:
        data = json.load(fh)
    tracklets = data if isinstance(data, list) else [data]

    fetch_result = _build_fetch_result(tracklets)
    summary = compute_temporal_coverage(fetch_result)

    if as_json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Observations : {summary['n_observations']}")
        print(f"Min JD       : {summary['min_jd']}")
        print(f"Max JD       : {summary['max_jd']}")
        print(f"Span (days)  : {summary['span_days']}")
        print(f"Nights       : {summary['n_nights']}")


if __name__ == "__main__":
    main(sys.argv[1:])
