"""Fetch and display known PHAs from the MPC."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fetch import fetch_known_phas


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch known PHAs from MPC")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass disk cache")
    parser.add_argument("--json", action="store_true", dest="json_out", help="Print JSON")
    args = parser.parse_args()

    phas = fetch_known_phas(force_refresh=args.force_refresh)

    if args.json_out:
        print(json.dumps(phas, indent=2))
        return

    if not phas:
        print("No PHAs returned.")
        return

    header = f"{'Designation':<20} {'H':>6} {'MOID (AU)':>10} {'Class':<10}"
    print(header)
    print("-" * len(header))
    for p in phas:
        desig = str(p.get("designation", "unknown"))[:20]
        h = p.get("absolute_magnitude_h")
        moid = p.get("moid_au")
        cls = str(p.get("neo_class", "unknown"))
        h_str = f"{h:6.2f}" if h is not None else "   N/A"
        moid_str = f"{moid:10.6f}" if moid is not None else "    N/A   "
        print(f"{desig:<20} {h_str} {moid_str} {cls:<10}")

    print(f"\nTotal: {len(phas)} PHAs")


if __name__ == "__main__":
    main()
