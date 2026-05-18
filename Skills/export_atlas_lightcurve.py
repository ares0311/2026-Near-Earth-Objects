"""Export an ATLAS forced-photometry light curve for a target.

Fetches ATLAS orange/cyan-band photometry for a sky position and either
plots it as a PNG or exports it as a CSV.

Usage
-----
    python Skills/export_atlas_lightcurve.py \\
        --ra 180.0 --dec 10.0 \\
        --start-jd 2460000.5 --end-jd 2460030.5 \\
        --format png --out lightcurve.png

    python Skills/export_atlas_lightcurve.py \\
        --ra 180.0 --dec 10.0 \\
        --start-jd 2460000.5 --end-jd 2460030.5 \\
        --format csv --out lightcurve.csv

    python Skills/export_atlas_lightcurve.py \\
        --ra 180.0 --dec 10.0 \\
        --start-jd 2460000.5 --end-jd 2460030.5 \\
        --format json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

_BAND_COLORS = {"o": "darkorange", "c": "cyan"}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Export ATLAS forced-photometry light curve."
    )
    parser.add_argument("--ra", type=float, required=True, help="RA in degrees")
    parser.add_argument("--dec", type=float, required=True, help="Dec in degrees")
    parser.add_argument("--start-jd", type=float, required=True, dest="start_jd",
                        help="Start epoch as Julian Date")
    parser.add_argument("--end-jd", type=float, required=True, dest="end_jd",
                        help="End epoch as Julian Date")
    parser.add_argument("--token", default=None, help="ATLAS API token")
    parser.add_argument("--force-refresh", action="store_true", dest="force_refresh",
                        help="Bypass disk cache")
    parser.add_argument("--format", choices=["png", "csv", "json"], default="csv",
                        dest="fmt", help="Output format")
    parser.add_argument("--out", default=None, help="Output file path (omit for stdout/show)")
    args = parser.parse_args(argv)

    from fetch import fetch_atlas_forced

    observations = fetch_atlas_forced(
        ra_deg=args.ra,
        dec_deg=args.dec,
        start_jd=args.start_jd,
        end_jd=args.end_jd,
        atlas_token=args.token,
        force_refresh=args.force_refresh,
    )

    if not observations:
        print("No ATLAS observations found for this position/time range.", file=sys.stderr)
        sys.exit(1)

    rows = [
        {
            "obs_id": o.obs_id,
            "jd": o.jd,
            "ra_deg": o.ra_deg,
            "dec_deg": o.dec_deg,
            "mag": o.mag,
            "mag_err": o.mag_err,
            "filter_band": o.filter_band,
        }
        for o in sorted(observations, key=lambda o: o.jd)
        if o.mag < 90.0
    ]

    if args.fmt == "json":
        out = json.dumps(rows, indent=2)
        if args.out:
            Path(args.out).write_text(out)
            print(f"Saved {len(rows)} observations to {args.out}")
        else:
            print(out)
        return

    if args.fmt == "csv":
        if args.out:
            with open(args.out, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            print(f"Saved {len(rows)} observations to {args.out}")
        else:
            writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return

    # PNG plot
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available; use --format csv or --format json", file=sys.stderr)
        sys.exit(1)

    fig, ax = plt.subplots(figsize=(10, 5))
    for band, color in _BAND_COLORS.items():
        band_rows = [r for r in rows if r["filter_band"] == band]
        if band_rows:
            jds = [r["jd"] for r in band_rows]
            mags = [r["mag"] for r in band_rows]
            errs = [r["mag_err"] for r in band_rows]
            ax.errorbar(jds, mags, yerr=errs, fmt="o", color=color,
                        label=f"ATLAS {band}", markersize=4, capsize=2)

    ax.invert_yaxis()
    ax.set_xlabel("JD")
    ax.set_ylabel("Magnitude")
    ax.set_title(f"ATLAS Light Curve  RA={args.ra:.4f}  Dec={args.dec:.4f}")
    ax.legend()
    plt.tight_layout()

    out_path = args.out or "atlas_lightcurve.png"
    fig.savefig(out_path, dpi=150)
    print(f"Saved light curve plot to {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()
