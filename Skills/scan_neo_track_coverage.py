#!/usr/bin/env python
"""Gate Z3 -- scan a known NEO's real predicted track for real ZTF coverage.

`Skills/lookup_neo_archive_ephemeris.py`'s first live run exposed a real
targeting error, not just a low-cadence field: the Gate Z1 metadata "hit"
recorded for night 20180902 at RA 232.6, Dec -8.4 was a coincidental
revisit of the *original* fixed field, not evidence that ZTF imaged
wherever the real object (designation 72966) actually was that night. By
night 20180902 the object's real predicted position had moved to
RA~241.6, Dec~-11.6 -- about 9.4 deg in RA and 3.2 deg away from the
original fixed 2-degree search box, so the alert-archive ingest at the old
fixed position (docs/evidence/live/2026-07-02-ztf-alert-archive-ingest-second-attempt.md)
was searching the wrong patch of sky, not confirming the wrong thing about
this specific field's cadence.

This script corrects that: for a subset of the real ephemeris points
already fetched by `Skills/lookup_neo_archive_ephemeris.py` (bounded by
--stride so it does not hammer IRSA with one query per day), it re-centers
each cheap Gate Z1 metadata query (`Skills/ztf_dr24_bounded_ingest.py`,
already live-verified) on that night's real predicted position, and
reports which nights (if any) had real ZTF science exposure near where the
object actually was -- before spending any bandwidth on the expensive
multi-GB alert archive.

Usage:
    caffeinate -i uv run --python 3.14 python Skills/scan_neo_track_coverage.py \\
        --designation 72966 \\
        --start-jd 2458339.5 --end-jd 2458439.5 --step 1d --stride 5
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_SKILLS_DIR = Path(__file__).resolve().parent
_OUT_DIR = Path("Logs/pipeline_runs/scan_neo_track_coverage")


def _load_skill(name: str):
    """Load a sibling Skills/ script by path -- these are not an installed
    package, matching how this project's other cross-Skill imports work."""
    spec = importlib.util.spec_from_file_location(name, _SKILLS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _fmt_duration(seconds: float) -> str:
    """Format elapsed seconds as Mm SSs, per the standing progress-output rule."""
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def run_scan(
    designation: str,
    start_jd: float,
    end_jd: float,
    step: str,
    stride: int,
    size_deg: float,
    out_dir: Path,
) -> dict:
    """Check real ZTF sci-metadata coverage at a known NEO's real predicted
    position on a bounded subset of real nights (every `stride`-th ephemeris
    point), reusing the already live-verified Gate Z1 metadata tool per
    candidate night. Never downloads the multi-GB alert archive itself."""
    lookup = _load_skill("lookup_neo_archive_ephemeris")
    z1 = _load_skill("ztf_dr24_bounded_ingest")

    ephem_report = lookup.run_lookup(
        designation, start_jd, end_jd, step, out_dir / "ephemeris"
    )
    rows = ephem_report["rows"][::stride]
    print(
        f"[scan] Checking {len(rows)} of {ephem_report['n_points']} real "
        f"nights (stride={stride}) for real ZTF coverage near {designation}'s "
        f"predicted position",
        flush=True,
    )

    t0 = time.monotonic()
    hits = []
    for i, row in enumerate(rows, start=1):
        # A 1-day window bracketing this specific real UTC night, centered
        # on the object's real predicted position for that night.
        z1_report = z1.run_bounded_ingest(
            ra=row["ra_deg"],
            dec=row["dec_deg"],
            size_deg=size_deg,
            start_jd=row["jd"] - 0.5,
            end_jd=row["jd"] + 0.5,
            out_dir=out_dir / "z1_checks",
        )
        n_rows = z1_report["n_rows"]
        if n_rows > 0:
            hits.append({**row, "n_sci_rows": n_rows})

        elapsed = time.monotonic() - t0
        eta = (elapsed / i) * (len(rows) - i)
        print(
            f"[scan] ({i}/{len(rows)}) {row['night_yyyymmdd']}: "
            f"RA={row['ra_deg']:.4f} Dec={row['dec_deg']:.4f} -> "
            f"{n_rows} real sci exposure row(s)  elapsed {_fmt_duration(elapsed)}  "
            f"ETA {_fmt_duration(eta)}",
            flush=True,
        )

    report = {
        "designation": designation,
        "n_nights_checked": len(rows),
        "n_nights_with_coverage": len(hits),
        "hits": hits,
        "elapsed_seconds": round(time.monotonic() - t0, 2),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "scan_report.json"
    report_path.write_text(json.dumps(report, indent=2))

    print(
        f"[scan] Complete: {len(hits)}/{len(rows)} checked nights had real "
        f"ZTF coverage near {designation}'s predicted position  "
        f"elapsed {_fmt_duration(time.monotonic() - t0)}",
        flush=True,
    )
    for hit in hits:
        print(
            f"[scan]   HIT {hit['night_yyyymmdd']}: RA={hit['ra_deg']:.4f} "
            f"Dec={hit['dec_deg']:.4f}  ({hit['n_sci_rows']} sci row(s))",
            flush=True,
        )
    print(f"[scan] Wrote {report_path}", flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--designation",
        default="72966",
        help="Real MPC/JPL designation to track (default: 72966).",
    )
    parser.add_argument("--start-jd", type=float, required=True, help="Window start, Julian date")
    parser.add_argument("--end-jd", type=float, required=True, help="Window end, Julian date")
    parser.add_argument("--step", default="1d", help="Horizons ephemeris step size (default: 1d)")
    parser.add_argument(
        "--stride",
        type=int,
        default=5,
        help="Check every Nth ephemeris point (default: 5) -- bounds the "
        "number of IRSA metadata queries issued.",
    )
    parser.add_argument(
        "--size-deg",
        type=float,
        default=2.0,
        help="Gate Z1 sci-metadata search-box size in degrees (default: 2.0).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=_OUT_DIR,
        help=f"Checkpoint directory (default: {_OUT_DIR}).",
    )
    args = parser.parse_args()

    if args.stride < 1:
        raise SystemExit("--stride must be >= 1")

    run_scan(
        args.designation, args.start_jd, args.end_jd, args.step,
        args.stride, args.size_deg, args.out_dir,
    )


if __name__ == "__main__":
    main()
