"""Compute field overlap fraction between two fetch-result JSON files.

Usage
-----
    python Skills/compute_field_overlap.py result1.json result2.json

    python Skills/compute_field_overlap.py result1.json result2.json --json
"""

from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _load_fetch_result(path: str) -> object:
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):
        alerts_raw = data
    elif isinstance(data, dict) and "alerts" in data:
        alerts_raw = data["alerts"]
    else:
        alerts_raw = []
    obs_list = []
    for item in alerts_raw:
        if isinstance(item, dict):
            obs = types.SimpleNamespace(
                ra_deg=float(item.get("ra_deg", 0.0)),
                dec_deg=float(item.get("dec_deg", 0.0)),
            )
            obs_list.append(obs)
    result = types.SimpleNamespace(alerts=obs_list)
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Compute fraction of observations in result1 within 0.1 deg of result2."
    )
    parser.add_argument("result1", help="Path to first fetch-result JSON file")
    parser.add_argument("result2", help="Path to second fetch-result JSON file")
    parser.add_argument("--json", dest="as_json", action="store_true",
                        help="Output as JSON object")
    args = parser.parse_args(argv)

    from fetch import compute_field_overlap

    r1 = _load_fetch_result(args.result1)
    r2 = _load_fetch_result(args.result2)
    overlap = compute_field_overlap(r1, r2)

    if args.as_json:
        print(json.dumps({
            "result1": args.result1,
            "result2": args.result2,
            "overlap_fraction": overlap,
            "n_alerts_result1": len(r1.alerts),
            "n_alerts_result2": len(r2.alerts),
        }, indent=2))
        return

    print(f"Result 1: {args.result1}  ({len(r1.alerts)} observations)")
    print(f"Result 2: {args.result2}  ({len(r2.alerts)} observations)")
    print(f"Field overlap fraction: {overlap:.4f}")


if __name__ == "__main__":
    main()
