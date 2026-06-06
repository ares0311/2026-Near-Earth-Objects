#!/usr/bin/env python
"""Download labeled ZTF alert packets from IRSA for Tier 1/2 ML training.

Fetches full ZTF alert Avro packets (which include base64-encoded image
cutouts and rb/drb real/bogus scores) from the IRSA alert archive via
ztfquery. Converts them to the JSON format expected by build_cutout_dataset.py.

IMPORTANT: Run from your Mac, not from the coding agent server.
Credentials are loaded from environment variables set by Keychain:
    ZTF_IRSA_USERNAME, ZTF_IRSA_PASSWORD

Usage (from repo root on your Mac, with venv active):
    source Skills/verify_live_credentials.sh   # loads Keychain creds
    PYTHONPATH=src python Skills/download_ztf_training_alerts.py
    PYTHONPATH=src python Skills/download_ztf_training_alerts.py --nights 7 --limit 5000
    PYTHONPATH=src python Skills/download_ztf_training_alerts.py --dry-run

Output: data/ztf_labeled_alerts.json
    List of alert dicts with keys: label, rb, drb, observations (with cutouts).
    Feed directly into Skills/build_cutout_dataset.py.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Ensure src/ is importable when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# rb threshold: alerts with rb >= REAL_THRESHOLD are labeled "real",
# alerts with rb < BOGUS_THRESHOLD are labeled "bogus".
# Alerts between the two thresholds are ambiguous and excluded.
REAL_THRESHOLD = 0.65   # ZTF standard rb cut for real detections
BOGUS_THRESHOLD = 0.35  # conservative bogus cut to avoid borderline labels


def configure_ztfquery_credentials() -> None:
    """Write IRSA credentials from env vars into the ztfquery config file.

    ztfquery reads credentials from ~/.ztfquery. We populate it from
    the env vars loaded by verify_live_credentials.sh so no plaintext
    credentials are stored in the repo.
    """
    username = os.environ.get("ZTF_IRSA_USERNAME", "")
    password = os.environ.get("ZTF_IRSA_PASSWORD", "")
    if not username or not password:
        raise RuntimeError(
            "ZTF_IRSA_USERNAME and ZTF_IRSA_PASSWORD must be set. "
            "Run: source Skills/verify_live_credentials.sh"
        )

    # ztfquery stores credentials in ~/.ztfquery as a simple key=value file
    config_dir = Path.home() / ".ztfquery"
    config_dir.mkdir(exist_ok=True)
    config_file = config_dir / "irsa_account.cfg"
    config_file.write_text(f"[IRSA]\nusername = {username}\npassword = {password}\n")
    config_file.chmod(0o600)  # restrict permissions — contains credentials
    print(f"  IRSA credentials written to {config_file} (chmod 600)")


def download_alerts_ztfquery(
    nights: int = 30,
    limit: int = 10000,
    rb_real: float = REAL_THRESHOLD,
    rb_bogus: float = BOGUS_THRESHOLD,
) -> list[dict]:
    """Download ZTF alert packets from IRSA via ztfquery and label by rb score.

    Queries the last `nights` nights of ZTF alerts, downloads full Avro
    packets (which include image cutouts), and labels each alert as real
    (rb >= rb_real) or bogus (rb < rb_bogus). Ambiguous alerts excluded.

    Returns a list of dicts ready for build_cutout_dataset.py.
    """
    try:
        from ztfquery import query as zquery  # type: ignore[import]
    except ImportError:
        raise RuntimeError("ztfquery not installed. Run: pip install ztfquery")

    # Build date range for the query: last `nights` nights up to today
    end_date = datetime.now(tz=UTC)
    start_date = end_date - timedelta(days=nights)
    jd_start = 2440587.5 + start_date.timestamp() / 86400.0
    jd_end = 2440587.5 + end_date.timestamp() / 86400.0

    print(f"  Querying ZTF alerts: JD {jd_start:.2f} – {jd_end:.2f} ({nights} nights)")

    # Use ztfquery to search IRSA for alerts in the date range.
    # We request a broad all-sky query and filter by rb score locally.
    zq = zquery.ZTFQuery()
    zq.load_metatable(
        kind="sci",
        sql_query=f"obsjd BETWEEN {jd_start} AND {jd_end}",
        limit=limit,
    )

    if len(zq.metatable) == 0:
        print("  No alerts found in date range.")
        return []

    print(f"  Found {len(zq.metatable)} alert files; downloading packets...")

    # Download the alert Avro files to local cache (~/.ztfquery/sci/)
    zq.download_data(
        suffix="sciimg.fits",  # triggers alert packet download
        show_progress=True,
        nprocess=4,  # parallel downloads
    )

    # Parse downloaded Avro packets and extract cutouts + rb labels
    results = []
    for filepath in zq.get_local_data("sciimg.fits"):
        try:
            alert_dict = _parse_avro_alert(filepath, rb_real, rb_bogus)
            if alert_dict is not None:
                results.append(alert_dict)
        except Exception as e:
            print(f"  Warning: could not parse {filepath}: {e}", file=sys.stderr)

    return results


def _parse_avro_alert(
    filepath: str,
    rb_real: float,
    rb_bogus: float,
) -> dict | None:
    """Parse a single ZTF Avro alert file into the JSON format for build_cutout_dataset.

    Returns None if the alert is ambiguous (rb between thresholds) or
    if required fields are missing.
    """
    try:
        import fastavro  # type: ignore[import]
    except ImportError:
        raise RuntimeError("fastavro not installed. Run: pip install fastavro")

    with open(filepath, "rb") as f:
        reader = fastavro.reader(f)
        for record in reader:
            # Extract the real/bogus score (rb) and deep-learning rb (drb)
            rb = float(record.get("candidate", {}).get("rb", -1.0))
            drb = float(record.get("candidate", {}).get("drb", -1.0))

            # Assign label based on rb threshold; skip ambiguous zone
            if rb >= rb_real:
                label = 0  # real (neo_candidate class in pipeline schema)
            elif rb < rb_bogus:
                label = 3  # bogus (stellar_artifact class in pipeline schema)
            else:
                return None  # ambiguous — skip

            # Extract base64-encoded cutout images (63×63 float32)
            cutout_science = record.get("cutoutScience", {}).get("stampData", b"")
            cutout_reference = record.get("cutoutTemplate", {}).get("stampData", b"")
            cutout_difference = record.get("cutoutDifference", {}).get("stampData", b"")

            # Build the observation dict that build_cutout_dataset.py expects
            obs = {
                "cutout_science": base64.b64encode(cutout_science).decode("ascii"),
                "cutout_reference": base64.b64encode(cutout_reference).decode("ascii"),
                "cutout_difference": base64.b64encode(cutout_difference).decode("ascii"),
                "rb": rb,
                "drb": drb,
            }

            return {
                "label": label,
                "rb": rb,
                "drb": drb,
                "observations": [obs],
            }
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download labeled ZTF alerts from IRSA (run from Mac, not coding agent server)"
    )
    parser.add_argument(
        "--nights", type=int, default=30,
        help="Number of past nights to query (default: 30)"
    )
    parser.add_argument(
        "--limit", type=int, default=10000,
        help="Max alert files to download (default: 10000)"
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/ztf_labeled_alerts.json"),
        help="Output JSON file for build_cutout_dataset.py"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Configure credentials and query metadata only; do not download packets"
    )
    args = parser.parse_args()

    print("Step 1: Configuring IRSA credentials from environment...")
    configure_ztfquery_credentials()

    if args.dry_run:
        print("Dry run — skipping packet download.")
        return

    print(f"Step 2: Downloading ZTF alerts ({args.nights} nights, limit {args.limit})...")
    alerts = download_alerts_ztfquery(nights=args.nights, limit=args.limit)

    # Count label distribution for reporting
    n_real = sum(1 for a in alerts if a["label"] == 0)
    n_bogus = sum(1 for a in alerts if a["label"] == 3)
    print(f"  Downloaded: {len(alerts)} labeled alerts ({n_real} real, {n_bogus} bogus)")

    if not alerts:
        print("No alerts downloaded. Check credentials and date range.")
        return

    print(f"Step 3: Writing to {args.output}...")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as f:
        json.dump(alerts, f)
    print(f"  Written: {args.output} ({args.output.stat().st_size / 1e6:.1f} MB)")
    print()
    print("Next step:")
    print("  PYTHONPATH=src python Skills/build_cutout_dataset.py \\")
    print(f"      --input {args.output} \\")
    print("      --output-dir data/cutouts/ \\")
    print("      --csv data/cutouts/index.csv")


if __name__ == "__main__":
    main()
