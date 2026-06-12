#!/usr/bin/env python
"""Download MPC catalog entries and write approved training label manifests.

Outputs a CSV with columns: designation, neo_class, h_mag, source
suitable for training the Tier 1 XGBoost classifier.

Tier 3 pilot mode writes the approved four-class MPC manifest. The fifth
``stellar_artifact`` class is acquired separately from ALeRCE because the MPC
does not catalog instrumental artifacts.

IMPORTANT: Run from your Mac, not from the coding agent server.
The MPC blocks cloud/data-center IP ranges. This script must be run
from an end-user machine (same as verify_live_credentials.sh).

Usage (from repo root on your Mac, with venv active):
    PYTHONPATH=src python Skills/generate_training_labels.py
    PYTHONPATH=src python Skills/generate_training_labels.py --limit 2000
    PYTHONPATH=src python Skills/generate_training_labels.py --dry-run
    PYTHONPATH=src python Skills/generate_training_labels.py \
        --tier3-pilot --limit 50 \
        --output data/sequences/tier3_pilot_manifest.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

# Ensure src/ is importable when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# MPC static catalog URLs — publicly accessible, no authentication required.
# These are updated daily by the MPC and are stable long-term URLs.
MPC_NEA_URL = "https://www.minorplanetcenter.net/iau/MPCORB/NEA.txt"
MPC_MPCORB_URL = "https://www.minorplanetcenter.net/iau/MPCORB/MPCORB.DAT"
TIER3_FIELDNAMES = [
    "designation",
    "neo_class",
    "h_mag",
    "source",
    "sequence_window",
    "label_basis",
]


# Century prefix used in MPC 7-char packed provisional designations.
# Per https://www.minorplanetcenter.net/iau/info/PackedDes.html
_CENTURY_CODES: dict[str, int] = {"I": 1800, "J": 1900, "K": 2000}


def _unpack_designation(packed: str) -> str:
    """Convert a packed MPCORB designation to the form MPC.get_observations accepts.

    MPC.get_observations needs unpacked designations.  Two cases handled:

    1. Numbered objects — zero-padded integers like '00433' → '433'.
       MPC.get_observations('00433') returns None; '433' works correctly.

    2. Packed provisional designations — 7-char form like 'K23A00A' → '2023 AA'.
       Format (per MPC): [century][YY][half-month][sub2][order]
         century : I=1800s  J=1900s  K=2000s
         YY      : 2-digit year within century
         half-month : survey letter (A-Z, a-z)
         sub2    : 2-char subscript (digits 00-99; leading letter for 100+)
         order   : trailing order letter

    Anything that does not match either pattern is returned unchanged (safe
    fallback for comet designations already in unpacked form from astroquery).
    """
    stripped = packed.strip()
    # All-digit strings are packed numbered designations; strip leading zeros.
    if stripped.isdigit():
        return str(int(stripped))
    # 7-char strings beginning with a century code are packed provisional designations.
    if len(stripped) == 7 and stripped[0] in _CENTURY_CODES:
        try:
            year = _CENTURY_CODES[stripped[0]] + int(stripped[1:3])
            half_month = stripped[3]
            subscript_chars = stripped[4:6]
            order_letter = stripped[6]
            # Subscripts 0-99: plain digit pair.
            # Subscripts 100+: letter + digit (a0=100, a1=101, ..., b0=110, ...).
            if subscript_chars[0].isdigit():
                subscript = int(subscript_chars)
            else:
                subscript = (
                    (ord(subscript_chars[0].lower()) - ord("a") + 10) * 10
                    + int(subscript_chars[1])
                )
            if subscript == 0:
                return f"{year} {half_month}{order_letter}"
            return f"{year} {half_month}{order_letter}{subscript}"
        except (ValueError, IndexError):
            pass
    return stripped


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
        # Field offsets per MPC format specification.
        # Unpack the designation so MPC.get_observations can resolve it.
        designation = _unpack_designation(line[0:7])
        h_mag_str = line[8:13].strip()
        h_mag = float(h_mag_str) if h_mag_str else 99.0
        # MPCORB extends past column 80 with eccentricity and semimajor axis.
        eccentricity_text = line[70:79].strip() if len(line) >= 79 else ""
        semimajor_axis_text = line[92:103].strip() if len(line) >= 103 else ""
        return {
            "designation": designation,
            "h_mag": h_mag,
            "eccentricity": float(eccentricity_text) if eccentricity_text else None,
            "semimajor_axis_au": (
                float(semimajor_axis_text) if semimajor_axis_text else None
            ),
        }
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


def _is_numbered_designation(designation: str) -> bool:
    """Return whether an MPC packed designation represents a numbered object."""
    return designation.strip().isdigit()


def build_tier3_nea_rows(text: str, limit: int) -> list[dict]:
    """Build temporally distinct NEO-candidate and known-object manifest rows."""
    if limit < 1:
        raise ValueError("limit must be at least 1")

    candidates: list[dict] = []
    known: list[dict] = []
    for line in io.StringIO(text):
        record = parse_mpc_80col_line(line.rstrip("\n"))
        if record is None:
            continue
        designation = record["designation"]
        if _is_numbered_designation(designation):
            if len(known) < limit:
                known.append(
                    {
                        "designation": designation,
                        "neo_class": "known_object",
                        "h_mag": record["h_mag"],
                        "source": "MPC_NEA",
                        "sequence_window": "late",
                        "label_basis": "numbered NEO; late catalog-era observations",
                    }
                )
        elif len(candidates) < limit:
            candidates.append(
                {
                    "designation": designation,
                    "neo_class": "neo_candidate",
                    "h_mag": record["h_mag"],
                    "source": "MPC_NEA",
                    "sequence_window": "early",
                    "label_basis": "provisional NEO; earliest discovery-arc observations",
                }
            )
        if len(candidates) >= limit and len(known) >= limit:
            break
    return candidates + known


def fetch_tier3_nea_rows(limit: int) -> list[dict]:
    """Download NEA.txt and build the approved temporal NEO label classes."""
    print(f"  Downloading {MPC_NEA_URL} ...", file=sys.stderr)
    response = requests.get(MPC_NEA_URL, timeout=120)
    response.raise_for_status()
    return build_tier3_nea_rows(response.text, limit)


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
                semimajor_axis = rec["semimajor_axis_au"]
                eccentricity = rec["eccentricity"]
                # Use numbered, dynamically main-belt objects and exclude NEO orbits.
                if (
                    not _is_numbered_designation(rec["designation"])
                    or semimajor_axis is None
                    or eccentricity is None
                    or not 2.0 < semimajor_axis < 3.5
                    or semimajor_axis * (1.0 - eccentricity) <= 1.3
                    or h < 15
                ):
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


def fetch_tier3_mba_rows(limit: int) -> list[dict]:
    """Convert authoritative numbered MBA labels into Tier 3 manifest rows."""
    rows = fetch_mba_labels_from_catalog(limit)
    return [
        {
            **row,
            "sequence_window": "full",
            "label_basis": "numbered MPC object with 2<a<3.5 AU and q>1.3 AU",
        }
        for row in rows
    ]


def _catalog_value(row: object, *names: str, default: object = "") -> object:
    """Read a field from an astropy row or mapping without assuming one type."""
    for name in names:
        try:
            value = row[name]  # type: ignore[index]
        except (KeyError, IndexError, TypeError):
            continue
        if value is not None:
            return value
    return default


def fetch_other_solar_system_rows(
    limit: int,
    *,
    query_objects: Callable[..., Any] | None = None,
) -> list[dict]:
    """Fetch enough usable confirmed comets for the other-solar-system class."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if query_objects is None:
        from astroquery.mpc import MPC  # type: ignore[import]

        query_objects = MPC.query_objects

    # MPC comet searches can return multiple orbit solutions for one designation.
    # Fetch a bounded surplus and retain exactly the approved number of unique rows.
    query_limit = max(limit * 5, limit + 50)
    result = query_objects("comet", limit=query_limit)
    rows: list[dict] = []
    seen: set[str] = set()
    for row in result:
        designation = str(
            _catalog_value(row, "designation", "name", "number", default="")
        ).strip()
        if not designation or designation in seen:
            continue
        seen.add(designation)
        magnitude = _catalog_value(row, "absolute_magnitude", "H", default=99.0)
        try:
            h_mag = float(magnitude)
        except (TypeError, ValueError):
            h_mag = 99.0
        rows.append(
            {
                "designation": designation,
                "neo_class": "other_solar_system",
                "h_mag": h_mag,
                "source": "MPC_COMET",
                "sequence_window": "full",
                "label_basis": "confirmed MPC comet",
            }
        )
        if len(rows) >= limit:
            break
    return rows


