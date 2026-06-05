"""Compute observation time span from a fetch-result JSON file.

Usage:
    python Skills/compute_observation_time_spans.py fetch_result.json [--json]

Reads a fetch-result JSON file and prints the total time span (max JD - min JD)
across all valid observations using compute_observation_time_span from fetch.py.
"""
import json
import sys
from types import SimpleNamespace

sys.path.insert(0, "src")

from fetch import compute_observation_time_span


def _load_obs(d: dict) -> SimpleNamespace:
    return SimpleNamespace(
        obs_id=d.get("obs_id", "unknown"),
        ra_deg=d.get("ra_deg", 0.0),
        dec_deg=d.get("dec_deg", 0.0),
        jd=d.get("jd", 0.0),
        mag=d.get("mag", 99.0),
        mag_err=d.get("mag_err", 0.0),
        filter_band=d.get("filter_band", "r"),
        real_bogus_score=d.get("real_bogus_score"),
        mission=d.get("mission", "ZTF"),
        cutout_science=None,
        cutout_reference=None,
        cutout_difference=None,
    )


def main(argv: list[str]) -> None:
    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("--")]

    if not paths:
        print("Usage: compute_observation_time_spans.py <fetch_result.json> [--json]",
              file=sys.stderr)
        sys.exit(1)

    with open(paths[0]) as fh:
        data = json.load(fh)

    if isinstance(data, list):
        alerts = [_load_obs(d) for d in data]
    elif isinstance(data, dict):
        alerts = [_load_obs(d) for d in data.get("alerts", [])]
    else:
        alerts = []

    fetch_result = SimpleNamespace(alerts=alerts, provenance=None)
    span = compute_observation_time_span(fetch_result)

    if as_json:
        print(json.dumps({
            "n_observations": len(alerts),
            "time_span_days": span,
        }, indent=2))
    else:
        print(f"Observations: {len(alerts)}")
        if span is None:
            print("Time span: N/A (fewer than 2 valid JDs)")
        else:
            print(f"Time span:    {span:.5f} days")


if __name__ == "__main__":
    main(sys.argv[1:])
