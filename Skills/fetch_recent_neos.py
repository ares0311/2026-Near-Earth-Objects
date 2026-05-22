"""Fetch recently announced NEOs from the MPC catalog.

Usage
-----
    python Skills/fetch_recent_neos.py
    python Skills/fetch_recent_neos.py --n-days 60 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Fetch recently announced NEOs from the MPC catalog."
    )
    parser.add_argument(
        "--n-days",
        type=int,
        default=30,
        help="Number of days to look back for recent NEO discoveries (default: 30)",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output as JSON array",
    )
    args = parser.parse_args(argv)

    try:
        from fetch import fetch_recent_mpc_neos

        observations = fetch_recent_mpc_neos(n_days=args.n_days)

        if args.as_json:
            print(json.dumps([o.model_dump() for o in observations], indent=2))
            sys.exit(0)

        if not observations:
            print("No recent NEOs found.")
            sys.exit(0)

        hdr = f"{'obs_id':<25} {'ra_deg':>8} {'dec_deg':>9} {'mag':>6}"
        print(hdr)
        print("-" * len(hdr))
        for obs in observations:
            print(
                f"{obs.obs_id:<25} {obs.ra_deg:>8.4f} {obs.dec_deg:>9.4f} {obs.mag:>6.2f}"
            )
        sys.exit(0)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