def build_tier3_pilot_manifest(limit: int) -> list[dict]:
    """Acquire the four MPC-backed classes in the approved five-class policy."""
    nea_rows = fetch_tier3_nea_rows(limit)
    mba_rows = fetch_tier3_mba_rows(limit)
    other_rows = fetch_other_solar_system_rows(limit)
    rows = nea_rows + mba_rows + other_rows

    # Fail closed unless every MPC-backed class has the exact approved unique size.
    required = {
        "neo_candidate",
        "known_object",
        "main_belt_asteroid",
        "other_solar_system",
    }
    counts = {class_name: 0 for class_name in required}
    for row in rows:
        if row["neo_class"] in counts:
            counts[row["neo_class"]] += 1
    invalid_counts = {name: count for name, count in counts.items() if count != limit}
    designations = [str(row.get("designation", "")).strip() for row in rows]
    duplicate_count = len(designations) - len(set(designations))
    if invalid_counts or duplicate_count:
        raise RuntimeError(
            "Tier 3 pilot manifest is incomplete: "
            f"counts={invalid_counts}, duplicate_designations={duplicate_count}"
        )
    return rows


def write_csv(rows: list[dict], output: Path) -> None:
    """Write label rows to CSV with header."""
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = TIER3_FIELDNAMES if any("sequence_window" in row for row in rows) else [
        "designation",
        "neo_class",
        "h_mag",
        "source",
    ]
    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download MPC training labels (run from Mac, not coding agent server)"
    )
    parser.add_argument("--output", type=Path, default=Path("data/training_labels.csv"))
    parser.add_argument("--limit", type=int, default=500, help="Max objects per class")
    parser.add_argument("--dry-run", action="store_true", help="Print counts without writing file")
    parser.add_argument(
        "--tier3-pilot",
        action="store_true",
        help="Build the approved four-class MPC manifest for the Tier 3 pilot",
    )
    args = parser.parse_args()

    if args.tier3_pilot:
        print(f"Building approved Tier 3 MPC manifest with {args.limit} objects per class...")
        all_rows = build_tier3_pilot_manifest(args.limit)
        counts: dict[str, int] = {}
        for row in all_rows:
            counts[row["neo_class"]] = counts.get(row["neo_class"], 0) + 1
        print(json.dumps(counts, indent=2, sort_keys=True))
        if args.dry_run:
            print("Dry run — no file written.")
            return
        write_csv(all_rows, args.output)
        print(f"Written to {args.output}")
        return

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
