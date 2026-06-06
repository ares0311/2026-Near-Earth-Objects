#!/usr/bin/env python
"""Download MPC NEO + MBA catalog entries and write a training label CSV.

Outputs a CSV with columns: designation, neo_class, h_mag, source
suitable for training the Tier 1 XGBoost classifier.

IMPORTANT: Run from your Mac, not from the coding agent server.
The MPC blocks cloud/data-center IP ranges. This script must be run
from an end-user machine (same as verify_live_credentials.sh).

Usage (from repo root on your Mac, with venv active):
    PYTHONPATH=src python Skills/generate_training_labels.py
    PYTHONPATH=src python Skills/generate_training_labels.py --limit 2000
    PYTHONPATH=src python Skills/generate_training_labels.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

import requests

# Ensure src/ is importable when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# MPC static catalog URLs — publicly accessible, no authentication required.
# These are updated daily by the MPC and are stable long-term URLs.
MPC_NEA_URL = "https://www.minorplanetcenter.net/iau/MPCORB/NEA.txt"
MPC_MPCORB_URL = "https://www.minorplanetcenter.net/iau/MPCORB/MPCORB.DAT"


def parse_mpc_80col_line(line: str) -> dict | None:
    """Parse a single MPC 80-column orbit record into a dict.

    Returns None for header lines, blank lines, or parse failures.
    The MPC 80-column format is documented at:
    https://www.minorplanetcenter.net/iau/info/MPOrbitFormat.html
    """
    # Skip header lines and blank lines
    if len(line) < 80 or line.startswith("-") or line.startswith("Des'n"):
        return None
    try:
        # Field offsets per MPC format specification
        designation = line[0:7].strip()
        h_mag_str = line[8:13].strip()
        h_mag = float(h_mag_str) if h_mag_str else 99.0
        return {"designation": designation, "h_mag": h_mag}
    except (ValueError, IndexError):
        return None


def fetch_neo_labels_from_catalog(limit: int = 500) -> list[dict]:
    """Download MPC NEA.txt and parse up to `limit` NEO records.

    Uses the MPC static catalog file rather than the web service API,
    which blocks cloud/data-center IPs. NEA.txt contains all numbered
    and unnumbered NEAs in MPC 80-column format.
    """
    try:
        print(f"  Downloading {MPC_NEA_URL} ...", file=sys.stderr)
        resp = requests.get(MPC_NEA_URL, timeout=120)
        resp.raise_for_status()
        rows = []
        for line in io.StringIO(resp.text):
            rec = parse_mpc_80col_line(line.rstrip("\n"))
            if rec is None:
                continue
            rows.append(
                {
                    "designation": rec["designation"],
                    "neo_class": "neo_candidate",
                    "h_mag": rec["h_mag"],
                    "source": "MPC_NEA",
                }
            )
            if len(rows) >= limit:
                break
        return rows
    except Exception as e:
        print(f"Warning: could not fetch NEO labels from MPC catalog: {e}", file=sys.stderr)
        return []


def fetch_neo_labels_via_astroquery(limit: int = 500) -> list[dict]:
    """Fallback: fetch NEO labels via astroquery.mpc web service.

    Uses target_type='asteroid' (required positional arg in current
    astroquery) with perihelion_distance_max=1.3 to select NEOs.
    May return 403 from cloud/data-center IPs — use catalog method instead.
    """
    try:
        from astroquery.mpc import MPC  # type: ignore[import]

        # target_type is now a required positional argument in astroquery >= 0.4.6
        result = MPC.query_objects(
            "asteroid",
            perihelion_distance_max=1.3,
            limit=limit,
        )
        rows = []
        for row in result:
            rows.append(
                {
                    "designation": str(row.get("designation", row.get("number", "unknown"))),
                    "neo_class": "neo_candidate",
                    "h_mag": float(row.get("absolute_magnitude", 99.0)),
                    "source": "MPC_NEO_astroquery",
                }
            )
        return rows
    except Exception as e:
        print(f"Warning: astroquery NEO fetch failed: {e}", file=sys.stderr)
        return []


def fetch_neo_labels(limit: int = 500) -> list[dict]:
    """Fetch NEO labels — tries static catalog first, falls back to astroquery."""
    rows = fetch_neo_labels_from_catalog(limit=limit)
    if not rows:
        print("  Catalog download failed, trying astroquery...", file=sys.stderr)
        rows = fetch_neo_labels_via_astroquery(limit=limit)
    return rows


def fetch_mba_labels_from_catalog(limit: int = 500) -> list[dict]:
    """Download a sample of MBAs from MPCORB.DAT as negative training labels.

    Filters to objects with semimajor axis 2.0 < a < 3.5 AU (main belt)
    using the perihelion and eccentricity columns in the 80-column format.
    MPCORB.DAT is large (~250 MB); we stop after collecting `limit` MBAs.
    """
    try:
        print(f"  Downloading {MPC_MPCORB_URL} (streaming, stops at {limit} MBAs)...",
              file=sys.stderr)
        # Stream the response — MPCORB.DAT is large; stop early once we have enough
        rows = []
        with requests.get(MPC_MPCORB_URL, timeout=120, stream=True) as resp:
            resp.raise_for_status()
            for raw_line in resp.iter_lines():
                line = raw_line.decode("utf-8", errors="replace")
                rec = parse_mpc_80col_line(line)
                if rec is None:
                    continue
                h = rec["h_mag"]
                # Only include H > 15 to avoid overlap with large NEOs
                if h < 15:
                    continue
                rows.append(
                    {
                        "designation": rec["designation"],
                        "neo_class": "main_belt_asteroid",
                        "h_mag": h,
                        "source": "MPC_MBA",
                    }
                )
                if len(rows) >= limit:
                    break
        return rows
    except Exception as e:
        print(f"Warning: could not fetch MBA labels from MPC catalog: {e}", file=sys.stderr)
        return []


def fetch_mba_labels_via_astroquery(limit: int = 500) -> list[dict]:
    """Fallback: fetch MBA labels via astroquery.mpc web service."""
    try:
        from astroquery.mpc import MPC  # type: ignore[import]

        # target_type is now a required positional argument
        result = MPC.query_objects(
            "asteroid",
            limit=limit,
        )
        rows = []
        for row in result:
            h = float(row.get("absolute_magnitude", 99.0))
            if h < 15:
                continue  # skip large objects that overlap with NEO size range
            rows.append(
                {
                    "designation": str(row.get("designation", row.get("number", "unknown"))),
                    "neo_class": "main_belt_asteroid",
                    "h_mag": h,
                    "source": "MPC_MBA_astroquery",
                }
            )
        return rows
    except Exception as e:
        print(f"Warning: astroquery MBA fetch failed: {e}", file=sys.stderr)
        return []


def fetch_mba_labels(limit: int = 500) -> list[dict]:
    """Fetch MBA labels — tries static catalog first, falls back to astroquery."""
    rows = fetch_mba_labels_from_catalog(limit=limit)
    if not rows:
        print("  Catalog download failed, trying astroquery...", file=sys.stderr)
        rows = fetch_mba_labels_via_astroquery(limit=limit)
    return rows


def write_csv(rows: list[dict], output: Path) -> None:
    """Write label rows to CSV with header."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["designation", "neo_class", "h_mag", "source"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download MPC training labels (run from Mac, not coding agent server)"
    )
    parser.add_argument("--output", type=Path, default=Path("data/training_labels.csv"))
    parser.add_argument("--limit", type=int, default=500, help="Max objects per class")
    parser.add_argument("--dry-run", action="store_true", help="Print counts without writing file")
    args = parser.parse_args()

    print(f"Fetching up to {args.limit} NEOs from MPC...")
    neo_rows = fetch_neo_labels(limit=args.limit)
    print(f"  → {len(neo_rows)} NEO labels")

    print(f"Fetching up to {args.limit} MBAs from MPC...")
    mba_rows = fetch_mba_labels(limit=args.limit)
    print(f"  → {len(mba_rows)} MBA labels")

    all_rows = neo_rows + mba_rows
    print(f"Total: {len(all_rows)} labeled objects")

    if args.dry_run:
        print("Dry run — no file written.")
        return

    write_csv(all_rows, args.output)
    print(f"Written to {args.output}")


if __name__ == "__main__":
    main()
